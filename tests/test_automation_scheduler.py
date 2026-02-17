from datetime import UTC, datetime

from paw.automation.scheduler import _cron_matches


def test_cron_matches_supports_every_n_minutes() -> None:
    now = datetime(2026, 2, 17, 10, 15, tzinfo=UTC)
    assert _cron_matches("*/5 * * * *", now) is True
    assert _cron_matches("*/10 * * * *", now) is False


def test_cron_matches_supports_exact_values() -> None:
    now = datetime(2026, 2, 17, 10, 15, tzinfo=UTC)
    assert _cron_matches("15 10 * * *", now) is True
    assert _cron_matches("14 10 * * *", now) is False
