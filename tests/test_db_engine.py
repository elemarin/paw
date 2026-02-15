import pytest

from paw.db.engine import Database


@pytest.mark.asyncio
async def test_database_supports_delete_journal_mode(tmp_path) -> None:
    db = Database(str(tmp_path), journal_mode="DELETE")
    await db.initialize()

    mode = await db.fetch_one("PRAGMA journal_mode")
    assert mode is not None
    assert mode["journal_mode"] == "delete"

    await db.close()


def test_database_rejects_unsupported_journal_mode(tmp_path) -> None:
    with pytest.raises(ValueError, match="Unsupported SQLite journal mode: INVALID"):
        Database(str(tmp_path), journal_mode="INVALID")
