import os

import pytest

from paw.db.engine import Database


def _test_db_url() -> str:
    value = os.getenv("PAW_TEST_DATABASE_URL")
    if not value:
        pytest.skip("PAW_TEST_DATABASE_URL is not set")
    return value


@pytest.mark.asyncio
async def test_database_initializes_postgres_schema() -> None:
    db = Database(_test_db_url())
    await db.initialize()

    row = await db.fetch_one("SELECT 1 as ok")
    assert row is not None
    assert row["ok"] == 1

    await db.close()


def test_database_requires_url() -> None:
    with pytest.raises(ValueError, match="PAW_DATABASE_URL is required"):
        Database("")
