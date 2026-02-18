"""Chat completion endpoint — OpenAI-compatible + agent mode."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from paw.api.middleware.auth import verify_api_key
logger = structlog.get_logger()

router = APIRouter()


def _resolve_model(
    *,
    config,
    requested_model: str | None,
    smart_mode: bool,
) -> str:
    if requested_model:
        return requested_model
    return config.llm.smart_model if smart_mode else config.llm.model


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    conversation_id: str | None = Field(default=None, description="Resume an existing conversation")
    agent_mode: bool = Field(default=True, description="Enable agent loop with tool calling")
    smart_mode: bool = Field(
        default=False,
        description="Use configured smart model unless explicit model is provided",
    )


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    conversation_id: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] | None = None
    tool_calls_made: int = 0


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: Request,
    body: ChatRequest,
    _api_key: str | None = Depends(verify_api_key),
) -> ChatResponse | StreamingResponse:
    """Chat completion endpoint. Supports agent mode with tool calling."""
    config = request.app.state.config
    event_gateway = request.app.state.event_gateway
    selected_model = _resolve_model(
        config=config,
        requested_model=body.model,
        smart_mode=body.smart_mode,
    )

    processed = await event_gateway.handle_chat_messages(
        conversation_id=body.conversation_id,
        messages=[(msg.role, msg.content or "") for msg in body.messages],
        model=selected_model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        agent_mode=body.agent_mode,
    )

    return ChatResponse(
        id=f"paw-{uuid.uuid4().hex[:8]}",
        model=processed.model,
        conversation_id=processed.conversation_id,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": processed.response_text},
                "finish_reason": processed.finish_reason,
            }
        ],
        usage=processed.usage,
        tool_calls_made=processed.tool_calls_made,
    )
