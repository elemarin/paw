"""Tool base class and registry — the foundation of PAW's capabilities."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class Tool(ABC):
    """Base class for all PAW tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result."""
        ...

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Central registry for all tools — built-in, plugins, MCP, etc."""

    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        if tool.name in self.tools:
            logger.warning("tool.duplicate", name=tool.name, action="replacing")
        self.tools[tool.name] = tool
        logger.info("tool.registered", name=tool.name)

    def unregister(self, name: str) -> None:
        """Remove a tool."""
        if name in self.tools:
            del self.tools[name]
            logger.info("tool.unregistered", name=name)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self.tools.get(name)

    async def execute(self, name: str, arguments: str | dict) -> str:
        """Execute a tool by name with the given arguments."""
        tool = self.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'. Available tools: {list(self.tools.keys())}"

        # Parse arguments
        if isinstance(arguments, str):
            try:
                kwargs = json.loads(arguments)
            except json.JSONDecodeError:
                return f"Error: Invalid JSON arguments: {arguments}"
        else:
            kwargs = arguments

        try:
            result = await tool.execute(**kwargs)
            logger.info("tool.executed", name=name, result_length=len(result))
            return result
        except Exception as e:
            error_msg = f"Error executing tool '{name}': {type(e).__name__}: {e}"
            logger.error("tool.error", name=name, error=str(e))
            return error_msg

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Get all tools in OpenAI function calling format."""
        return [tool.to_openai_tool() for tool in self.tools.values()]

    def list_tools(self) -> list[dict[str, str]]:
        """List all tools with names and descriptions."""
        return [
            {"name": t.name, "description": t.description}
            for t in self.tools.values()
        ]
