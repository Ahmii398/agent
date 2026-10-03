from datetime import UTC, datetime

import pytest

from trade_agent.data.timeframes import expected_bar_count, timeframe_delta


def test_parse_common_timeframes() -> None:
    assert timeframe_delta("1m").total_seconds() == 60
    assert timeframe_delta("1h").total_seconds() == 3600
    assert timeframe_delta("4h").total_seconds() == 14400
    assert timeframe_delta("1d").total_seconds() == 86400


def test_bad_timeframe() -> None:
    with pytest.raises(ValueError):
        timeframe_delta("1x")


def test_expected_bar_count() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 2, tzinfo=UTC)
    assert expected_bar_count(start, end, "1h") == 24
