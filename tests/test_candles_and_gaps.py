from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from trade_agent.data.candles import (
    drop_unclosed,
    empty_frame,
    merge_frames,
    normalize_frame,
)
from trade_agent.data.gaps import detect_gaps, quality_report


def _bar(ts: datetime, price: float = 100.0) -> dict:
    return {
        "ts": ts,
        "open": price,
        "high": price + 1,
        "low": price - 1,
        "close": price + 0.2,
        "volume": 10.0,
    }


def test_normalize_sorts_and_dedupes() -> None:
    t0 = datetime(2024, 1, 1, 0, tzinfo=UTC)
    t1 = datetime(2024, 1, 1, 1, tzinfo=UTC)
    df = normalize_frame(
        pd.DataFrame([_bar(t1, 101), _bar(t0, 100), _bar(t0, 999)])
    )
    assert list(df["ts"]) == [pd.Timestamp(t0), pd.Timestamp(t1)]
    assert df.iloc[0]["close"] == 100.2  # first copy kept


def test_detect_planted_gap() -> None:
    t0 = datetime(2024, 1, 1, 0, tzinfo=UTC)
    rows = [_bar(t0 + timedelta(hours=i)) for i in (0, 1, 2, 4, 5)]
    df = normalize_frame(pd.DataFrame(rows))
    gaps = detect_gaps(df, "1h")
    assert len(gaps) == 1
    assert gaps[0].missing_bars == 1
    assert gaps[0].start == datetime(2024, 1, 1, 3, tzinfo=UTC)


def test_quality_flags_ohlc_and_neg_volume() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    bad = _bar(t0)
    bad["high"] = 1.0
    bad["low"] = 50.0
    bad["volume"] = -3
    report = quality_report(normalize_frame(pd.DataFrame([bad])), "1h")
    assert report.ohlc_violations == 1
    assert report.negative_volume == 1
    assert report.ok is False


def test_merge_empty() -> None:
    assert merge_frames(empty_frame()).empty
