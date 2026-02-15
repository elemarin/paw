"""SQLite async database — PAW's persistent memory.

Provides:
- Conversation history
- Message storage
- Tool call logs
- Key-value memory
- Plugin state
"""

from __future__ import annotations

from datetime import UTC
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

CREATE TABLE IF NOT EXISTS channel_offsets (
    channel TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT 'default',
    last_update_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, account_id)
);

CREATE TABLE IF NOT EXISTS channel_dedupe (
    channel TEXT NOT NULL,
    key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (channel, key)
);

CREATE TABLE IF NOT EXISTS channel_sessions (
    channel TEXT NOT NULL,
    session_key TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, session_key)
);

CREATE TABLE IF NOT EXISTS channel_session_modes (
    channel TEXT NOT NULL,
    session_key TEXT NOT NULL,
    mode TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, session_key)
);

CREATE TABLE IF NOT EXISTS channel_runtime (
    channel TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT 'default',
    mode TEXT NOT NULL,
    running INTEGER NOT NULL,
    last_error TEXT,
    last_inbound_at TEXT,
    last_outbound_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, account_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_conversation ON tool_calls(conversation_id);
CREATE INDEX IF NOT EXISTS idx_channel_dedupe_created_at ON channel_dedupe(created_at);
"""


class Database:
    """Async SQLite database for PAW."""

    def __init__(
        self,
        data_dir: str,
        journal_mode: str = "WAL",
        busy_timeout_ms: int = 5000,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "paw.db"
        self.journal_mode = journal_mode.upper()
        if self.journal_mode not in {"WAL", "DELETE"}:
            raise ValueError(f"Unsupported SQLite journal mode: {journal_mode}")
        self.busy_timeout_ms = int(busy_timeout_ms)
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and run migrations."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row

        # WAL is great on local disks, but may fail on network filesystems
        # (e.g., Azure Files). Fall back to DELETE mode if WAL is unavailable.
        try:
            await self._conn.execute(f"PRAGMA journal_mode={self.journal_mode}")
        except Exception as exc:
            if self.journal_mode == "WAL":
                logger.warning(
                    "db.wal_unavailable_fallback",
                    path=str(self.db_path),
                    error=str(exc),
                )
                await self._conn.execute("PRAGMA journal_mode=DELETE")
            else:
                raise

        await self._conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
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
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        await self.execute(
            (
                "INSERT OR REPLACE INTO memory "
                "(key, value, created_at, updated_at) VALUES (?, ?, ?, ?)"
            ),
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

    # ── Channel runtime state ─────────────────────────────────────

    async def channel_offset_get(self, channel: str, account_id: str = "default") -> int | None:
        """Get last processed update offset for a channel account."""
        row = await self.fetch_one(
            "SELECT last_update_id FROM channel_offsets WHERE channel = ? AND account_id = ?",
            (channel, account_id),
        )
        if not row:
            return None
        try:
            return int(row["last_update_id"])
        except Exception:
            return None

    async def channel_offset_set(
        self,
        channel: str,
        last_update_id: int,
        account_id: str = "default",
    ) -> None:
        """Set last processed update offset for a channel account."""
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        await self.execute(
                """INSERT OR REPLACE INTO channel_offsets
                    (channel, account_id, last_update_id, updated_at)
               VALUES (?, ?, ?, ?)""",
            (channel, account_id, int(last_update_id), now),
        )

    async def channel_dedupe_exists(self, channel: str, key: str) -> bool:
        """Check whether a dedupe key has already been seen."""
        row = await self.fetch_one(
            "SELECT 1 FROM channel_dedupe WHERE channel = ? AND key = ?",
            (channel, key),
        )
        return bool(row)

    async def channel_dedupe_add(self, channel: str, key: str) -> None:
        """Store a dedupe key."""
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        await self.execute(
            """INSERT OR REPLACE INTO channel_dedupe (channel, key, created_at)
               VALUES (?, ?, ?)""",
            (channel, key, now),
        )

    async def channel_dedupe_prune(self, channel: str, keep_last: int = 5000) -> None:
        """Prune dedupe records for a channel to bound table growth."""
        keep_last = max(100, int(keep_last))
        await self.execute(
            """DELETE FROM channel_dedupe
               WHERE channel = ?
                 AND key NOT IN (
                   SELECT key FROM channel_dedupe
                   WHERE channel = ?
                   ORDER BY created_at DESC
                   LIMIT ?
                 )""",
            (channel, channel, keep_last),
        )

    async def channel_session_get(self, channel: str, session_key: str) -> str | None:
        """Get mapped conversation id for a channel session key."""
        row = await self.fetch_one(
            "SELECT conversation_id FROM channel_sessions WHERE channel = ? AND session_key = ?",
            (channel, session_key),
        )
        return row["conversation_id"] if row else None

    async def channel_session_set(
        self,
        channel: str,
        session_key: str,
        conversation_id: str,
    ) -> None:
        """Set mapped conversation id for a channel session key."""
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        await self.execute(
                """INSERT OR REPLACE INTO channel_sessions
                    (channel, session_key, conversation_id, updated_at)
               VALUES (?, ?, ?, ?)""",
            (channel, session_key, conversation_id, now),
        )

    async def channel_runtime_upsert(
        self,
        *,
        channel: str,
        mode: str,
        running: bool,
        account_id: str = "default",
        last_error: str | None = None,
        last_inbound_at: str | None = None,
        last_outbound_at: str | None = None,
    ) -> None:
        """Insert/update runtime status for a channel."""
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        await self.execute(
            """INSERT OR REPLACE INTO channel_runtime
                             (
                                 channel,
                                 account_id,
                                 mode,
                                 running,
                                 last_error,
                                 last_inbound_at,
                                 last_outbound_at,
                                 updated_at
                             )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                channel,
                account_id,
                mode,
                1 if running else 0,
                last_error,
                last_inbound_at,
                last_outbound_at,
                now,
            ),
        )

    async def channel_runtime_list(self) -> list[dict[str, Any]]:
        """List runtime records for all channels."""
        return await self.fetch_all(
            """SELECT channel, account_id, mode, running, last_error,
                      last_inbound_at, last_outbound_at, updated_at
               FROM channel_runtime ORDER BY channel, account_id"""
        )

    async def channel_session_mode_get(self, channel: str, session_key: str) -> str | None:
        """Get selected mode for a channel session key."""
        row = await self.fetch_one(
            "SELECT mode FROM channel_session_modes WHERE channel = ? AND session_key = ?",
            (channel, session_key),
        )
        return row["mode"] if row else None

    async def channel_session_mode_set(self, channel: str, session_key: str, mode: str) -> None:
        """Set selected mode for a channel session key."""
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        await self.execute(
            """INSERT OR REPLACE INTO channel_session_modes
                    (channel, session_key, mode, updated_at)
               VALUES (?, ?, ?, ?)""",
            (channel, session_key, mode, now),
        )
