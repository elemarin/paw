"""PostgreSQL async database — PAW's persistent memory.

Provides:
- Conversation history
- Message storage
- Tool call logs
- Key-value memory
- Plugin state
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
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
    id BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    tool_call_id TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id BIGSERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS channel_pairing_codes (
    channel TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_by TEXT,
    used_at TEXT,
    PRIMARY KEY (channel, code)
);

CREATE TABLE IF NOT EXISTS channel_pairings (
    channel TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (channel, sender_id)
);

CREATE TABLE IF NOT EXISTS heartbeat_cron_jobs (
    id BIGSERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    schedule TEXT NOT NULL,
    prompt TEXT NOT NULL,
    output_target TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_conversation ON tool_calls(conversation_id);
CREATE INDEX IF NOT EXISTS idx_channel_dedupe_created_at ON channel_dedupe(created_at);
CREATE INDEX IF NOT EXISTS idx_heartbeat_cron_jobs_enabled ON heartbeat_cron_jobs(enabled);
"""


@dataclass
class ExecuteResult:
    rowcount: int


class Database:
    """Async PostgreSQL database for PAW."""

    def __init__(
        self,
        database_url: str,
        data_dir: str = "data",
    ) -> None:
        self.database_url = database_url.strip()
        if not self.database_url:
            raise ValueError("PAW_DATABASE_URL is required")
        self.data_dir = str(Path(data_dir))
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        """Create the database and run migrations."""
        self._pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=10)
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA)
            column_exists = await conn.fetchval(
                """SELECT EXISTS (
                       SELECT 1
                       FROM information_schema.columns
                       WHERE table_name = 'heartbeat_cron_jobs'
                         AND table_schema = current_schema()
                         AND column_name = 'output_target'
                   )"""
            )
            if not column_exists:
                await conn.execute("ALTER TABLE heartbeat_cron_jobs ADD COLUMN output_target TEXT")
        logger.info("db.initialized", backend="postgresql")

    async def close(self) -> None:
        """Close the database connection."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("db.closed")

    @staticmethod
    def _translate_sql(sql: str) -> str:
        index = 0
        translated: list[str] = []
        for char in sql:
            if char == "?":
                index += 1
                translated.append(f"${index}")
            else:
                translated.append(char)
        return "".join(translated)

    @staticmethod
    def _parse_rowcount(status: str) -> int:
        parts = status.strip().split()
        if not parts:
            return 0
        last = parts[-1]
        try:
            return int(last)
        except ValueError:
            return 0

    async def execute(self, sql: str, params: tuple = ()) -> ExecuteResult:
        """Execute a SQL statement."""
        assert self._pool, "Database not initialized"
        translated = self._translate_sql(sql)
        async with self._pool.acquire() as conn:
            status = await conn.execute(translated, *params)
        return ExecuteResult(rowcount=self._parse_rowcount(status))

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute a SQL statement with multiple parameter sets."""
        assert self._pool, "Database not initialized"
        if not params_list:
            return
        translated = self._translate_sql(sql)
        async with self._pool.acquire() as conn:
            await conn.executemany(translated, params_list)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Fetch a single row."""
        assert self._pool, "Database not initialized"
        translated = self._translate_sql(sql)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(translated, *params)
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Fetch all rows."""
        assert self._pool, "Database not initialized"
        translated = self._translate_sql(sql)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(translated, *params)
        return [dict(row) for row in rows]

    # ── Convenience methods for memory ──────────────────────────────

    async def memory_set(self, key: str, value: str) -> None:
        """Set a key-value pair in memory."""
        now = datetime.now(UTC).isoformat()
        await self.execute(
            (
                "INSERT INTO memory (key, value, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (key) DO UPDATE SET "
                "value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
            ),
            (key, value, now, now),
        )

    async def memory_get(self, key: str) -> str | None:
        """Get a value from memory."""
        row = await self.fetch_one("SELECT value FROM memory WHERE key = ?", (key,))
        return row["value"] if row else None

    async def memory_delete(self, key: str) -> bool:
        """Delete a key from memory."""
        result = await self.execute("DELETE FROM memory WHERE key = ?", (key,))
        return result.rowcount > 0

    async def memory_list(self) -> list[dict[str, str]]:
        """List all memory keys."""
        return await self.fetch_all("SELECT key, value, updated_at FROM memory ORDER BY key")

    # ── Plugin state ────────────────────────────────────────────────

    async def plugin_state_set(self, plugin: str, key: str, value: str) -> None:
        """Set a plugin state value."""
        await self.execute(
            (
                "INSERT INTO plugin_state (plugin_name, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT (plugin_name, key) DO UPDATE SET value = EXCLUDED.value"
            ),
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
        now = datetime.now(UTC).isoformat()
        await self.execute(
                """INSERT INTO channel_offsets
                    (channel, account_id, last_update_id, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (channel, account_id)
               DO UPDATE SET
                   last_update_id = EXCLUDED.last_update_id,
                   updated_at = EXCLUDED.updated_at""",
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
        now = datetime.now(UTC).isoformat()
        await self.execute(
                """INSERT INTO channel_dedupe (channel, key, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT (channel, key) DO NOTHING""",
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
        now = datetime.now(UTC).isoformat()
        await self.execute(
                """INSERT INTO channel_sessions
                    (channel, session_key, conversation_id, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (channel, session_key)
               DO UPDATE SET
                   conversation_id = EXCLUDED.conversation_id,
                   updated_at = EXCLUDED.updated_at""",
            (channel, session_key, conversation_id, now),
        )

    async def channel_session_latest_key(self, channel: str) -> str | None:
        """Return the most recently updated session key for a channel."""
        row = await self.fetch_one(
            """SELECT session_key
               FROM channel_sessions
               WHERE channel = ?
               ORDER BY updated_at DESC
               LIMIT 1""",
            (channel,),
        )
        return str(row["session_key"]) if row and row.get("session_key") else None

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
        now = datetime.now(UTC).isoformat()
        await self.execute(
            """INSERT INTO channel_runtime
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
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (channel, account_id)
               DO UPDATE SET
                   mode = EXCLUDED.mode,
                   running = EXCLUDED.running,
                   last_error = EXCLUDED.last_error,
                   last_inbound_at = EXCLUDED.last_inbound_at,
                   last_outbound_at = EXCLUDED.last_outbound_at,
                   updated_at = EXCLUDED.updated_at""",
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
        now = datetime.now(UTC).isoformat()
        await self.execute(
            """INSERT INTO channel_session_modes
                    (channel, session_key, mode, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (channel, session_key)
               DO UPDATE SET
                   mode = EXCLUDED.mode,
                   updated_at = EXCLUDED.updated_at""",
            (channel, session_key, mode, now),
        )

    async def channel_pairing_code_create(
        self,
        *,
        channel: str,
        code: str,
        ttl_minutes: int,
    ) -> None:
        """Create a pairing code for a channel."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=max(1, ttl_minutes))
        await self.execute(
            """INSERT INTO channel_pairing_codes
                    (channel, code, created_at, expires_at, used_by, used_at)
               VALUES (?, ?, ?, ?, NULL, NULL)
               ON CONFLICT (channel, code)
               DO UPDATE SET
                    created_at = EXCLUDED.created_at,
                    expires_at = EXCLUDED.expires_at,
                    used_by = NULL,
                    used_at = NULL""",
            (channel, code, now.isoformat(), expires_at.isoformat()),
        )

    async def channel_pairing_claim(self, *, channel: str, code: str, sender_id: str) -> bool:
        """Claim an existing pairing code."""
        row = await self.fetch_one(
            """SELECT expires_at, used_by
               FROM channel_pairing_codes
               WHERE channel = ? AND code = ?""",
            (channel, code),
        )
        if not row or row.get("used_by"):
            return False

        try:
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
        except Exception:
            return False

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return False

        now = datetime.now(UTC).isoformat()
        result = await self.execute(
            """UPDATE channel_pairing_codes
               SET used_by = ?, used_at = ?
               WHERE channel = ? AND code = ? AND used_by IS NULL""",
            (sender_id, now, channel, code),
        )
        if result.rowcount <= 0:
            return False

        await self.execute(
            """INSERT INTO channel_pairings (channel, sender_id, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT (channel, sender_id) DO NOTHING""",
            (channel, sender_id, now),
        )
        return True

    async def channel_pairing_is_allowed(self, *, channel: str, sender_id: str) -> bool:
        """Return whether sender is paired for channel."""
        row = await self.fetch_one(
            "SELECT 1 FROM channel_pairings WHERE channel = ? AND sender_id = ?",
            (channel, sender_id),
        )
        return bool(row)

    async def heartbeat_cron_add(
        self,
        *,
        label: str,
        schedule: str,
        prompt: str,
        output_target: str | None = None,
    ) -> None:
        """Add a heartbeat cron job."""
        await self.execute(
            """INSERT INTO heartbeat_cron_jobs
                    (label, schedule, prompt, output_target, enabled, last_run_at, created_at)
               VALUES (?, ?, ?, ?, 1, NULL, ?)""",
            (label, schedule, prompt, output_target, datetime.now(UTC).isoformat()),
        )

    async def heartbeat_cron_list(self) -> list[dict[str, Any]]:
        """List configured heartbeat cron jobs."""
        return await self.fetch_all(
            """SELECT id, label, schedule, prompt, output_target, enabled, last_run_at, created_at
               FROM heartbeat_cron_jobs
               ORDER BY id ASC"""
        )

    async def heartbeat_cron_remove(self, *, job_id: int) -> bool:
        """Remove a heartbeat cron job."""
        result = await self.execute("DELETE FROM heartbeat_cron_jobs WHERE id = ?", (job_id,))
        return result.rowcount > 0

    async def heartbeat_cron_mark_run(self, *, job_id: int) -> None:
        """Update cron job last-run timestamp."""
        await self.execute(
            "UPDATE heartbeat_cron_jobs SET last_run_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), job_id),
        )
