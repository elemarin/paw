"""LiteLLM gateway — async wrapper for multi-provider LLM access."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

import litellm
import structlog

from paw.config import LLMConfig

logger = structlog.get_logger()

# Suppress litellm's noisy logging
litellm.suppress_debug_info = True
litellm.drop_params = True


class LLMGateway:
    """Async wrapper around LiteLLM for multi-provider model access."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.request_count = 0

    async def completion(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        stream: bool = False,
    ) -> Any:
        """Send a completion request through LiteLLM."""
        model = model or self.config.model
        is_openai_model = model.startswith("openai/")
        temperature = temperature if temperature is not None else self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if is_openai_model:
            kwargs["drop_params"] = True

        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            kwargs["api_base"] = self.config.api_base
        if tools:
            kwargs["tools"] = tools
        if tool_choice and not is_openai_model:
            kwargs["tool_choice"] = tool_choice

        start = time.monotonic()
        self.request_count += 1
        request_id = self.request_count

        logger.info(
            "llm.request",
            request_id=request_id,
            model=model,
            message_count=len(messages),
            has_tools=bool(tools),
            stream=stream,
        )

        try:
            response = await litellm.acompletion(**kwargs)

            if not stream:
                # Track usage
                usage = getattr(response, "usage", None)
                if usage:
                    tokens = getattr(usage, "total_tokens", 0)
                    self.total_tokens_used += tokens
                    try:
                        cost = litellm.completion_cost(completion_response=response)
                    except Exception:
                        cost = 0.0  # Local models (Ollama) have no cost
                    self.total_cost += cost
                    logger.info(
                        "llm.response",
                        request_id=request_id,
                        tokens=tokens,
                        cost=f"${cost:.6f}",
                        duration=f"{time.monotonic() - start:.2f}s",
                    )

            return response

        except Exception as e:
            logger.error("llm.error", request_id=request_id, error=str(e), model=model)

            # Try fallback models
            for fallback in self.config.fallback_models:
                logger.info("llm.fallback", fallback_model=fallback)
                try:
                    kwargs["model"] = fallback
                    response = await litellm.acompletion(**kwargs)
                    logger.info("llm.fallback.success", model=fallback)
                    return response
                except Exception as fallback_err:
                    logger.error("llm.fallback.error", model=fallback, error=str(fallback_err))

            raise

    async def stream_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Any]:
        """Stream a completion response."""
        response = await self.completion(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=True,
        )
        async for chunk in response:
            yield chunk

    @property
    def stats(self) -> dict[str, Any]:
        """Return usage statistics."""
        return {
            "total_tokens": self.total_tokens_used,
            "total_cost": f"${self.total_cost:.6f}",
            "request_count": self.request_count,
            "model": self.config.model,
        }
