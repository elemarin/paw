"""Hello World — example PAW plugin.

Demonstrates how to create a plugin that registers a tool.
"""

from __future__ import annotations

from typing import Any

from paw.agent.tools import Tool, ToolRegistry
from paw.extensions.base import PawPlugin


class HelloTool(Tool):
    """A simple greeting tool."""

    @property
    def name(self) -> str:
        return "hello"

    @property
    def description(self) -> str:
        return "Say hello! A simple example tool to demonstrate the plugin system."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Who to greet. Default: World",
                },
            },
            "required": [],
        }

    async def execute(self, name: str = "World") -> str:
        return f"🐾 Hello, {name}! PAW is running and plugins are working!"


class HelloWorldPlugin(PawPlugin):
    """Example plugin that registers the 'hello' tool."""

    @property
    def name(self) -> str:
        return "hello_world"

    @property
    def description(self) -> str:
        return "Example plugin that says hello"

    async def on_load(self, registry: ToolRegistry, db=None) -> list[Tool]:
        tool = HelloTool()
        return [tool]
