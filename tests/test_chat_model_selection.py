from types import SimpleNamespace

from paw.api.routes.chat import _resolve_model


def test_resolve_model_uses_regular_by_default() -> None:
    config = SimpleNamespace(llm=SimpleNamespace(model="openai/gpt-5-mini", smart_model="openai/gpt-4o"))
    selected = _resolve_model(config=config, requested_model=None, smart_mode=False)
    assert selected == "openai/gpt-5-mini"


def test_resolve_model_uses_smart_mode_when_enabled() -> None:
    config = SimpleNamespace(llm=SimpleNamespace(model="openai/gpt-5-mini", smart_model="openai/gpt-4o"))
    selected = _resolve_model(config=config, requested_model=None, smart_mode=True)
    assert selected == "openai/gpt-4o"


def test_resolve_model_prefers_explicit_request() -> None:
    config = SimpleNamespace(llm=SimpleNamespace(model="openai/gpt-5-mini", smart_model="openai/gpt-4o"))
    selected = _resolve_model(
        config=config,
        requested_model="anthropic/claude-sonnet-4-20250514",
        smart_mode=True,
    )
    assert selected == "anthropic/claude-sonnet-4-20250514"
