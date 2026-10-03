from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from trade_agent.features.fvg import fair_value_gaps
from trade_agent.features.patterns import candle_patterns
from trade_agent.features.sessions import session_flags
from trade_agent.features.volatility import atr


def test_sessions_utc() -> None:
    ts = [
        datetime(2024, 1, 2, 1, tzinfo=UTC),   # Asia
        datetime(2024, 1, 2, 8, tzinfo=UTC),   # London
        datetime(2024, 1, 2, 14, tzinfo=UTC),  # NY
        datetime(2024, 1, 2, 22, tzinfo=UTC),  # off
    ]
    df = pd.DataFrame(
        {
            "ts": ts,
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
        }
    )
    s = session_flags(df)
    assert list(s["session"]) == ["asia", "london", "ny", "off"]
    assert bool(s.loc[2, "session_london"])  # NY overlap still flags London


def test_atr_positive() -> None:
    n = 30
    df = pd.DataFrame(
        {
            "ts": [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(n)],
            "open": [100 + i * 0.1 for i in range(n)],
            "high": [101 + i * 0.1 for i in range(n)],
            "low": [99 + i * 0.1 for i in range(n)],
            "close": [100.5 + i * 0.1 for i in range(n)],
            "volume": [1] * n,
        }
    )
    series = atr(df, 14)
    assert series.iloc[13:].min() > 0


def test_bullish_fvg() -> None:
    # t-2 high=10, t low=12 → gap
    rows = [
        (10, 10, 9, 10),
        (10, 11, 9.5, 11),
        (12, 13, 12, 12.5),
    ]
    df = pd.DataFrame(
        {
            "ts": [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(3)],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": 1,
        }
    )
    fvg = fair_value_gaps(df)
    assert bool(fvg.loc[2, "fvg_bull"])
    assert not bool(fvg.loc[2, "fvg_bear"])


def test_bull_engulf() -> None:
    df = pd.DataFrame(
        {
            "ts": [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(2)],
            "open": [10.0, 8.0],
            "high": [10.5, 12.0],
            "low": [8.5, 7.5],
            "close": [9.0, 11.5],
            "volume": 1,
        }
    )
    p = candle_patterns(df)
    assert bool(p.loc[1, "bull_engulf"])
