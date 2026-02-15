from types import SimpleNamespace

import pytest

from paw.agent.conversation import Conversation
from paw.agent.loop import AgentLoop
from paw.agent.tools import Tool, ToolRegistry
from paw.config import AgentConfig


class DummyTool(Tool):
    @property
    def name(self) -> str:
        return "coder"

    @property
    def description(self) -> str:
        return "dummy coder"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "ok"


class FakeGateway:
    def __init__(self) -> None:
        self.models_used: list[str | None] = []
        self._count = 0

    async def completion(self, messages, *, model=None, **kwargs):
        self.models_used.append(model)
        self._count += 1

        if self._count == 1:
            tool_call = SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name="coder", arguments="{}"),
            )
            message = SimpleNamespace(content="", tool_calls=[tool_call])
            choice = SimpleNamespace(message=message, finish_reason="tool_calls")
            return SimpleNamespace(choices=[choice], usage=None)

        message = SimpleNamespace(content="final answer", tool_calls=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None)


class FakeGatewayForToolName:
    def __init__(self, tool_name: str) -> None:
        self.models_used: list[str | None] = []
        self._count = 0
        self._tool_name = tool_name

    async def completion(self, messages, *, model=None, **kwargs):
        self.models_used.append(model)
        self._count += 1

        if self._count == 1:
            tool_call = SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name=self._tool_name, arguments="{}"),
            )
            message = SimpleNamespace(content="", tool_calls=[tool_call])
            choice = SimpleNamespace(message=message, finish_reason="tool_calls")
            return SimpleNamespace(choices=[choice], usage=None)

        message = SimpleNamespace(content="final answer", tool_calls=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None)


class NamedDummyTool(Tool):
    def __init__(self, tool_name: str) -> None:
        self._name = tool_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"dummy {self._name}"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "ok"


@pytest.mark.asyncio
async def test_agent_uses_tool_specific_model_on_followup_iteration() -> None:
    gateway = FakeGateway()
    registry = ToolRegistry()
    registry.register(DummyTool())

    loop = AgentLoop(
        gateway=gateway,
        registry=registry,
        config=AgentConfig(max_iterations=3, max_tool_calls=3, tool_models={"coder": "openai/gpt-5.4-codex"}),
    )

    conversation = Conversation(id="conv-model-routing")
    conversation.add_message("system", "You are PAW")
    conversation.add_message("user", "create plugin")

    result = await loop.run(conversation)

    assert result.response == "final answer"
    assert gateway.models_used == [None, "openai/gpt-5.4-codex"]


def test_agent_config_tool_models_parses_key_value_string() -> None:
    cfg = AgentConfig(tool_models="coder=openai/gpt-5.4-codex,shell=ollama/llama3.1")
    assert cfg.tool_models == {
        "coder": "openai/gpt-5.4-codex",
        "shell": "ollama/llama3.1",
    }


def test_agent_config_tool_profiles_parse_key_value_string() -> None:
    cfg = AgentConfig(
        tool_model_profiles="regular=openai/gpt-5-mini,smart=openai/gpt-5.4-codex",
        tool_profile_by_tool="coder=smart,shell=regular",
    )
    assert cfg.tool_model_profiles == {
        "regular": "openai/gpt-5-mini",
        "smart": "openai/gpt-5.4-codex",
    }
    assert cfg.tool_profile_by_tool == {
        "coder": "smart",
        "shell": "regular",
    }


@pytest.mark.asyncio
async def test_agent_chat_trigger_think_harder_uses_smart_profile() -> None:
    gateway = FakeGatewayForToolName("shell")
    registry = ToolRegistry()
    registry.register(NamedDummyTool("shell"))

    loop = AgentLoop(
        gateway=gateway,
        registry=registry,
        config=AgentConfig(
            max_iterations=3,
            max_tool_calls=3,
            tool_model_profiles={
                "regular": "openai/gpt-5-mini",
                "smart": "openai/gpt-5.4-codex",
            },
            tool_profile_default="regular",
            tool_profile_by_tool={"shell": "regular"},
        ),
    )

    conversation = Conversation(id="conv-think-harder")
    conversation.add_message("system", "You are PAW")
    conversation.add_message("user", "think harder and run shell checks")

    result = await loop.run(conversation)

    assert result.response == "final answer"
    assert gateway.models_used == [None, "openai/gpt-5.4-codex"]


@pytest.mark.asyncio
async def test_agent_chat_trigger_switch_back_uses_regular_profile() -> None:
    gateway = FakeGatewayForToolName("coder")
    registry = ToolRegistry()
    registry.register(NamedDummyTool("coder"))

    loop = AgentLoop(
        gateway=gateway,
        registry=registry,
        config=AgentConfig(
            max_iterations=3,
            max_tool_calls=3,
            tool_model_profiles={
                "regular": "openai/gpt-5-mini",
                "smart": "openai/gpt-5.4-codex",
            },
            tool_profile_default="regular",
            tool_profile_by_tool={"coder": "smart"},
        ),
    )

    conversation = Conversation(id="conv-switch-back")
    conversation.add_message("system", "You are PAW")
    conversation.add_message("user", "switch back and then create a plugin")

    result = await loop.run(conversation)

    assert result.response == "final answer"
    assert gateway.models_used == [None, "openai/gpt-5-mini"]
