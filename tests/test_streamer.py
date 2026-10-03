from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trade_agent.data.streamer import poll_closed_candles
from trade_agent.interfaces.data_provider import DataProvider, Gap, OHLCVBar


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class _PollProvider(DataProvider):
    name = "binance"

    def __init__(self) -> None:
        self.bars: list[OHLCVBar] = []

    def fetch_ohlcv(self, symbol, timeframe, start, end):
        return [b for b in self.bars if start <= b.ts < end]

    def detect_gaps(self, bars, timeframe) -> list[Gap]:
        return []


def test_streamer_yields_each_closed_bar_once() -> None:
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    clock = _Clock(t0 + timedelta(hours=2, minutes=5))
    provider = _PollProvider()
    provider.bars = [
        OHLCVBar(ts=t0, open=1, high=2, low=0.5, close=1.2, volume=1),
        OHLCVBar(ts=t0 + timedelta(hours=1), open=2, high=3, low=1.5, close=2.2, volume=1),
    ]
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        if len(sleeps) >= 2:
            raise StopIteration

    gen = poll_closed_candles(
        provider,
        "BTC/USDT",
        "1h",
        poll_seconds=1.0,
        sleep=fake_sleep,
        now=clock,
        max_yields=2,
    )
    got = list(gen)
    assert [b.ts for b in got] == [t0, t0 + timedelta(hours=1)]


def test_streamer_drops_unclosed_even_if_provider_leaks() -> None:
    t0 = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    clock = _Clock(t0 + timedelta(minutes=10))  # first bar still open
    provider = _PollProvider()
    provider.bars = [OHLCVBar(ts=t0, open=1, high=2, low=0.5, close=1.2, volume=1)]
    got = list(
        poll_closed_candles(
            provider,
            "BTC/USDT",
            "1h",
            poll_seconds=0.0,
            sleep=lambda _s: None,
            now=clock,
            max_yields=1,
            max_polls=2,
        )
    )
    assert got == []
