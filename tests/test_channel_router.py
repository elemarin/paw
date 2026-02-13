import pytest

from paw.channels.router import ChannelRouter
from paw.db.engine import Database


@pytest.mark.asyncio
async def test_channel_router_returns_stable_conversation_id(tmp_path) -> None:
    db = Database(str(tmp_path))
    await db.initialize()

    router = ChannelRouter(db)
    first = await router.resolve_conversation_id("telegram", "telegram:123")
    second = await router.resolve_conversation_id("telegram", "telegram:123")

    assert first == second

    await db.close()


@pytest.mark.asyncio
async def test_channel_router_distinguishes_session_keys(tmp_path) -> None:
    db = Database(str(tmp_path))
    await db.initialize()

    router = ChannelRouter(db)
    dm = await router.resolve_conversation_id("telegram", "telegram:123")
    group = await router.resolve_conversation_id("telegram", "telegram:group:123")

    assert dm != group

    await db.close()
