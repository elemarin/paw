"""Gateway event models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

InboundEventKind = Literal["user_message", "heartbeat", "cron", "hook", "webhook"]


@dataclass
class InboundEvent:
    """Normalized inbound event accepted by the PAW runtime gateway."""

    kind: InboundEventKind
    channel: str
    session_key: str
    sender_id: str
    peer_id: str
    text: str
    conversation_id: str | None = None
    model: str | None = None
    smart_mode: bool = False
    agent_mode: bool = True
    temperature: float | None = None
    max_tokens: int | None = None
    output_target: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedEventResult:
    """Result after an inbound event is processed by PAW."""

    conversation_id: str
    response_text: str
    model: str
    finish_reason: str
    usage: dict[str, int] | None
    tool_calls_made: int
