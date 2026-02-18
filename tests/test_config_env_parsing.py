from __future__ import annotations

from paw.config import PawConfig


def test_agent_tool_models_accepts_empty_env(monkeypatch) -> None:
    monkeypatch.setenv("PAW_AGENT__TOOL_MODELS", "")

    config = PawConfig.load()

    assert config.agent.tool_models == {}


def test_complex_env_fields_accept_plain_strings(monkeypatch) -> None:
    monkeypatch.setenv("PAW_AGENT__TOOL_MODELS", "shell=openai/gpt-4o-mini")
    monkeypatch.setenv("PAW_TELEGRAM_ALLOW_FROM", "123,456")
    monkeypatch.setenv("PAW_HOOKS_MODEL_CHANGED_TARGETS", "telegram,log")

    config = PawConfig.load()

    assert config.agent.tool_models == {"shell": "openai/gpt-4o-mini"}
    assert config.channels.telegram.allow_from == ["123", "456"]
    assert config.hooks.model_changed_targets == ["telegram", "log"]
