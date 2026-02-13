"""File tool — read, write, list, and search files in PAW's workspace."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from paw.agent.tools import Tool
from paw.config import PawConfig

logger = structlog.get_logger()


class FileTool(Tool):
    """Read, write, list, and search files."""

    def __init__(self, config: PawConfig) -> None:
        self._config = config
        self._writable_dirs = [
            config.workspace_dir,
            config.plugins_dir,
            config.data_dir,
            "/tmp",
        ]

    @property
    def name(self) -> str:
        return "files"

    @property
    def description(self) -> str:
        return (
            "Manage files in PAW's environment. Actions: "
            "'read' (read a file), 'write' (create/overwrite a file), "
            "'append' (append to a file), 'list' (list directory contents), "
            "'search' (search for files by name pattern), 'exists' (check if path exists), "
            "'delete' (delete a file)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "append", "list", "search", "exists", "delete"],
                    "description": "The file action to perform.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for 'write' and 'append').",
                },
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (for 'search', e.g. '*.py').",
                },
            },
            "required": ["action", "path"],
        }

    def _check_writable(self, path: str) -> str | None:
        """Check if a path is in a writable directory. Returns error message or None."""
        resolved = str(Path(path).resolve())
        for allowed in self._writable_dirs:
            if resolved.startswith(str(Path(allowed).resolve())):
                return None
        return f"Error: Cannot write to '{path}'. Writable dirs: {self._writable_dirs}"

    async def execute(
        self,
        action: str,
        path: str,
        content: str = "",
        pattern: str = "*",
    ) -> str:
        """Execute a file operation."""
        p = Path(path)

        try:
            if action == "read":
                if not p.exists():
                    return f"Error: File not found: {path}"
                if not p.is_file():
                    return f"Error: Not a file: {path}"
                text = p.read_text(encoding="utf-8", errors="replace")
                if len(text) > 50_000:
                    text = text[:50_000] + f"\n... (truncated, {len(text)} chars total)"
                return text

            elif action == "write":
                error = self._check_writable(path)
                if error:
                    return error
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                logger.info("files.write", path=path, size=len(content))
                return f"Written {len(content)} chars to {path}"

            elif action == "append":
                error = self._check_writable(path)
                if error:
                    return error
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as f:
                    f.write(content)
                logger.info("files.append", path=path, size=len(content))
                return f"Appended {len(content)} chars to {path}"

            elif action == "list":
                if not p.exists():
                    return f"Error: Directory not found: {path}"
                if not p.is_dir():
                    return f"Error: Not a directory: {path}"
                entries = sorted(p.iterdir())
                lines = []
                for entry in entries[:200]:  # Limit
                    kind = "dir" if entry.is_dir() else "file"
                    size = entry.stat().st_size if entry.is_file() else 0
                    lines.append(f"  [{kind}] {entry.name}" + (f" ({size} bytes)" if kind == "file" else ""))
                result = f"Contents of {path} ({len(entries)} items):\n" + "\n".join(lines)
                return result

            elif action == "search":
                if not p.exists():
                    return f"Error: Directory not found: {path}"
                matches = list(p.rglob(pattern))[:100]
                if not matches:
                    return f"No files matching '{pattern}' in {path}"
                lines = [f"  {m}" for m in matches]
                return f"Found {len(matches)} matches:\n" + "\n".join(lines)

            elif action == "exists":
                if p.exists():
                    kind = "directory" if p.is_dir() else "file"
                    return f"Yes: {path} exists ({kind})"
                return f"No: {path} does not exist"

            elif action == "delete":
                error = self._check_writable(path)
                if error:
                    return error
                if not p.exists():
                    return f"Error: File not found: {path}"
                if p.is_dir():
                    return f"Error: Cannot delete directory with file tool. Use shell: rm -r {path}"
                p.unlink()
                logger.info("files.delete", path=path)
                return f"Deleted: {path}"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
