"""Webhook ingress endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from paw.gateway import InboundEvent

router = APIRouter()


class InboundWebhookRequest(BaseModel):
    event_type: str = Field(default="webhook")
    text: str
    channel: str = Field(default="webhook")
    session_key: str | None = None
    sender_id: str = Field(default="webhook")
    peer_id: str = Field(default="webhook")
    conversation_id: str | None = None
    model: str | None = None
    smart_mode: bool = False
    agent_mode: bool = True
    temperature: float | None = None
    max_tokens: int | None = None
    output_target: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/v1/webhooks/inbound")
async def inbound_webhook(
    request: Request,
    body: InboundWebhookRequest,
    x_paw_webhook_secret: str | None = Header(default=None),
) -> dict:
    config = request.app.state.config
    if not config.webhooks.enabled or not config.webhooks.inbound_enabled:
        raise HTTPException(status_code=404, detail="Webhooks are disabled")

    expected_secret = config.webhooks.inbound_secret.strip()
    if expected_secret and (x_paw_webhook_secret or "").strip() != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    kind = body.event_type.strip().lower() or "webhook"
    if kind not in {"user_message", "heartbeat", "cron", "hook", "webhook"}:
        raise HTTPException(status_code=400, detail="Unsupported event_type")

    session_key = (body.session_key or "").strip() or f"webhook:{kind}:{body.sender_id}"
    result = await request.app.state.event_gateway.handle_event(
        InboundEvent(
            kind=kind,  # type: ignore[arg-type]
            channel=body.channel.strip() or "webhook",
            session_key=session_key,
            sender_id=body.sender_id.strip() or "webhook",
            peer_id=body.peer_id.strip() or "webhook",
            text=body.text,
            conversation_id=body.conversation_id,
            model=body.model,
            smart_mode=body.smart_mode,
            agent_mode=body.agent_mode,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            output_target=body.output_target,
            metadata=body.metadata,
        )
    )

    return {
        "status": "ok",
        "conversation_id": result.conversation_id,
        "model": result.model,
        "response": result.response_text,
        "usage": result.usage,
        "tool_calls_made": result.tool_calls_made,
    }
