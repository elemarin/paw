from __future__ import annotations

import os
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
        default_smart_model="openai/gpt-4o",
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

    assert captured_models == ["openai/gpt-4o"]

    await db.close()
