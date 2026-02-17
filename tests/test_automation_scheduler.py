import asyncio
from datetime import UTC, datetime

from paw.automation.scheduler import _cron_matches
from paw.config import HeartbeatConfig, LLMConfig
from paw.tools.automation import AutomationTool


def test_cron_matches_supports_every_n_minutes() -> None:
    now = datetime(2026, 2, 17, 10, 15, tzinfo=UTC)
    assert _cron_matches("*/5 * * * *", now) is True
    assert _cron_matches("*/10 * * * *", now) is False


def test_cron_matches_supports_exact_values() -> None:
    now = datetime(2026, 2, 17, 10, 15, tzinfo=UTC)
    assert _cron_matches("15 10 * * *", now) is True
    assert _cron_matches("14 10 * * *", now) is False


class _DummyDB:
    async def channel_pairing_code_create(
        self,
        **kwargs,  # pragma: no cover - not used in this test
    ):
        return None

def test_automation_model_set_updates_runtime_config() -> None:
    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.3-codex")
    tool = AutomationTool(db=_DummyDB(), heartbeat=HeartbeatConfig(), llm=llm)

    result = asyncio.run(tool.execute(action="model_set", model="ollama/llama3.1"))

    assert "Runtime models updated." in result
    assert llm.model == "ollama/llama3.1"
    assert llm.smart_model == "ollama/llama3.1"


def test_automation_model_set_regular_keeps_smart_model() -> None:
    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.3-codex")
    tool = AutomationTool(db=_DummyDB(), heartbeat=HeartbeatConfig(), llm=llm)

    asyncio.run(tool.execute(action="model_set_regular", model="azure/gpt-4.1-mini"))

    assert llm.model == "azure/gpt-4.1-mini"
    assert llm.smart_model == "openai/gpt-5.3-codex"
