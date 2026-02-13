"""Long-term memory — key-value store the agent can read/write."""

from __future__ import annotations

from typing import Any

import structlog

from paw.agent.tools import Tool

logger = structlog.get_logger()


class MemoryTool(Tool):
    """Key-value memory that persists across conversations."""

    def __init__(self, db: Any = None) -> None:
        self._store: dict[str, str] = {}
        self._db = db

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Persistent key-value memory. Use this to remember important information "
            "across conversations. Actions: 'remember' (store a value), 'recall' (retrieve "
            "a value), 'forget' (delete a value), 'list' (show all keys)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["remember", "recall", "forget", "list"],
                    "description": "The memory action to perform.",
                },
                "key": {
                    "type": "string",
                    "description": "The memory key (not needed for 'list').",
                },
                "value": {
                    "type": "string",
                    "description": "The value to store (only for 'remember').",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, key: str = "", value: str = "") -> str:
        """Execute a memory operation."""
        if action == "remember":
            if not key or not value:
                return "Error: 'remember' requires both 'key' and 'value'."
            self._store[key] = value
            await self._persist(key, value)
            logger.info("memory.remember", key=key)
            return f"Remembered: {key} = {value}"

        elif action == "recall":
            if not key:
                return "Error: 'recall' requires a 'key'."
            val = self._store.get(key)
            if val is None:
                return f"No memory found for key '{key}'."
            return f"{key} = {val}"

        elif action == "forget":
            if not key:
                return "Error: 'forget' requires a 'key'."
            if key in self._store:
                del self._store[key]
                await self._delete(key)
                return f"Forgot: {key}"
            return f"No memory found for key '{key}'."

        elif action == "list":
            if not self._store:
                return "Memory is empty."
            items = [f"  {k}: {v}" for k, v in self._store.items()]
            return f"Stored memories ({len(self._store)}):\n" + "\n".join(items)

        return f"Unknown action: {action}"

    async def load_from_db(self) -> None:
        """Load all memories from database."""
        if not self._db:
            return
        try:
            rows = await self._db.fetch_all("SELECT key, value FROM memory")
            for row in rows:
                self._store[row["key"]] = row["value"]
            logger.info("memory.loaded_from_db", count=len(rows))
        except Exception:
            pass

    async def _persist(self, key: str, value: str) -> None:
        """Save a memory to the database."""
        if not self._db:
            return
        try:
            await self._db.execute(
                "INSERT OR REPLACE INTO memory (key, value) VALUES (?, ?)",
                (key, value),
            )
        except Exception as e:
            logger.error("memory.persist_failed", key=key, error=str(e))

    async def _delete(self, key: str) -> None:
        """Delete a memory from the database."""
        if not self._db:
            return
        try:
            await self._db.execute("DELETE FROM memory WHERE key = ?", (key,))
        except Exception as e:
            logger.error("memory.delete_failed", key=key, error=str(e))
