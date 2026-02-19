from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from paw.channels.telegram.provider import TelegramChannelProvider
from paw.config import TelegramChannelConfig
from paw.db.engine import Database


def _test_db_url() -> str:
    value = os.getenv("PAW_TEST_DATABASE_URL")
    if not value:
        pytest.skip("PAW_TEST_DATABASE_URL is not set")
    return value


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def post(self, _url: str, json: dict[str, Any]) -> _FakeResponse:
        text = json.get("text")
        if isinstance(text, str):
            self.messages.append(text)
        return _FakeResponse()


@pytest.mark.asyncio
async def test_telegram_mode_toggle_switches_model_for_chat() -> None:
    db = Database(_test_db_url())
    await db.initialize()

    captured_models: list[str | None] = []

    async def inbound_handler(event) -> str:
        captured_models.append(event.model)
        return "ok"

    provider = TelegramChannelProvider(
        config=TelegramChannelConfig(enabled=True, bot_token="token", dm_policy="open"),
        db=db,
        inbound_handler=inbound_handler,
        default_model="openai/gpt-5-mini",
        default_smart_model="openai/gpt-5.2",
    )

    client = _FakeClient()

    await provider._process_update(
        client,
        "https://api.telegram.org/botTOKEN",
        {
            "update_id": 100,
            "message": {
                "message_id": 1,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123},
                "text": "/status",
            },
        },
    )
    assert "Mode: regular" in client.messages[-1]
    assert "Current model: openai/gpt-5-mini" in client.messages[-1]

    await provider._process_update(
        client,
        "https://api.telegram.org/botTOKEN",
        {
            "update_id": 101,
            "message": {
                "message_id": 2,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123},
                "text": "/mode",
            },
        },
    )
    assert "Mode switched to smart" in client.messages[-1]

    await provider._process_update(
        client,
        "https://api.telegram.org/botTOKEN",
        {
            "update_id": 102,
            "message": {
                "message_id": 3,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123},
                "text": "hello",
            },
        },
    )

    assert captured_models == ["openai/gpt-5.2"]

    await db.close()


@pytest.mark.asyncio
async def test_telegram_heartbeat_commands_show_add_edit_remove(tmp_path: Path) -> None:
    db = Database(_test_db_url())
    await db.initialize()

    async def inbound_handler(_event) -> str:
        return "ok"

    checklist = tmp_path / "heartbeat.md"
    checklist.write_text("- initial check | output=log\n", encoding="utf-8")

    provider = TelegramChannelProvider(
        config=TelegramChannelConfig(enabled=True, bot_token="token", dm_policy="open"),
        db=db,
        inbound_handler=inbound_handler,
        default_model="openai/gpt-5-mini",
        default_smart_model="openai/gpt-5.2",
        heartbeat_interval_minutes=7,
        heartbeat_checklist_path=str(checklist),
        heartbeat_default_output_target="log",
    )

    client = _FakeClient()

    await provider._process_update(
        client,
        "https://api.telegram.org/botTOKEN",
        {
            "update_id": 200,
            "message": {
                "message_id": 1,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123},
                "text": "/heartbeat show",
            },
        },
    )
    assert "interval_minutes=7" in client.messages[-1]
    assert "1. - initial check | output=log" in client.messages[-1]

    await provider._process_update(
        client,
        "https://api.telegram.org/botTOKEN",
        {
            "update_id": 201,
            "message": {
                "message_id": 2,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123},
                "text": "/heartbeat add Review PR queue | output=telegram",
            },
        },
    )
    assert client.messages[-1] == "Added heartbeat item #2."

    await provider._process_update(
        client,
        "https://api.telegram.org/botTOKEN",
        {
            "update_id": 202,
            "message": {
                "message_id": 3,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123},
                "text": "/heartbeat edit 2 Review PR queue daily | output=email",
            },
        },
    )
    assert client.messages[-1] == "Updated heartbeat item #2."

    await provider._process_update(
        client,
        "https://api.telegram.org/botTOKEN",
        {
            "update_id": 203,
            "message": {
                "message_id": 4,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123},
                "text": "/heartbeat remove 1",
            },
        },
    )
    assert client.messages[-1] == "Removed heartbeat item #1."

    final_lines = checklist.read_text(encoding="utf-8").splitlines()
    assert final_lines == ["- Review PR queue daily | output=email"]

    await db.close()
