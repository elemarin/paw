"""Telegram channel provider (polling-first)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from paw.channels.base import ChannelInboundEvent, ChannelProvider, ChannelStatus
from paw.config import TelegramChannelConfig
from paw.db.engine import Database

logger = structlog.get_logger()


class TelegramChannelProvider(ChannelProvider):
    def __init__(
        self,
        *,
        config: TelegramChannelConfig,
        db: Database,
        inbound_handler,
    ) -> None:
        self.config = config
        self.db = db
        self.inbound_handler = inbound_handler

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

        self._offset = 0
        self._bot_username: str | None = None
        self._status = ChannelStatus(
            channel="telegram",
            mode=self.config.mode,
            running=False,
            enabled=self.enabled,
        )

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self.config.bot_token.strip())

    def status(self) -> ChannelStatus:
        return self._status

    async def start(self) -> None:
        if not self.enabled:
            return
        if self.config.mode != "polling":
            raise ValueError(
                "Telegram webhook mode is planned for a later phase; use polling mode now."
            )

        if self.config.dm_policy == "allowlist" and not self.config.allow_from:
            logger.warning(
                "channels.telegram.blocking_all_dms",
                reason="dm_policy=allowlist and allow_from is empty",
            )

        offset = await self.db.channel_offset_get("telegram")
        self._offset = offset if offset is not None else 0

        await self.db.channel_dedupe_prune("telegram", keep_last=5000)

        self._running = True
        self._stop_event.clear()
        self._set_status(running=True)
        self._task = asyncio.create_task(self._poll_loop(), name="channel-telegram-poll")

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._set_status(running=False)

    async def _poll_loop(self) -> None:
        api_base = f"https://api.telegram.org/bot{self.config.bot_token.strip()}"
        timeout = httpx.Timeout(
            connect=10.0,
            read=self.config.poll_timeout_s + 10.0,
            write=10.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            await self._load_bot_identity(client, api_base)

            while not self._stop_event.is_set():
                try:
                    updates = await self._get_updates(client, api_base)
                    for update in updates:
                        await self._process_update(client, api_base, update)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("channels.telegram.poll_error", error=str(e))
                    self._set_status(last_error=str(e))
                    await asyncio.sleep(self.config.retry_delay_s)

    async def _load_bot_identity(self, client: httpx.AsyncClient, api_base: str) -> None:
        resp = await client.get(f"{api_base}/getMe")
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("result") or {}
        username = result.get("username")
        if isinstance(username, str) and username.strip():
            self._bot_username = username.strip().lower()

    async def _get_updates(self, client: httpx.AsyncClient, api_base: str) -> list[dict[str, Any]]:
        resp = await client.get(
            f"{api_base}/getUpdates",
            params={
                "offset": self._offset,
                "timeout": self.config.poll_timeout_s,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {payload}")

        result = payload.get("result", [])
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]

    async def _process_update(
        self,
        client: httpx.AsyncClient,
        api_base: str,
        update: dict[str, Any],
    ) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            dedupe_key = f"u:{update_id}"
            if await self.db.channel_dedupe_exists("telegram", dedupe_key):
                self._offset = max(self._offset, update_id + 1)
                return

        message = update.get("message")
        if not isinstance(message, dict):
            if isinstance(update_id, int):
                self._offset = max(self._offset, update_id + 1)
                await self.db.channel_offset_set("telegram", self._offset)
                await self.db.channel_dedupe_add("telegram", f"u:{update_id}")
            return

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return
        chat_type = str(chat.get("type") or "private")
        text = (message.get("text") or "").strip()
        if not text:
            if isinstance(update_id, int):
                self._offset = max(self._offset, update_id + 1)
                await self.db.channel_offset_set("telegram", self._offset)
                await self.db.channel_dedupe_add("telegram", f"u:{update_id}")
            return

        sender = message.get("from") or {}
        sender_id = str(sender.get("id") or "")

        if not self._allowed_sender(sender_id=sender_id, chat_type=chat_type):
            logger.info(
                "channels.telegram.message_blocked",
                reason="sender_not_allowed",
                chat_type=chat_type,
                sender_id=sender_id,
            )
            if isinstance(update_id, int):
                self._offset = max(self._offset, update_id + 1)
                await self.db.channel_offset_set("telegram", self._offset)
                await self.db.channel_dedupe_add("telegram", f"u:{update_id}")
            return

        if chat_type != "private":
            if not self.config.groups_enabled:
                logger.info(
                    "channels.telegram.message_blocked",
                    reason="groups_disabled",
                    chat_type=chat_type,
                )
                return
            if self.config.require_mention and not self._has_bot_mention(text):
                logger.info(
                    "channels.telegram.message_blocked",
                    reason="mention_required",
                    chat_type=chat_type,
                )
                return

        thread_id = message.get("message_thread_id")
        session_key = self._session_key(chat_id=chat_id, chat_type=chat_type, thread_id=thread_id)

        inbound = ChannelInboundEvent(
            channel="telegram",
            session_key=session_key,
            sender_id=sender_id,
            peer_id=str(chat_id),
            thread_id=str(thread_id) if thread_id is not None else None,
            message_id=(
                str(message.get("message_id"))
                if message.get("message_id") is not None
                else None
            ),
            update_id=str(update_id) if update_id is not None else None,
            text=text,
            model=self.config.model,
            agent_mode=self.config.agent_mode,
        )

        self._set_status(last_inbound_at=self._now_iso())
        reply = await self.inbound_handler(inbound)
        await self._send_reply(client, api_base, chat_id, reply, thread_id)
        self._set_status(last_outbound_at=self._now_iso())

        if isinstance(update_id, int):
            self._offset = max(self._offset, update_id + 1)
            await self.db.channel_offset_set("telegram", self._offset)
            await self.db.channel_dedupe_add("telegram", f"u:{update_id}")

    async def _send_reply(
        self,
        client: httpx.AsyncClient,
        api_base: str,
        chat_id: int | str,
        text: str,
        thread_id: Any,
    ) -> None:
        for chunk in self._chunk_text(text):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if thread_id is not None:
                payload["message_thread_id"] = thread_id

            resp = await client.post(f"{api_base}/sendMessage", json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "channels.telegram.send_failed",
                    status_code=resp.status_code,
                    body=resp.text[:300],
                )

    def _allowed_sender(self, *, sender_id: str, chat_type: str) -> bool:
        if chat_type == "private":
            if self.config.dm_policy == "disabled":
                return False
            if self.config.dm_policy == "open":
                return True
        if not self.config.allow_from:
            return self.config.dm_policy == "open" and chat_type == "private"

        normalized = {item.strip().lower() for item in self.config.allow_from if item.strip()}
        sender = sender_id.strip().lower()
        return sender in normalized

    def _has_bot_mention(self, text: str) -> bool:
        if not self._bot_username:
            return False
        return f"@{self._bot_username}" in text.lower()

    def _session_key(self, *, chat_id: Any, chat_type: str, thread_id: Any) -> str:
        if chat_type == "private":
            return f"telegram:{chat_id}"
        if thread_id is not None:
            return f"telegram:group:{chat_id}:thread:{thread_id}"
        return f"telegram:group:{chat_id}"

    def _chunk_text(self, text: str) -> list[str]:
        content = (text or "").strip() or "(empty response)"
        if len(content) <= self.config.max_message_chars:
            return [content]

        chunks: list[str] = []
        start = 0
        while start < len(content):
            end = min(start + self.config.max_message_chars, len(content))
            chunks.append(content[start:end])
            start = end
        return chunks

    def _set_status(
        self,
        *,
        running: bool | None = None,
        last_error: str | None = None,
        last_inbound_at: str | None = None,
        last_outbound_at: str | None = None,
    ) -> None:
        if running is not None:
            self._status.running = running
        if last_error is not None:
            self._status.last_error = last_error
        if last_inbound_at is not None:
            self._status.last_inbound_at = last_inbound_at
        if last_outbound_at is not None:
            self._status.last_outbound_at = last_outbound_at

        asyncio.create_task(
            self.db.channel_runtime_upsert(
                channel="telegram",
                account_id="default",
                mode=self.config.mode,
                running=self._status.running,
                last_error=self._status.last_error,
                last_inbound_at=self._status.last_inbound_at,
                last_outbound_at=self._status.last_outbound_at,
            )
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
