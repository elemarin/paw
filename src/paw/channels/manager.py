"""Channel runtime manager."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog

from paw.channels.base import ChannelInboundEvent, ChannelProvider, ChannelStatus
from paw.channels.telegram.provider import TelegramChannelProvider
from paw.config import PawConfig
from paw.db.engine import Database

logger = structlog.get_logger()

InboundHandler = Callable[[ChannelInboundEvent], Awaitable[str]]
ClearConversationHandler = Callable[[str, str], Awaitable[str | None]]


def _parse_output_target(target: str) -> str | None:
    normalized = (target or "").strip()
    if not normalized:
        return None

    if ":" in normalized:
        channel, _, _destination = normalized.partition(":")
        channel_name = channel.strip().lower()
        logger.info(
            "channels.output_target.qualifier_ignored",
            target=normalized,
            normalized_channel=channel_name,
        )
    else:
        channel_name = normalized.strip().lower()

    if not channel_name:
        return None
    return channel_name


class ChannelRuntimeManager:
    """Owns lifecycle and status of all enabled channel providers."""

    def __init__(
        self,
        config: PawConfig,
        db: Database,
        inbound_handler: InboundHandler,
        clear_conversation_handler: ClearConversationHandler | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.inbound_handler = inbound_handler
        self.clear_conversation_handler = clear_conversation_handler
        self.providers: list[ChannelProvider] = []

        self._initialize_providers()

    def _initialize_providers(self) -> None:
        telegram = TelegramChannelProvider(
            config=self.config.channels.telegram,
            db=self.db,
            inbound_handler=self.inbound_handler,
            clear_conversation_handler=self.clear_conversation_handler,
            default_model=self.config.llm.model,
            default_smart_model=self.config.llm.smart_model,
            heartbeat_interval_minutes=self.config.heartbeat.interval_minutes,
            heartbeat_checklist_path=self.config.heartbeat.checklist_path,
            heartbeat_default_output_target=self.config.heartbeat.default_output_target,
        )
        self.providers.append(telegram)

    async def start(self) -> None:
        """Start all configured providers."""
        for provider in self.providers:
            if not provider.enabled:
                logger.info("channels.provider.disabled", provider=provider.name)
                continue
            try:
                await provider.start()
                logger.info("channels.provider.started", provider=provider.name)
            except Exception as e:
                logger.error("channels.provider.start_failed", provider=provider.name, error=str(e))

    async def stop(self) -> None:
        """Stop all providers."""
        for provider in self.providers:
            try:
                await provider.stop()
                logger.info("channels.provider.stopped", provider=provider.name)
            except Exception as e:
                logger.warning(
                    "channels.provider.stop_failed",
                    provider=provider.name,
                    error=str(e),
                )

    def statuses(self) -> list[ChannelStatus]:
        """Return runtime statuses for all providers."""
        return [provider.status() for provider in self.providers]

    def set_models(self, *, regular_model: str, smart_model: str) -> None:
        """Broadcast runtime model updates to providers that support it."""
        for provider in self.providers:
            updater = getattr(provider, "set_models", None)
            if callable(updater):
                updater(regular_model=regular_model, smart_model=smart_model)

    async def dispatch_output_target(self, target: str, text: str) -> bool:
        """Dispatch channel output target to provider runtime."""
        channel_name = _parse_output_target(target)
        if not channel_name:
            return False

        for provider in self.providers:
            if provider.name.lower() != channel_name:
                continue
            try:
                return await provider.send_system_message(text)
            except Exception as exc:
                logger.warning(
                    "channels.provider.dispatch_failed",
                    provider=provider.name,
                    target=target,
                    error=str(exc),
                )
                return False
        return False
