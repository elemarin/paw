"""SQLite async database — PAW's persistent memory.

Provides:
- Conversation history
- Message storage
- Tool call logs
- Key-value memory
- Plugin state
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

logger = structlog.get_logger()

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    tool_call_id TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT,
    result TEXT,
    duration_ms INTEGER,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plugin_state (
    plugin_name TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (plugin_name, key)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_conversation ON tool_calls(conversation_id);
"""


class Database:
    """Async SQLite database for PAW."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "paw.db"
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and run migrations."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrency
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

        # Create tables
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

        logger.info("db.initialized", path=str(self.db_path))

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("db.closed")

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a SQL statement."""
        assert self._conn, "Database not initialized"
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute a SQL statement with multiple parameter sets."""
        assert self._conn, "Database not initialized"
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Fetch a single row."""
        assert self._conn, "Database not initialized"
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Fetch all rows."""
        assert self._conn, "Database not initialized"
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ── Convenience methods for memory ──────────────────────────────

    async def memory_set(self, key: str, value: str) -> None:
        """Set a key-value pair in memory."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await self.execute(
            "INSERT OR REPLACE INTO memory (key, value, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (key, value, now, now),
        )

    async def memory_get(self, key: str) -> str | None:
        """Get a value from memory."""
        row = await self.fetch_one("SELECT value FROM memory WHERE key = ?", (key,))
        return row["value"] if row else None

    async def memory_delete(self, key: str) -> bool:
        """Delete a key from memory."""
        cursor = await self.execute("DELETE FROM memory WHERE key = ?", (key,))
        return cursor.rowcount > 0

    async def memory_list(self) -> list[dict[str, str]]:
        """List all memory keys."""
        return await self.fetch_all("SELECT key, value, updated_at FROM memory ORDER BY key")

    # ── Plugin state ────────────────────────────────────────────────

    async def plugin_state_set(self, plugin: str, key: str, value: str) -> None:
        """Set a plugin state value."""
        await self.execute(
            "INSERT OR REPLACE INTO plugin_state (plugin_name, key, value) VALUES (?, ?, ?)",
            (plugin, key, value),
        )

    async def plugin_state_get(self, plugin: str, key: str) -> str | None:
        """Get a plugin state value."""
        row = await self.fetch_one(
            "SELECT value FROM plugin_state WHERE plugin_name = ? AND key = ?",
            (plugin, key),
        )
        return row["value"] if row else None
