"""Conversation state manager."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Message:
    """A single message in a conversation."""

    role: str
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI message format."""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        return msg


@dataclass
class Conversation:
    """A multi-turn conversation."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> Message:
        """Add a message to the conversation."""
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        return msg

    def add_tool_result(self, tool_call_id: str, content: str) -> Message:
        """Add a tool result message."""
        return self.add_message("tool", content, tool_call_id=tool_call_id)

    def to_messages(self) -> list[dict[str, Any]]:
        """Convert all messages to OpenAI format."""
        normalized: list[dict[str, Any]] = []
        valid_tool_call_ids: set[str] = set()

        for msg in self.messages:
            raw = msg.to_dict()
            role = raw.get("role")

            if role == "assistant":
                tool_calls = raw.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        tool_call_id = tool_call.get("id")
                        if isinstance(tool_call_id, str) and tool_call_id:
                            valid_tool_call_ids.add(tool_call_id)
                normalized.append(raw)
                continue

            if role == "tool":
                tool_call_id = raw.get("tool_call_id")
                if isinstance(tool_call_id, str) and tool_call_id in valid_tool_call_ids:
                    normalized.append(raw)
                else:
                    logger.warning("conversation.drop_orphan_tool_message", conversation_id=self.id)
                continue

            normalized.append(raw)

        return normalized

    @property
    def last_user_message(self) -> str | None:
        """Get the last user message content."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
        return None


class ConversationManager:
    """Manages all conversations."""

    def __init__(self, db: Any = None, soul: str = "") -> None:
        self._conversations: dict[str, Conversation] = {}
        self._db = db
        self._soul = soul

    def get_or_create(self, conversation_id: str | None = None) -> Conversation:
        """Get an existing conversation or create a new one."""
        if conversation_id and conversation_id in self._conversations:
            return self._conversations[conversation_id]

        conv = Conversation(id=conversation_id or str(uuid.uuid4()))
        # Inject soul as system message
        if self._soul:
            conv.add_message("system", self._soul)

        self._conversations[conv.id] = conv
        logger.info("conversation.created", id=conv.id)
        return conv

    def get(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID."""
        return self._conversations.get(conversation_id)

    def list_all(self) -> list[dict[str, Any]]:
        """List all conversations."""
        return [
            {
                "id": c.id,
                "title": c.title or c.last_user_message or "Untitled",
                "created_at": c.created_at.isoformat(),
                "message_count": len(c.messages),
            }
            for c in self._conversations.values()
        ]

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    async def load_from_db(self) -> None:
        """Load conversations from database."""
        if not self._db:
            return
        try:
            rows = await self._db.fetch_all(
                "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
            )
            for row in rows:
                conv = Conversation(
                    id=row["id"],
                    title=row["title"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                # Load messages
                msg_rows = await self._db.fetch_all(
                    "SELECT role, content, tool_calls, tool_call_id, timestamp "
                    "FROM messages WHERE conversation_id = ? ORDER BY timestamp",
                    (row["id"],),
                )
                for mr in msg_rows:
                    tool_calls = None
                    raw_tool_calls = mr.get("tool_calls")
                    if raw_tool_calls:
                        try:
                            parsed = json.loads(raw_tool_calls)
                            if isinstance(parsed, list):
                                tool_calls = parsed
                        except json.JSONDecodeError:
                            logger.warning(
                                "conversation.invalid_tool_calls_json",
                                conversation_id=row["id"],
                            )

                    conv.messages.append(Message(
                        role=mr["role"],
                        content=mr["content"],
                        tool_calls=tool_calls,
                        tool_call_id=mr.get("tool_call_id"),
                        timestamp=datetime.fromisoformat(mr["timestamp"]),
                    ))
                self._conversations[conv.id] = conv
            logger.info("conversations.loaded_from_db", count=len(rows))
        except Exception as e:
            logger.warning("conversations.db_load_failed", error=str(e))

    async def save_conversation(self, conv: Conversation) -> None:
        """Save a conversation to the database."""
        if not self._db:
            return
        try:
            await self._db.execute(
                """INSERT OR REPLACE INTO conversations (id, title, created_at)
                   VALUES (?, ?, ?)""",
                (conv.id, conv.title or conv.last_user_message, conv.created_at.isoformat()),
            )
            # Save new messages (simple: delete and re-insert)
            await self._db.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conv.id,)
            )
            for msg in conv.messages:
                serialized_tool_calls = None
                if msg.tool_calls:
                    serialized_tool_calls = json.dumps(msg.tool_calls)

                await self._db.execute(
                    """INSERT INTO messages (
                       conversation_id, role, content, tool_calls, tool_call_id, timestamp
                    )
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        conv.id,
                        msg.role,
                        msg.content,
                        serialized_tool_calls,
                        msg.tool_call_id,
                        msg.timestamp.isoformat(),
                    ),
                )
        except Exception as e:
            logger.error("conversation.save_failed", id=conv.id, error=str(e))
