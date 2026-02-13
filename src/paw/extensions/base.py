"""Plugin base class — the contract for PAW extensions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from paw.agent.tools import Tool, ToolRegistry
    from paw.db.engine import Database


class PawPlugin(ABC):
    """Base class for all PAW plugins.

    To create a plugin:
    1. Create a directory in /home/paw/plugins/<name>/
    2. Add a plugin.yaml with metadata
    3. Add an __init__.py exporting a class that inherits PawPlugin
    4. Implement on_load() to register tools
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """What this plugin does."""
        ...

    @property
    def version(self) -> str:
        """Plugin version."""
        return "0.1.0"

    async def on_load(self, registry: ToolRegistry, db: Database | None = None) -> list[Tool]:
        """Called when the plugin is loaded. Register tools here.

        Args:
            registry: The tool registry to register tools with.
            db: Optional database for plugin state persistence.

        Returns:
            List of tools registered by this plugin.
        """
        return []

    async def on_unload(self) -> None:
        """Called when the plugin is unloaded. Clean up resources."""
        pass

    def __repr__(self) -> str:
        return f"<Plugin: {self.name} v{self.version}>"
