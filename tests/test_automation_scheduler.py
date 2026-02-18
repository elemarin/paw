import asyncio
from datetime import UTC, datetime

from paw.automation.scheduler import _cron_matches
from paw.config import HeartbeatConfig, LLMConfig
from paw.tools.automation import AutomationTool, _parse_heartbeat_item


def test_cron_matches_supports_every_n_minutes() -> None:
    now = datetime(2026, 2, 17, 10, 15, tzinfo=UTC)
    assert _cron_matches("*/5 * * * *", now) is True
    assert _cron_matches("*/10 * * * *", now) is False


def test_cron_matches_supports_exact_values() -> None:
    now = datetime(2026, 2, 17, 10, 15, tzinfo=UTC)
    assert _cron_matches("15 10 * * *", now) is True
    assert _cron_matches("14 10 * * *", now) is False


class _DummyDB:
    def __init__(self) -> None:
        self.cron_add_calls: list[dict] = []

    async def channel_pairing_code_create(
        self,
        **kwargs,  # pragma: no cover - not used in this test
    ):
        return None

    async def heartbeat_cron_add(self, **kwargs):
        self.cron_add_calls.append(kwargs)

    async def heartbeat_cron_list(self):
        return []

    async def heartbeat_cron_remove(self, **kwargs):
        return True

def test_automation_model_set_updates_runtime_config() -> None:
    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.2")
    tool = AutomationTool(db=_DummyDB(), heartbeat=HeartbeatConfig(), llm=llm)

    result = asyncio.run(tool.execute(action="model_set", model="ollama/llama3.1"))

    assert "Runtime models updated." in result
    assert llm.model == "ollama/llama3.1"
    assert llm.smart_model == "ollama/llama3.1"


def test_automation_model_set_regular_keeps_smart_model() -> None:
    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.2")
    tool = AutomationTool(db=_DummyDB(), heartbeat=HeartbeatConfig(), llm=llm)

    asyncio.run(tool.execute(action="model_set_regular", model="azure/gpt-4.1-mini"))

    assert llm.model == "azure/gpt-4.1-mini"
    assert llm.smart_model == "openai/gpt-5.2"


def test_automation_heartbeat_item_requires_output_target(tmp_path) -> None:
    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.2")
    heartbeat = HeartbeatConfig(checklist_path=str(tmp_path / "heartbit.md"))
    tool = AutomationTool(db=_DummyDB(), heartbeat=heartbeat, llm=llm)

    result = asyncio.run(tool.execute(action="heartbeat_add_item", text="summarize workspace"))

    assert "Please specify output_target" in result


def test_automation_heartbeat_item_add_edit_remove(tmp_path) -> None:
    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.2")
    heartbeat = HeartbeatConfig(checklist_path=str(tmp_path / "heartbit.md"))
    tool = AutomationTool(db=_DummyDB(), heartbeat=heartbeat, llm=llm)

    add_result = asyncio.run(
        tool.execute(
            action="heartbeat_add_item",
            text="summarize workspace",
            output_target="telegram:default",
        )
    )
    edit_result = asyncio.run(
        tool.execute(
            action="heartbeat_edit_item",
            index=1,
            text="summarize workspace deeply",
            output_target="email:ops",
        )
    )
    remove_result = asyncio.run(tool.execute(action="heartbeat_remove_item", index=1))

    assert "Added heartbeat item #1." == add_result
    assert "Updated heartbeat item #1." == edit_result
    assert "Removed heartbeat item #1." == remove_result


def test_automation_cron_add_requires_output_target() -> None:
    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.2")
    db = _DummyDB()
    tool = AutomationTool(db=db, heartbeat=HeartbeatConfig(), llm=llm)

    result = asyncio.run(
        tool.execute(
            action="cron_add",
            label="summary",
            schedule="*/30 * * * *",
            prompt="do summary",
        )
    )

    assert "Please specify output_target" in result
    assert db.cron_add_calls == []


def test_parse_heartbeat_item_handles_output_and_extra_fields() -> None:
    text, output = _parse_heartbeat_item(
        "- summarize workspace | priority=high | output=telegram:default"
    )
    assert text == "summarize workspace"
    assert output == "telegram:default"


def test_heartbeat_items_ignores_non_list_lines(tmp_path) -> None:
    path = tmp_path / "heartbit.md"
    path.write_text(
        "# Heading\n\nnot an item\n* another bullet style\n"
        "- valid one | output=telegram:default\n  \n- valid two\n",
        encoding="utf-8",
    )

    llm = LLMConfig(model="openai/gpt-4o-mini", smart_model="openai/gpt-5.2")
    heartbeat = HeartbeatConfig(checklist_path=str(path))
    tool = AutomationTool(db=_DummyDB(), heartbeat=heartbeat, llm=llm)

    items = tool._heartbeat_items()
    assert items == ["- valid one | output=telegram:default", "- valid two"]
