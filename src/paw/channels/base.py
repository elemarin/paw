"""Core channel abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChannelInboundEvent:
    """Normalized inbound event from a channel provider."""

    channel: str
    session_key: str
    sender_id: str
    peer_id: str
    text: str
    message_id: str | None = None
    update_id: str | None = None
    thread_id: str | None = None
    model: str | None = None
    agent_mode: bool = True


@dataclass
class ChannelStatus:
    """Runtime status snapshot for a channel provider."""

    channel: str
    mode: str
    running: bool
    enabled: bool
    last_error: str | None = None
    last_inbound_at: str | None = None
    last_outbound_at: str | None = None


class ChannelProvider(ABC):
    """Interface implemented by all channel providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def enabled(self) -> bool:
        ...

    @abstractmethod
    async def start(self) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    def status(self) -> ChannelStatus:
        ...

    @abstractmethod
    async def send_system_message(self, text: str) -> bool:
        """Send an outbound runtime/system message using provider default routing."""
        ...
