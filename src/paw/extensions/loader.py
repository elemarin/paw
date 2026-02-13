"""Plugin loader — discovers and loads plugins from the plugins directory."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import structlog
import yaml

from paw.agent.tools import ToolRegistry
from paw.extensions.base import PawPlugin

logger = structlog.get_logger()


async def load_plugins(
    plugins_dir: str,
    registry: ToolRegistry,
    db: Any = None,
) -> list[str]:
    """Discover and load all plugins from the plugins directory.

    Each plugin is a directory with:
    - plugin.yaml (metadata: name, description, version, entry_point)
    - __init__.py or entry_point.py with a PawPlugin subclass

    Returns list of loaded plugin names.
    """
    plugins_path = Path(plugins_dir)
    loaded: list[str] = []

    if not plugins_path.exists():
        logger.info("plugins.dir_not_found", path=plugins_dir)
        plugins_path.mkdir(parents=True, exist_ok=True)
        return loaded

    for plugin_dir in sorted(plugins_path.iterdir()):
        if not plugin_dir.is_dir():
            continue
        if plugin_dir.name.startswith((".", "_")):
            continue

        try:
            plugin = await _load_single_plugin(plugin_dir, registry, db)
            if plugin:
                loaded.append(plugin.name)
                logger.info("plugins.loaded", name=plugin.name, version=plugin.version)
        except Exception as e:
            logger.error("plugins.load_failed", dir=plugin_dir.name, error=str(e))

    return loaded


async def _load_single_plugin(
    plugin_dir: Path,
    registry: ToolRegistry,
    db: Any,
) -> PawPlugin | None:
    """Load a single plugin from a directory."""

    # Load metadata
    meta_path = plugin_dir / "plugin.yaml"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = yaml.safe_load(f) or {}

    entry_point = meta.get("entry_point", "__init__")

    # Determine module file
    if entry_point == "__init__":
        module_file = plugin_dir / "__init__.py"
    else:
        module_file = plugin_dir / f"{entry_point}.py"

    if not module_file.exists():
        logger.warning("plugins.no_entry", dir=plugin_dir.name, expected=str(module_file))
        return None

    # Import the module
    module_name = f"paw_plugin_{plugin_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # Find the PawPlugin subclass
    plugin_class = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, PawPlugin)
            and attr is not PawPlugin
        ):
            plugin_class = attr
            break

    if not plugin_class:
        logger.warning("plugins.no_class", dir=plugin_dir.name)
        return None

    plugin = plugin_class()

    tools = await plugin.on_load(registry, db)

    if tools:
        for tool in tools:
            registry.register(tool)

    return plugin
