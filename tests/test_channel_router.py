import os

import pytest

from paw.channels.router import ChannelRouter
from paw.db.engine import Database


def _test_db_url() -> str:
    value = os.getenv("PAW_TEST_DATABASE_URL")
    if not value:
        pytest.skip("PAW_TEST_DATABASE_URL is not set")
    return value


@pytest.mark.asyncio
async def test_channel_router_returns_stable_conversation_id() -> None:
    db = Database(_test_db_url())
    await db.initialize()

    router = ChannelRouter(db)
    first = await router.resolve_conversation_id("telegram", "telegram:123")
    second = await router.resolve_conversation_id("telegram", "telegram:123")

    assert first == second

    await db.close()


@pytest.mark.asyncio
async def test_channel_router_distinguishes_session_keys() -> None:
    db = Database(_test_db_url())
    await db.initialize()

    router = ChannelRouter(db)
    dm = await router.resolve_conversation_id("telegram", "telegram:123")
    group = await router.resolve_conversation_id("telegram", "telegram:group:123")

    assert dm != group

    await db.close()
