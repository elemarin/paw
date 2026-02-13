"""Soul loader — reads soul.md and injects it as the base system prompt."""

from __future__ import annotations

import structlog
from pathlib import Path

logger = structlog.get_logger()

_DEFAULT_SOUL = """You are PAW, a personal agent workspace. You are a helpful, direct, and capable AI assistant that can execute shell commands, manage files, and build plugins to extend your own capabilities. Be concise and action-oriented."""


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


def get_system_prompt(soul_path: str | Path, extra_context: str | None = None) -> str:
    """Build the full system prompt from soul.md + optional extra context."""
    soul = load_soul(soul_path)
    parts = [soul]

    if extra_context:
        parts.append(f"\n\n---\n\n{extra_context}")

    return "\n".join(parts)
