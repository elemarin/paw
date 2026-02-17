"""Coder engine — PAW builds itself.

The Coder tool lets PAW create new plugins, features, and improvements
by writing code, creating files, and managing its own codebase.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from paw.agent.tools import Tool

logger = structlog.get_logger()


class CoderTool(Tool):
    """PAW's self-building tool — create plugins, scripts, and features."""

    def __init__(self, workspace_dir: str, plugins_dir: str) -> None:
        self._workspace = Path(workspace_dir)
        self._plugins = Path(plugins_dir)

    @property
    def name(self) -> str:
        return "coder"

    @property
    def description(self) -> str:
        return (
            "Create new plugins, scripts, and features for PAW. Actions: "
            "'create_plugin' (scaffold a new plugin), "
            "'create_script' (create a standalone script), "
            "'propose' (create a self-improvement proposal), "
            "'list_plugins' (show installed plugins), "
            "'read_source' (read PAW's own source code for reference)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_plugin", "create_script", "propose", "list_plugins", "read_source"],
                    "description": "The coder action to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Name of the plugin/script/proposal.",
                },
                "description": {
                    "type": "string",
                    "description": "Description of what to create.",
                },
                "code": {
                    "type": "string",
                    "description": "The code to write (for create_plugin, create_script).",
                },
                "path": {
                    "type": "string",
                    "description": "File path to read (for read_source).",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        name: str = "",
        description: str = "",
        code: str = "",
        path: str = "",
    ) -> str:
        try:
            if action == "create_plugin":
                return await self._create_plugin(name, description, code)
            elif action == "create_script":
                return await self._create_script(name, code)
            elif action == "propose":
                return await self._create_proposal(name, description)
            elif action == "list_plugins":
                return await self._list_plugins()
            elif action == "read_source":
                return await self._read_source(path)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    async def _create_plugin(self, name: str, description: str, code: str) -> str:
        """Scaffold a new plugin."""
        if not name:
            return "Error: Plugin name is required."

        # Sanitize name
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        plugin_dir = self._plugins / safe_name

        if plugin_dir.exists():
            return f"Error: Plugin '{safe_name}' already exists at {plugin_dir}"

        plugin_dir.mkdir(parents=True, exist_ok=True)

        # Write plugin.yaml
        meta = {
            "name": safe_name,
            "description": description or f"Auto-generated plugin: {name}",
            "version": "1.0.0",
            "author": "PAW (self-generated)",
            "entry_point": "__init__",
        }

        import yaml
        (plugin_dir / "plugin.yaml").write_text(
            yaml.dump(meta, default_flow_style=False),
            encoding="utf-8",
        )

        # Write code
        if code:
            (plugin_dir / "__init__.py").write_text(code, encoding="utf-8")
        else:
            # Generate skeleton
            skeleton = f'''"""Plugin: {name}

{description or 'Auto-generated PAW plugin.'}
"""

from __future__ import annotations
from typing import Any
from paw.agent.tools import Tool, ToolRegistry
from paw.extensions.base import PawPlugin


class {_to_class_name(safe_name)}Tool(Tool):
    """TODO: Implement this tool."""

    @property
    def name(self) -> str:
        return "{safe_name}"

    @property
    def description(self) -> str:
        return "{description or name}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {{
            "type": "object",
            "properties": {{}},
            "required": [],
        }}

    async def execute(self, **kwargs: Any) -> str:
        return "TODO: Implement {safe_name}"


class {_to_class_name(safe_name)}Plugin(PawPlugin):
    @property
    def name(self) -> str:
        return "{safe_name}"

    @property
    def description(self) -> str:
        return "{description or name}"

    async def on_load(self, registry: ToolRegistry, db=None) -> list[Tool]:
        return [{_to_class_name(safe_name)}Tool()]
'''
            (plugin_dir / "__init__.py").write_text(skeleton, encoding="utf-8")

        logger.info("coder.plugin_created", name=safe_name, path=str(plugin_dir))
        return (
            f"✅ Plugin '{safe_name}' created at {plugin_dir}/\n"
            f"Files:\n"
            f"  - plugin.yaml\n"
            f"  - __init__.py\n\n"
            f"The plugin will be loaded on next restart, or you can ask me to "
            f"reload plugins."
        )

    async def _create_script(self, name: str, code: str) -> str:
        """Create a standalone script in the workspace."""
        if not name:
            return "Error: Script name is required."
        if not code:
            return "Error: Code is required."

        script_path = self._workspace / name
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(code, encoding="utf-8")

        logger.info("coder.script_created", name=name, path=str(script_path))
        return f"✅ Script created at {script_path}"

    async def _create_proposal(self, name: str, description: str) -> str:
        """Create a self-improvement proposal."""
        if not name or not description:
            return "Error: Both name and description are required for a proposal."

        proposals_dir = self._workspace / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        proposal_path = proposals_dir / f"{safe_name}.md"

        content = f"""# Proposal: {name}

## Description
{description}

## Status
- [ ] Proposed
- [ ] Approved
- [ ] Implemented
- [ ] Tested

## Implementation Plan
_To be filled in by PAW_

## Notes
Auto-generated proposal by PAW's Coder tool.
"""
        proposal_path.write_text(content, encoding="utf-8")

        logger.info("coder.proposal_created", name=safe_name)
        return f"✅ Proposal created at {proposal_path}"

    async def _list_plugins(self) -> str:
        """List all installed plugins."""
        if not self._plugins.exists():
            return "No plugins directory found."

        plugins = []
        for d in sorted(self._plugins.iterdir()):
            if d.is_dir() and not d.name.startswith((".", "_")):
                meta_path = d / "plugin.yaml"
                if meta_path.exists():
                    import yaml
                    meta = yaml.safe_load(meta_path.read_text()) or {}
                    plugins.append(f"  - {meta.get('name', d.name)} v{meta.get('version', '?')}: {meta.get('description', 'No description')}")
                else:
                    plugins.append(f"  - {d.name}: (no plugin.yaml)")

        if not plugins:
            return "No plugins installed."

        return f"Installed plugins ({len(plugins)}):\n" + "\n".join(plugins)

    async def _read_source(self, path: str) -> str:
        """Read PAW's own source code."""
        if not path:
            return "Error: path is required. Try 'src/paw/agent/loop.py' or 'src/paw/tools/shell.py'"

        # Resolve relative to the project root
        candidates = [
            Path(path),
            Path("/home/paw") / path,
            Path("/home/paw/workspace") / path,
        ]

        for p in candidates:
            if p.exists() and p.is_file():
                text = p.read_text(encoding="utf-8", errors="replace")
                if len(text) > 50_000:
                    text = text[:50_000] + "\n... (truncated)"
                return f"Source: {p}\n\n{text}"

        return f"File not found: {path}"


def _to_class_name(snake: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in snake.split("_"))
