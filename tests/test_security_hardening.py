from __future__ import annotations

from pathlib import Path

import pytest

from paw.config import PawConfig, ShellConfig
from paw.tools.files import FileTool
from paw.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_file_tool_denies_prefix_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    plugins = tmp_path / "plugins"
    data = tmp_path / "data"
    workspace.mkdir()
    plugins.mkdir()
    data.mkdir()
    outside = Path.cwd() / "workspace_evil"

    tool = FileTool(PawConfig(workspace_dir=str(workspace), plugins_dir=str(plugins), data_dir=str(data)))
    result = await tool.execute("write", str(outside / "x.txt"), "test")

    assert "Cannot write to" in result


@pytest.mark.asyncio
async def test_file_tool_denies_read_outside_sandbox(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    plugins = tmp_path / "plugins"
    data = tmp_path / "data"
    workspace.mkdir()
    plugins.mkdir()
    data.mkdir()
    tool = FileTool(PawConfig(workspace_dir=str(workspace), plugins_dir=str(plugins), data_dir=str(data)))
    result = await tool.execute("read", "/etc/hosts")

    assert "outside allowed sandbox dirs" in result


@pytest.mark.asyncio
async def test_shell_tool_denies_unapproved_patterns(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shell = ShellTool(
        ShellConfig(
            writable_dirs=[str(workspace)],
            approval_patterns=["sudo"],
            blocked_commands=[],
        )
    )

    result = await shell.execute("sudo whoami", working_dir=str(workspace))

    assert "requires approval" in result


@pytest.mark.asyncio
async def test_shell_tool_denies_working_dir_outside_sandbox(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    shell = ShellTool(
        ShellConfig(
            writable_dirs=[str(workspace)],
            approval_patterns=[],
            blocked_commands=[],
        )
    )

    result = await shell.execute("echo hi", working_dir=str(outside))

    assert "outside allowed sandbox paths" in result
