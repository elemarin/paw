"""Deterministic session routing for channel events."""

from __future__ import annotations

import uuid

from paw.db.engine import Database


class ChannelRouter:
    """Maps channel session keys to persistent PAW conversation IDs."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def resolve_conversation_id(self, channel: str, session_key: str) -> str:
        """Return existing mapped conversation id or create a new one."""
        existing = await self.db.channel_session_get(channel, session_key)
        if existing:
            return existing

        conversation_id = str(uuid.uuid4())
        await self.db.channel_session_set(channel, session_key, conversation_id)
        return conversation_id
