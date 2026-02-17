"""Chat completion endpoint — OpenAI-compatible + agent mode."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from paw.api.middleware.auth import verify_api_key
from paw.agent.soul import get_system_prompt

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
    gateway = request.app.state.gateway
    agent = request.app.state.agent
    conversations = request.app.state.conversations
    memory_tool = request.app.state.memory_tool
    selected_model = _resolve_model(
        config=config,
        requested_model=body.model,
        smart_mode=body.smart_mode,
    )

    # Get or create conversation
    conv_id = body.conversation_id or str(uuid.uuid4())
    conversation = conversations.get_or_create(conv_id)

    # Refresh the system message with current DB memories
    fresh_soul = get_system_prompt(config.soul_path, memory_tool=memory_tool)
    if conversation.messages and conversation.messages[0].role == "system":
        conversation.messages[0].content = fresh_soul
    elif not conversation.messages:
        conversation.add_message("system", fresh_soul)

    # Add user message(s)
    for msg in body.messages:
        conversation.add_message(msg.role, msg.content or "")

    if body.agent_mode:
        # Run the full agent loop (think → act → observe → repeat)
        result = await agent.run(
            conversation=conversation,
            model=selected_model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )

        # Persist conversation to DB
        await conversations.save_conversation(conversation)

        return ChatResponse(
            id=f"paw-{uuid.uuid4().hex[:8]}",
            model=selected_model,
            conversation_id=conv_id,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.response},
                    "finish_reason": result.finish_reason,
                }
            ],
            usage=result.usage,
            tool_calls_made=result.tool_calls_made,
        )
    else:
        # Simple proxy mode — no agent loop, just LLM
        messages = [{"role": m.role, "content": m.content} for m in conversation.messages]
        response = await gateway.completion(
            messages=messages,
            model=selected_model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )

        content = response.choices[0].message.content
        conversation.add_message("assistant", content)

        # Persist conversation to DB
        await conversations.save_conversation(conversation)

        return ChatResponse(
            id=f"paw-{uuid.uuid4().hex[:8]}",
            model=selected_model,
            conversation_id=conv_id,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": response.choices[0].finish_reason,
                }
            ],
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else None,
            tool_calls_made=0,
        )
