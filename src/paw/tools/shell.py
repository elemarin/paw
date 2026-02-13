"""Shell tool — execute commands in PAW's Linux environment."""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

import structlog

from paw.agent.tools import Tool
from paw.config import ShellConfig

logger = structlog.get_logger()


class ShellTool(Tool):
    """Execute shell commands inside PAW's container."""

    def __init__(self, config: ShellConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command in PAW's Linux environment. "
            "You can install packages (apt, pip), run scripts, manage files, "
            "use git, and more. Use this for any OS-level operation."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory (default: /home/paw/workspace).",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, working_dir: str = "/home/paw/workspace") -> str:
        """Execute a shell command."""
        if not self._config.enabled:
            return "Error: Shell tool is disabled."

        # Safety: check blocked commands
        for blocked in self._config.blocked_commands:
            if blocked in command:
                return f"Error: Command blocked — '{blocked}' is not allowed."

        # Safety: check approval patterns (for now, warn but allow)
        for pattern in self._config.approval_patterns:
            if pattern in command:
                logger.warning("shell.approval_needed", command=command, pattern=pattern)
                # In future: queue for approval. For MVP: warn and execute.

        logger.info("shell.execute", command=command, cwd=working_dir)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._config.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {self._config.timeout}s."

            exit_code = process.returncode
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            # Build result
            parts = []
            if stdout_str:
                parts.append(f"stdout:\n{stdout_str}")
            if stderr_str:
                parts.append(f"stderr:\n{stderr_str}")
            parts.append(f"exit_code: {exit_code}")

            result = "\n".join(parts)

            # Truncate very long output
            if len(result) > 10_000:
                result = result[:10_000] + f"\n... (truncated, {len(result)} chars total)"

            logger.info("shell.result", exit_code=exit_code, output_length=len(result))
            return result

        except Exception as e:
            error_msg = f"Error running command: {type(e).__name__}: {e}"
            logger.error("shell.error", command=command, error=str(e))
            return error_msg
