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

REGULAR_MODE = "regular"
SMART_MODE = "smart"


class TelegramChannelProvider(ChannelProvider):
    def __init__(
        self,
        *,
        config: TelegramChannelConfig,
        db: Database,
        inbound_handler,
        default_model: str,
        default_smart_model: str,
    ) -> None:
        self.config = config
        self.db = db
        self.inbound_handler = inbound_handler
        self._regular_model = (self.config.model or default_model).strip()
        self._smart_model = (self.config.smart_model or default_smart_model).strip()

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

    def set_models(self, *, regular_model: str, smart_model: str) -> None:
        """Update runtime model selection for this provider."""
        if regular_model.strip():
            self._regular_model = regular_model.strip()
        if smart_model.strip():
            self._smart_model = smart_model.strip()

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

    async def send_system_message(self, text: str) -> bool:
        """Send runtime output to Telegram using default routing."""
        if not self.enabled:
            return False

        chat_id_raw = (self.config.default_chat_id or "").strip()
        if not chat_id_raw:
            chat_id_raw = await self._resolve_default_destination_from_sessions()
        if not chat_id_raw:
            logger.warning("channels.telegram.send_runtime_missing_chat")
            return False

        chat_part, _, thread_part = chat_id_raw.partition("/")
        if not chat_part.strip():
            logger.warning("channels.telegram.send_runtime_invalid_chat")
            return False

        thread_id: str | None = thread_part.strip() or None
        api_base = f"https://api.telegram.org/bot{self.config.bot_token.strip()}"
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)

        sent_any = False
        async with httpx.AsyncClient(timeout=timeout) as client:
            for chunk in self._chunk_text(text):
                payload: dict[str, Any] = {
                    "chat_id": chat_part.strip(),
                    "text": chunk,
                    "disable_web_page_preview": True,
                }
                if thread_id:
                    payload["message_thread_id"] = thread_id
                response = await client.post(f"{api_base}/sendMessage", json=payload)
                if response.status_code >= 400:
                    logger.warning(
                        "channels.telegram.send_runtime_failed",
                        status_code=response.status_code,
                        body=response.text[:300],
                        chat_id=chat_part.strip(),
                    )
                    return False
                sent_any = True
        if sent_any:
            self._set_status(last_outbound_at=self._now_iso())
        return sent_any

    async def _resolve_default_destination_from_sessions(self) -> str:
        session_key = await self.db.channel_session_latest_key("telegram")
        if not session_key:
            return ""

        parts = session_key.split(":")
        if len(parts) >= 2 and parts[0] == "telegram" and parts[1] != "group":
            return parts[1]

        if len(parts) >= 4 and parts[0] == "telegram" and parts[1] == "group":
            chat_id = parts[2]
            if len(parts) >= 5 and parts[3] == "thread":
                thread_id = parts[4]
                if thread_id:
                    return f"{chat_id}/{thread_id}"
            return chat_id
        return ""

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
            await self._register_bot_commands(client, api_base)

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

    async def _register_bot_commands(self, client: httpx.AsyncClient, api_base: str) -> None:
        resp = await client.post(
            f"{api_base}/setMyCommands",
            json={
                "commands": [
                    {"command": "mode", "description": "Toggle mode: regular/smart"},
                    {"command": "status", "description": "Show current model mode"},
                    {"command": "pair", "description": "Pair this chat with a one-time code"},
                ]
            },
        )
        if resp.status_code >= 400:
            logger.warning(
                "channels.telegram.set_commands_failed",
                status_code=resp.status_code,
                body=resp.text[:300],
            )

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
        thread_id = message.get("message_thread_id")
        session_key = self._session_key(chat_id=chat_id, chat_type=chat_type, thread_id=thread_id)

        command = self._parse_command(text)
        if command is not None:
            command_name, command_arg = command
            handled, command_reply = await self._handle_command(
                command_name=command_name,
                command_arg=command_arg,
                session_key=session_key,
                sender_id=sender_id,
                chat_type=chat_type,
            )
            if handled:
                self._set_status(last_inbound_at=self._now_iso())
                await self._send_reply(client, api_base, chat_id, command_reply, thread_id)
                self._set_status(last_outbound_at=self._now_iso())
                if isinstance(update_id, int):
                    self._offset = max(self._offset, update_id + 1)
                    await self.db.channel_offset_set("telegram", self._offset)
                    await self.db.channel_dedupe_add("telegram", f"u:{update_id}")
                return

        if not await self._allowed_sender(sender_id=sender_id, chat_type=chat_type):
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

        if chat_type != "private" and not self.config.groups_enabled:
            logger.info(
                "channels.telegram.message_blocked",
                reason="groups_disabled",
                chat_type=chat_type,
            )
            if isinstance(update_id, int):
                self._offset = max(self._offset, update_id + 1)
                await self.db.channel_offset_set("telegram", self._offset)
                await self.db.channel_dedupe_add("telegram", f"u:{update_id}")
            return

        if (
            chat_type != "private"
            and self.config.require_mention
            and not self._has_bot_mention(text)
        ):
            logger.info(
                "channels.telegram.message_blocked",
                reason="mention_required",
                chat_type=chat_type,
            )
            if isinstance(update_id, int):
                self._offset = max(self._offset, update_id + 1)
                await self.db.channel_offset_set("telegram", self._offset)
                await self.db.channel_dedupe_add("telegram", f"u:{update_id}")
            return

        stored_mode = await self.db.channel_session_mode_get("telegram", session_key)
        selected_mode = stored_mode if stored_mode in {REGULAR_MODE, SMART_MODE} else REGULAR_MODE
        selected_model = self._smart_model if selected_mode == SMART_MODE else self._regular_model

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
            model=selected_model,
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

    async def _allowed_sender(self, *, sender_id: str, chat_type: str) -> bool:
        if self.config.pairing_enabled and await self.db.channel_pairing_is_allowed(
            channel="telegram",
            sender_id=sender_id,
        ):
            return True
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

    def _parse_command(self, text: str) -> tuple[str, str] | None:
        content = (text or "").strip()
        if not content.startswith("/"):
            return None

        first_token, _, remainder = content.partition(" ")
        if len(first_token) <= 1:
            return None

        command_token = first_token[1:]
        command_name, _, mention_name = command_token.partition("@")
        normalized_command = command_name.strip().lower()
        if not normalized_command:
            return None

        if mention_name:
            mention = mention_name.strip().lower()
            if not self._bot_username or mention != self._bot_username:
                return None

        return normalized_command, remainder.strip().lower()

    async def _handle_command(
        self,
        *,
        command_name: str,
        command_arg: str,
        session_key: str,
        sender_id: str,
        chat_type: str,
    ) -> tuple[bool, str]:
        if command_name == "pair":
            if not self.config.pairing_enabled:
                return True, "Pairing is disabled by configuration."
            if chat_type != "private":
                return True, "Pairing works only in private chats."
            code = command_arg.strip().upper()
            if not code:
                return True, "Usage: /pair <code>"
            ok = await self.db.channel_pairing_claim(
                channel="telegram",
                code=code,
                sender_id=sender_id,
            )
            if ok:
                return True, "Pairing complete. You can now chat with PAW."
            return True, "Invalid or expired pairing code."

        if command_name == "status":
            stored_mode = await self.db.channel_session_mode_get("telegram", session_key)
            selected_mode = (
                stored_mode if stored_mode in {REGULAR_MODE, SMART_MODE} else REGULAR_MODE
            )
            selected_model = (
                self._smart_model if selected_mode == SMART_MODE else self._regular_model
            )
            return (
                True,
                (
                    f"Mode: {selected_mode}\n"
                    f"Current model: {selected_model}\n"
                    f"Regular model: {self._regular_model}\n"
                    f"Smart model: {self._smart_model}"
                ),
            )

        if command_name != "mode":
            return False, ""

        stored_mode = await self.db.channel_session_mode_get("telegram", session_key)
        current_mode = stored_mode if stored_mode in {REGULAR_MODE, SMART_MODE} else REGULAR_MODE

        if command_arg in {"", "toggle", "switch"}:
            new_mode = SMART_MODE if current_mode == REGULAR_MODE else REGULAR_MODE
        elif command_arg in {"regular", "normal", "default"}:
            new_mode = REGULAR_MODE
        elif command_arg in {"smart", "think", "thinking"}:
            new_mode = SMART_MODE
        else:
            return True, "Usage: /mode [regular|smart|toggle]"

        await self.db.channel_session_mode_set("telegram", session_key, new_mode)
        active_model = self._smart_model if new_mode == SMART_MODE else self._regular_model
        return True, f"Mode switched to {new_mode}. Active model: {active_model}"

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
