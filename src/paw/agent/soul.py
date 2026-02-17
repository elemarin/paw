"""Soul loader — reads soul.md and injects it as the base system prompt."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from paw.agent.memory import MemoryTool

logger = structlog.get_logger()

_DEFAULT_SOUL = (
    "You are PAW, a personal agent workspace. You are a helpful, direct, and capable AI "
    "assistant that can execute shell commands, manage files, and build plugins to extend "
    "your own capabilities. Be concise and action-oriented."
)

_MEMORY_SYSTEM_INSTRUCTIONS = """
===========================
MEMORY SYSTEM (STAGE 1)
===========================

You have a persistent key-value memory that survives across conversations.
Use the "memory" TOOL (via function calling) to store and retrieve information.

Available memory actions (pass these as the "action" argument):
- remember: Store a key-value pair. Requires "key" and "value".
- recall:   Retrieve a stored value by key.
- list:     Show all stored memory keys and values.
- forget:   Delete a stored memory by key.
- Legacy alias: {"action": "write_memory", "key": "...", "value": "..."} maps to remember.

WHEN TO USE MEMORY:
- The user says "remember this" or similar
- The user gives a name, preference, identity, or stable fact
- A decision or commitment is made that should persist
- You want to store something that will matter in future conversations

IMPORTANT:
- Always use the memory tool via function calling. Never output raw JSON.
- When you have stored memories in context below, USE them to answer questions.
- If the user asks "what's my name?" and you see it in memory, answer directly.
- Proactively use memory when it's relevant to the conversation.

===========================
BEHAVIOR RULES
===========================

- Keep user-facing answers clean and helpful.
- Use memory when relevant — answer from memory before asking the user.
- Store to memory proactively when the user shares persistent information.
- If unsure, think step-by-step until you reach a decision."""


def load_soul(soul_path: str | Path) -> str:
    """Load soul.md from the given path. Falls back to a minimal default."""
    path = Path(soul_path)
    try:
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                logger.info("soul.loaded", path=str(path), length=len(content))
                return content
        logger.warning("soul.not_found", path=str(path), using="default")
    except Exception as e:
        logger.error("soul.load_error", path=str(path), error=str(e))

    return _DEFAULT_SOUL


def load_markdown_memory(memory_dir: str | Path = "memory", now: datetime | None = None) -> str:
    """Load MEMORY.md + today/yesterday/day-before markdown logs."""
    base_dir = Path(memory_dir)
    current = now or datetime.now(UTC)
    dates = [(current - timedelta(days=offset)).date().isoformat() for offset in range(3)]
    files = [base_dir / "MEMORY.md", *[base_dir / f"{day}.md" for day in dates]]

    logger.info("memory.load.start", directory=str(base_dir), files=len(files))

    parts: list[str] = []
    for path in files:
        if not path.exists():
            logger.info("memory.file.missing", path=str(path))
            continue

        content = path.read_text(encoding="utf-8").strip()
        if not content:
            logger.info("memory.file.empty", path=str(path))
            continue

        logger.info("memory.file.loaded", path=str(path), length=len(content))
        parts.append(f"# {path.name}\n{content}")

    memory_context = "\n\n".join(parts)
    logger.info("memory.load.complete", loaded_files=len(parts), length=len(memory_context))
    return memory_context


def format_db_memories(memory_tool: MemoryTool) -> str:
    """Format in-memory key-value store as text for the system prompt."""
    if not memory_tool._store:
        return ""
    lines = [f"- {k}: {v}" for k, v in memory_tool._store.items()]
    return "Stored memories:\n" + "\n".join(lines)


def get_system_prompt(
    soul_path: str | Path,
    extra_context: str | None = None,
    memory_dir: str | Path = "memory",
    memory_tool: MemoryTool | None = None,
) -> str:
    """Build the full system prompt from soul.md + memory instructions + stored memories."""
    soul = load_soul(soul_path)
    md_memory = load_markdown_memory(memory_dir)

    parts = [
        soul,
        _MEMORY_SYSTEM_INSTRUCTIONS,
    ]

    # Inject stored DB memories so the LLM can see them
    db_memories = format_db_memories(memory_tool) if memory_tool else ""
    all_memory = "\n\n".join(filter(None, [md_memory, db_memories]))
    if all_memory:
        parts.append(f"\n<MEMORY>\n{all_memory}\n</MEMORY>")

    if extra_context:
        parts.append(f"\n\n---\n\n{extra_context}")

    return "\n".join(parts)
