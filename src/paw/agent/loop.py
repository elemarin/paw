"""ReAct agent loop — PAW's brain.

Implements the Think → Act → Observe cycle:
1. Think: Send conversation + tools to the LLM
2. Act:   If the LLM calls a tool, execute it
3. Observe: Feed the tool result back and loop
4. Stop:  When the LLM responds without tool calls, return the answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from paw.agent.conversation import Conversation
from paw.agent.tools import ToolRegistry
from paw.config import AgentConfig
from paw.llm.gateway import LLMGateway

logger = structlog.get_logger()


@dataclass
class AgentResult:
    """Result of an agent run."""

    response: str
    finish_reason: str = "stop"
    tool_calls_made: int = 0
    iterations: int = 0
    usage: dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    tool_log: list[dict[str, Any]] = field(default_factory=list)


class AgentLoop:
    """ReAct agent loop — Think → Act → Observe → Repeat."""

    def __init__(
        self,
        gateway: LLMGateway,
        registry: ToolRegistry,
        config: AgentConfig,
        soul: str = "",
    ) -> None:
        self.gateway = gateway
        self.registry = registry
        self.config = config
        self.soul = soul

    async def run(
        self,
        conversation: Conversation,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AgentResult:
        """Run the full ReAct loop until the LLM produces a final answer."""
        result = AgentResult(response="")
        tools = self.registry.to_openai_tools() or None

        for iteration in range(1, self.config.max_iterations + 1):
            result.iterations = iteration
            logger.info(
                "agent.iteration",
                iteration=iteration,
                max=self.config.max_iterations,
                messages=len(conversation.messages),
                tool_calls_so_far=result.tool_calls_made,
            )

            # --- THINK: Ask the LLM ---
            messages = conversation.to_messages()
            logger.info(
                "agent.think.start",
                iteration=iteration,
                message_count=len(messages),
            )
            response = await self.gateway.completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice="auto" if tools else None,
            )

            choice = response.choices[0]
            message = choice.message

            # Accumulate usage
            if response.usage:
                result.usage["prompt_tokens"] += response.usage.prompt_tokens
                result.usage["completion_tokens"] += response.usage.completion_tokens
                result.usage["total_tokens"] += response.usage.total_tokens

            # --- CHECK: Does the LLM want to call tools? ---
            tool_calls = getattr(message, "tool_calls", None)
            logger.info(
                "agent.think.result",
                iteration=iteration,
                has_tool_calls=bool(tool_calls),
                finish_reason=choice.finish_reason,
            )

            if not tool_calls:
                # No tool calls — this is the final answer
                content = message.content or ""
                conversation.add_message("assistant", content)
                result.response = content
                result.finish_reason = choice.finish_reason or "stop"
                logger.info(
                    "agent.complete",
                    iterations=iteration,
                    tool_calls=result.tool_calls_made,
                    finish_reason=result.finish_reason,
                )
                return result

            # --- ACT: Execute tool calls ---
            # Add the assistant message with tool_calls to the conversation
            tool_calls_data = []
            for tc in tool_calls:
                tool_calls_data.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

            conversation.add_message(
                "assistant",
                message.content or "",
                tool_calls=tool_calls_data,
            )

            # Execute each tool call
            for tc in tool_calls:
                tool_name = tc.function.name
                tool_args_raw = tc.function.arguments
                tool_call_id = tc.id

                # Safety check: max tool calls
                if result.tool_calls_made >= self.config.max_tool_calls:
                    error_msg = (
                        f"Tool call limit reached ({self.config.max_tool_calls}). "
                        "Please provide a final answer with what you have so far."
                    )
                    conversation.add_tool_result(tool_call_id, error_msg)
                    logger.warning("agent.tool_limit", limit=self.config.max_tool_calls)
                    continue

                result.tool_calls_made += 1

                logger.info(
                    "agent.tool_call",
                    tool=tool_name,
                    call_id=tool_call_id,
                    iteration=iteration,
                    call_number=result.tool_calls_made,
                )

                # --- OBSERVE: Execute the tool and capture the result ---
                tool_result = await self.registry.execute(tool_name, tool_args_raw)

                # Log the tool call
                result.tool_log.append({
                    "tool": tool_name,
                    "arguments": _safe_parse(tool_args_raw),
                    "result_length": len(tool_result),
                    "iteration": iteration,
                })

                # Add tool result to conversation
                conversation.add_tool_result(tool_call_id, tool_result)

                logger.info(
                    "agent.tool_result",
                    tool=tool_name,
                    result_length=len(tool_result),
                )

        # Hit max iterations without a final answer — ask LLM to wrap up
        logger.warning("agent.max_iterations", iterations=self.config.max_iterations)

        conversation.add_message(
            "user",
            (
                "[SYSTEM: You have reached the maximum number of iterations. "
                "Please provide your final answer now with what you have so far.]"
            ),
        )

        # One final call without tools to force a text response
        messages = conversation.to_messages()
        response = await self.gateway.completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=None,
        )

        content = response.choices[0].message.content or ""
        conversation.add_message("assistant", content)
        result.response = content
        result.finish_reason = "max_iterations"

        if response.usage:
            result.usage["prompt_tokens"] += response.usage.prompt_tokens
            result.usage["completion_tokens"] += response.usage.completion_tokens
            result.usage["total_tokens"] += response.usage.total_tokens

        return result


def _safe_parse(raw: str) -> Any:
    """Parse JSON arguments, returning raw string on failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
