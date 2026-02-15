"""PAW configuration — loads from paw.yaml + .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_yaml_config() -> dict[str, Any]:
    """Load paw.yaml from PAW_CONFIG_PATH or default locations."""
    config_path = os.getenv("PAW_CONFIG_PATH")
    search_paths = (
        [Path(config_path)]
        if config_path
        else [
            Path("/home/paw/paw.yaml"),
            Path("/home/paw/data/paw.yaml"),
            Path("paw.yaml"),
        ]
    )
    for path in search_paths:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
    return {}


_yaml_data = _load_yaml_config()


class LLMConfig(BaseSettings):
    """LLM provider configuration."""

    model: str = Field(default="openai/gpt-4o-mini", description="LiteLLM model identifier")
    smart_model: str = Field(
        default="openai/gpt-5.3-codex",
        description="LiteLLM model used when smart mode is enabled",
    )
    api_key: str = Field(default="", description="API key for the LLM provider")
    api_base: str | None = Field(default=None, description="Custom API base URL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
    fallback_models: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(env_prefix="PAW_LLM_")


class AgentConfig(BaseSettings):
    """Agent behavior configuration."""

    max_iterations: int = Field(
        default=10,
        gt=0,
        description="Max ReAct loop iterations per request",
    )
    max_tool_calls: int = Field(default=20, gt=0, description="Max tool calls per request")
    token_budget: int = Field(default=100_000, gt=0, description="Max tokens per request")
    daily_token_budget: int = Field(default=1_000_000, gt=0, description="Daily token limit")

    model_config = SettingsConfigDict(env_prefix="PAW_AGENT_")


class ShellConfig(BaseSettings):
    """Shell tool configuration."""

    enabled: bool = True
    timeout: int = Field(default=30, gt=0, description="Command timeout in seconds")
    blocked_commands: list[str] = Field(
        default_factory=lambda: ["reboot", "shutdown", "init", "mkfs"],
        description="Commands that are always blocked",
    )
    approval_patterns: list[str] = Field(
        default_factory=lambda: ["rm -rf", "dd ", "sudo"],
        description="Command patterns requiring user approval",
    )
    writable_dirs: list[str] = Field(
        default_factory=lambda: [
            "/home/paw/workspace",
            "/home/paw/plugins",
            "/home/paw/data",
            "/tmp",
        ],
    )

    model_config = SettingsConfigDict(env_prefix="PAW_SHELL_")


class TelegramChannelConfig(BaseSettings):
    """Telegram channel configuration."""

    enabled: bool = False
    bot_token: str = Field(default="", description="Telegram bot token")
    mode: Literal["polling", "webhook"] = "polling"

    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_path: str = "/telegram-webhook"
    webhook_host: str = "127.0.0.1"
    webhook_port: int = Field(default=8787, ge=1, le=65535)

    gateway_url: str = "http://127.0.0.1:8000/v1/chat/completions"
    api_key: str | None = None
    model: str | None = None
    smart_model: str | None = None
    agent_mode: bool = True

    dm_policy: Literal["allowlist", "open", "disabled"] = "allowlist"
    allow_from: list[str] = Field(default_factory=list)
    groups_enabled: bool = False
    require_mention: bool = True

    poll_timeout_s: int = Field(default=25, ge=1, le=60)
    retry_delay_s: int = Field(default=3, ge=1, le=30)
    max_message_chars: int = Field(default=3500, ge=200, le=4000)

    @field_validator("allow_from", mode="before")
    @classmethod
    def _parse_allow_from(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                import json

                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    model_config = SettingsConfigDict(env_prefix="PAW_TELEGRAM_")


class ChannelsConfig(BaseModel):
    """Top-level channels configuration."""

    telegram: TelegramChannelConfig = Field(default_factory=TelegramChannelConfig)


class PawConfig(BaseSettings):
    """Root PAW configuration."""

    # Server
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")

    # Auth
    api_key: str = Field(default="", description="API key for authentication. Empty = no auth")

    # Paths
    data_dir: str = Field(default="/home/paw/data")
    plugins_dir: str = Field(default="/home/paw/plugins")
    workspace_dir: str = Field(default="/home/paw/workspace")
    soul_path: str = Field(default="/home/paw/soul.md")
    db_journal_mode: Literal["WAL", "DELETE"] = Field(default="WAL")
    db_busy_timeout_ms: int = Field(default=5000, ge=100, le=120000)

    # Sub-configs
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    shell: ShellConfig = Field(default_factory=ShellConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json", description="'json' or 'console'")

    model_config = SettingsConfigDict(
        env_prefix="PAW_",
        env_nested_delimiter="__",
    )

    @classmethod
    def load(cls) -> PawConfig:
        """Load config from YAML + env vars (env takes precedence)."""
        yaml_cfg = _load_yaml_config()

        # Flatten nested yaml into kwargs
        llm_data = yaml_cfg.pop("llm", {})
        agent_data = yaml_cfg.pop("agent", {})
        shell_data = yaml_cfg.pop("shell", {})
        channels_data = yaml_cfg.pop("channels", {})

        # Only pass YAML sub-configs if they have data;
        # otherwise let pydantic-settings pick up env vars
        kwargs: dict[str, Any] = {**yaml_cfg}
        if llm_data:
            kwargs["llm"] = LLMConfig(**llm_data)
        if agent_data:
            kwargs["agent"] = AgentConfig(**agent_data)
        if shell_data:
            kwargs["shell"] = ShellConfig(**shell_data)
        if channels_data:
            kwargs["channels"] = ChannelsConfig(**channels_data)

        return cls(**kwargs)


# Singleton
_config: PawConfig | None = None


def get_config() -> PawConfig:
    """Get or create the global config."""
    global _config
    if _config is None:
        _config = PawConfig.load()
    return _config
