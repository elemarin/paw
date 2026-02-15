"""Long-term memory — key-value store the agent can read/write."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from memsearch.store import MilvusStore

from paw.agent.tools import Tool

if TYPE_CHECKING:
    from paw.db.engine import Database

logger = structlog.get_logger()


class MemoryTool(Tool):
    """Key-value memory that persists across conversations."""

    _MEMORY_SOURCE = "paw://memory"
    # Milvus requires vector fields; use a stable placeholder because lookups are key-based.
    _DEFAULT_EMBEDDING = [1.0, 0.0]

    def __init__(self, db: Database | None = None) -> None:
        self._store: dict[str, str] = {}
        data_dir = Path(db.data_dir) if db else Path("data")
        self._memsearch = MilvusStore(
            uri=str(data_dir / "memsearch.db"),
            collection="paw_memory",
            dimension=2,
        )

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
            try:
                self._memsearch.upsert([self._to_chunk(key, value)])
                self._store[key] = value
            except Exception as e:
                logger.error("memory.remember_failed", key=key, error=str(e))
                return "Error: failed to store memory."
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
                try:
                    self._memsearch.delete_by_hashes([self._hash_key(key)])
                    del self._store[key]
                except Exception as e:
                    logger.error("memory.forget_failed", key=key, error=str(e))
                    return "Error: failed to delete memory."
                return f"Forgot: {key}"
            return f"No memory found for key '{key}'."

        elif action == "list":
            if not self._store:
                return "Memory is empty."
            items = [f"  {k}: {v}" for k, v in self._store.items()]
            return f"Stored memories ({len(self._store)}):\n" + "\n".join(items)

        return f"Unknown action: {action}"

    async def load_from_db(self) -> None:
        """Load all memories from memsearch store."""
        try:
            self._sync_from_store()
            logger.info("memory.loaded_from_store", count=len(self._store))
        except Exception:
            pass

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _to_chunk(self, key: str, value: str) -> dict[str, Any]:
        return {
            "chunk_hash": self._hash_key(key),
            "embedding": self._DEFAULT_EMBEDDING,
            "content": value,
            "source": self._MEMORY_SOURCE,
            "heading": key,
            "heading_level": 1,
            "start_line": 1,
            "end_line": 1,
        }

    def _sync_from_store(self) -> None:
        rows = self._memsearch.query(filter_expr=f'source == "{self._MEMORY_SOURCE}"')
        self._store = {
            str(row.get("heading", "")): str(row.get("content", ""))
            for row in rows
            if row.get("heading")
        }
