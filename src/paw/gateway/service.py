"""Unified event gateway for PAW runtime."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import structlog

from paw.agent.soul import get_system_prompt
from paw.gateway.models import InboundEvent, ProcessedEventResult

logger = structlog.get_logger()


class PawEventGateway:
    """Single entrypoint for all inbound runtime events."""

    def __init__(
        self,
        *,
        config,
        conversations,
        agent,
        llm_gateway,
        memory_tool,
        channel_router,
        output_router,
    ) -> None:
        self.config = config
        self.conversations = conversations
        self.agent = agent
        self.llm_gateway = llm_gateway
        self.memory_tool = memory_tool
        self.channel_router = channel_router
        self.output_router = output_router

    async def handle_event(self, event: InboundEvent) -> ProcessedEventResult:
        """Handle one normalized inbound event end-to-end."""
        conversation_id = event.conversation_id or await self.channel_router.resolve_conversation_id(
            event.channel,
            event.session_key,
        )
        selected_model = self._resolve_model(event.model, event.smart_mode)
        result = await self.handle_chat_messages(
            conversation_id=conversation_id,
            messages=[("user", event.text)],
            model=selected_model,
            temperature=event.temperature,
            max_tokens=event.max_tokens,
            agent_mode=event.agent_mode,
        )

        if event.output_target:
            await self.output_router.dispatch(
                target=event.output_target,
                text=result.response_text,
                source=f"{event.kind}:{event.channel}",
                metadata={
                    "kind": event.kind,
                    "conversation_id": result.conversation_id,
                    **(event.metadata or {}),
                },
            )
        return result

    async def handle_chat_messages(
        self,
        *,
        conversation_id: str | None,
        messages: Sequence[tuple[str, str]],
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        agent_mode: bool,
    ) -> ProcessedEventResult:
        """Shared chat processing path used by API and channel events."""
        conv_id = conversation_id or str(uuid.uuid4())
        conversation = self.conversations.get_or_create(conv_id)
        self._refresh_system_message(conversation)

        for role, content in messages:
            conversation.add_message(role, content or "")

        selected_model = model or self.config.llm.model

        if agent_mode:
            run_result = await self.agent.run(
                conversation=conversation,
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            await self.conversations.save_conversation(conversation)
            return ProcessedEventResult(
                conversation_id=conv_id,
                response_text=run_result.response,
                model=selected_model,
                finish_reason=run_result.finish_reason,
                usage=run_result.usage,
                tool_calls_made=run_result.tool_calls_made,
            )

        payload = [{"role": msg.role, "content": msg.content} for msg in conversation.messages]
        response = await self.llm_gateway.completion(
            messages=payload,
            model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        conversation.add_message("assistant", content)
        await self.conversations.save_conversation(conversation)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return ProcessedEventResult(
            conversation_id=conv_id,
            response_text=content,
            model=selected_model,
            finish_reason=response.choices[0].finish_reason or "stop",
            usage=usage,
            tool_calls_made=0,
        )

    async def emit_hook(self, *, name: str, payload: dict) -> None:
        """Dispatch configured internal hook notifications."""
        hook_cfg = self.config.hooks
        if name != "model_changed":
            return

        text = (
            "PAW runtime model update\n"
            f"regular_model={payload.get('regular_model', '')}\n"
            f"smart_model={payload.get('smart_model', '')}"
        )

        for target in hook_cfg.model_changed_targets:
            await self.output_router.dispatch(
                target=target,
                text=text,
                source="hook:model_changed",
                metadata=payload,
            )
        for url in hook_cfg.model_changed_webhooks:
            await self.output_router.dispatch(
                target=f"webhook:{url}",
                text=text,
                source="hook:model_changed",
                metadata=payload,
            )

        if hook_cfg.model_changed_targets or hook_cfg.model_changed_webhooks:
            logger.info(
                "gateway.hook.dispatched",
                hook=name,
                targets=len(hook_cfg.model_changed_targets),
                webhooks=len(hook_cfg.model_changed_webhooks),
            )

    def _resolve_model(self, requested_model: str | None, smart_mode: bool) -> str:
        if requested_model:
            return requested_model
        return self.config.llm.smart_model if smart_mode else self.config.llm.model

    def _refresh_system_message(self, conversation) -> None:
        soul = get_system_prompt(self.config.soul_path, memory_tool=self.memory_tool)
        if conversation.messages and conversation.messages[0].role == "system":
            conversation.messages[0].content = soul
        elif not conversation.messages:
            conversation.add_message("system", soul)
