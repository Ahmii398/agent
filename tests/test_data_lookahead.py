"""Deliberate look-ahead leaks that the data layer must reject."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from trade_agent.data.candles import drop_unclosed, normalize_frame
from trade_agent.data.ccxt_provider import CcxtOHLCVProvider, closed_as_of
from trade_agent.interfaces.data_provider import OHLCVBar


def _ohlcv_row(ts: datetime, price: float = 100.0) -> list[float]:
    return [int(ts.timestamp() * 1000), price, price + 1, price - 1, price + 0.5, 3.0]


class _ScriptedExchange:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows
        self.calls: list[tuple] = []

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        self.calls.append((symbol, timeframe, since, limit))
        out = [r for r in self.rows if since is None or r[0] >= since]
        return out[:limit]


def test_drop_unclosed_excludes_bar_that_has_not_finished() -> None:
    t0 = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    forming = t0 + timedelta(hours=2)
    as_of = forming + timedelta(minutes=15)  # 2h bar is only 15m old
    df = normalize_frame(
        pd.DataFrame(
            {
                "ts": [t0, t1, forming],
                "open": [1, 2, 3],
                "high": [2, 3, 4],
                "low": [0.5, 1.5, 2.5],
                "close": [1.5, 2.5, 3.5],
                "volume": [1, 1, 1],
            }
        )
    )
    closed = drop_unclosed(df, "1h", as_of=as_of)
    assert list(closed["ts"]) == [pd.Timestamp(t0), pd.Timestamp(t1)]
    assert pd.Timestamp(forming) not in set(closed["ts"])


def test_as_of_mid_bar_must_not_see_that_bar_or_later() -> None:
    """Using the open time of bar i as as_of must not include bar i (not closed)."""
    start = datetime(2024, 6, 1, tzinfo=UTC)
    times = [start + timedelta(hours=i) for i in range(20)]
    df = normalize_frame(
        pd.DataFrame(
            {
                "ts": times,
                "open": range(20),
                "high": [i + 1 for i in range(20)],
                "low": [i - 1 for i in range(20)],
                "close": [i + 0.1 for i in range(20)],
                "volume": [1] * 20,
            }
        )
    )
    as_of = times[10]  # bar 10 just opened
    visible = drop_unclosed(df, "1h", as_of=as_of)
    assert visible["ts"].max() == pd.Timestamp(times[9])
    leaked = visible[visible["ts"] >= pd.Timestamp(times[10])]
    assert leaked.empty, "look-ahead leak: future/unclosed bars visible"


def test_provider_drops_in_progress_and_future_rows() -> None:
    now = datetime(2024, 6, 1, 12, 30, tzinfo=UTC)
    closed = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    forming = now.replace(minute=0, second=0, microsecond=0)
    future = forming + timedelta(hours=1)
    exch = _ScriptedExchange(
        [
            _ohlcv_row(closed, 100),
            _ohlcv_row(forming, 200),
            _ohlcv_row(future, 300),
        ]
    )
    provider = CcxtOHLCVProvider(exchange_id="binance", exchange=exch)

    # Freeze "now" inside drop_unclosed by fetching a window that includes future
    # and monkeypatching utcnow used by the provider.
    import trade_agent.data.ccxt_provider as mod

    original = mod.utcnow
    mod.utcnow = lambda: now
    try:
        bars = provider.fetch_ohlcv(
            "BTC/USDT",
            "1h",
            closed - timedelta(hours=1),
            future + timedelta(hours=1),
        )
    finally:
        mod.utcnow = original

    assert [b.close for b in bars] == [100.5]
    assert all(closed_as_of(b, "1h", now) for b in bars)
    assert not any(b.ts >= forming for b in bars)


def test_closed_as_of_contract() -> None:
    ts = datetime(2024, 1, 1, 0, tzinfo=UTC)
    bar = OHLCVBar(ts=ts, open=1, high=2, low=0.5, close=1.5, volume=1)
    assert closed_as_of(bar, "1h", ts + timedelta(hours=1))
    assert not closed_as_of(bar, "1h", ts + timedelta(minutes=59))
    with pytest.raises(ValueError, match="naive"):
        closed_as_of(bar, "1h", datetime(2024, 1, 1, 1, 0, 0))
