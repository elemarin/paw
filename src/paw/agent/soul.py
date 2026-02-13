"""Soul loader — reads soul.md and injects it as the base system prompt."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

logger = structlog.get_logger()

_DEFAULT_SOUL = """You are PAW, a personal agent workspace. You are a helpful, direct, and capable AI assistant that can execute shell commands, manage files, and build plugins to extend your own capabilities. Be concise and action-oriented."""

_MEMORY_BEHAVIOR = """===========================
MEMORY SYSTEM (STAGE 1)
===========================

All memory is stored as Markdown files in ./memory/

- Long-term memory file:
  ./memory/MEMORY.md

- Daily logs:
  ./memory/YYYY-MM-DD.md

On startup, the host application will load:
- MEMORY.md
- Today’s log
- Yesterday’s log
- The day before yesterday’s log

This memory will be injected into your context as:
<MEMORY>
...content...
</MEMORY>

You must use this memory when relevant.

===========================
WHEN TO WRITE MEMORY
===========================

You write memory when:
- The user explicitly says “remember this”
- The user gives a stable preference, identity, or fact
- A decision or commitment is made
- You detect something that will matter later
- You want to append something to today’s log

To write memory, output ONLY a JSON object:

{
  "action": "write_memory",
  "type": "daily" | "fact",
  "content": "text to append"
}

No explanations inside the JSON.

The host will intercept this JSON and append it to the correct .md file.

===========================
TOOL CALLS
===========================

When you need to call a tool, output:

{
  "action": "tool",
  "name": "tool_name",
  "args": { ... }
}

===========================
BEHAVIOR RULES
===========================

- Keep user-facing answers clean and helpful.
- Use memory when relevant.
- Write memory when appropriate.
- If unsure, think step-by-step until you reach a decision.
- Never include reasoning inside JSON blocks.
- Never break JSON formatting."""


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
            logger.debug("memory.file.missing", path=str(path))
            continue

        content = path.read_text(encoding="utf-8").strip()
        if not content:
            logger.debug("memory.file.empty", path=str(path))
            continue

        logger.info("memory.file.loaded", path=str(path), length=len(content))
        parts.append(f"# {path.name}\n{content}")

    memory_context = "\n\n".join(parts)
    logger.info("memory.load.complete", loaded_files=len(parts), length=len(memory_context))
    return memory_context


def get_system_prompt(
    soul_path: str | Path,
    extra_context: str | None = None,
    memory_dir: str | Path = "memory",
) -> str:
    """Build the full system prompt from soul.md + memory context + optional extra context."""
    soul = load_soul(soul_path)
    memory = load_markdown_memory(memory_dir)
    parts = [
        soul,
        _MEMORY_BEHAVIOR,
        f"<MEMORY>\n{memory}\n</MEMORY>",
    ]

    if extra_context:
        parts.append(f"\n\n---\n\n{extra_context}")

    return "\n".join(parts)
