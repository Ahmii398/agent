from datetime import UTC, datetime

import pytest

from trade_agent.core.timeutil import ensure_utc, from_iso, to_iso, year_month


def test_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="naive"):
        ensure_utc(datetime(2024, 1, 1, 12, 0, 0))


def test_roundtrip_iso() -> None:
    dt = datetime(2024, 6, 15, 8, 30, 0, tzinfo=UTC)
    assert from_iso(to_iso(dt)) == dt


def test_year_month() -> None:
    dt = datetime(2026, 10, 3, tzinfo=UTC)
    assert year_month(dt) == "2026-10"
