from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trade_agent.data.candles import CandleStore, bars_to_frame
from trade_agent.data.downloader import HistoricalDownloader
from trade_agent.interfaces.data_provider import DataProvider, Gap, OHLCVBar


def _bar(ts: datetime, price: float) -> OHLCVBar:
    return OHLCVBar(ts=ts, open=price, high=price + 1, low=price - 1, close=price + 0.1, volume=5)


class ScriptedProvider(DataProvider):
    name = "binance"

    def __init__(self, bars: list[OHLCVBar]) -> None:
        self.bars = bars
        self.calls: list[tuple[datetime, datetime]] = []

    def fetch_ohlcv(self, symbol, timeframe, start, end):
        self.calls.append((start, end))
        return [b for b in self.bars if start <= b.ts < end]

    def detect_gaps(self, bars, timeframe) -> list[Gap]:
        return []


def test_second_download_does_not_refetch(settings, store) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [_bar(start + timedelta(hours=i), 100 + i) for i in range(10)]
    provider = ScriptedProvider(bars)
    candles = CandleStore(settings.data_dir)
    dl = HistoricalDownloader(provider, candles, store)
    end = start + timedelta(hours=10)
    first = dl.download("BTC/USDT", "1h", start, end)
    assert len(first) == 10
    assert len(provider.calls) == 1
    second = dl.download("BTC/USDT", "1h", start, end)
    assert len(second) == 10
    assert len(provider.calls) == 1  # cache hit


def test_download_only_fetches_new_tail(settings, store) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    first_bars = [_bar(start + timedelta(hours=i), 100 + i) for i in range(5)]
    extra = [_bar(start + timedelta(hours=i), 200 + i) for i in range(5, 8)]
    provider = ScriptedProvider(first_bars + extra)
    candles = CandleStore(settings.data_dir)
    dl = HistoricalDownloader(provider, candles, store)
    dl.download("BTC/USDT", "1h", start, start + timedelta(hours=5))
    provider.calls.clear()
    out = dl.download("BTC/USDT", "1h", start, start + timedelta(hours=8))
    assert len(out) == 8
    assert len(provider.calls) == 1
    fetched_start, fetched_end = provider.calls[0]
    assert fetched_start == start + timedelta(hours=5)
    assert fetched_end == start + timedelta(hours=8)


def test_repair_fetches_only_the_hole(settings, store) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    present = [_bar(start + timedelta(hours=i), 10) for i in (0, 1, 2, 4, 5)]
    missing = _bar(start + timedelta(hours=3), 99)
    candles = CandleStore(settings.data_dir)
    candles.save("binance", "BTC/USDT", "1h", bars_to_frame(present))
    provider = ScriptedProvider(present + [missing])
    dl = HistoricalDownloader(provider, candles, store)
    repaired = dl.repair_gaps("BTC/USDT", "1h")
    assert len(repaired) == 6
    assert len(provider.calls) == 1
    assert provider.calls[0][0] == start + timedelta(hours=3)


def test_coverage_row_written(settings, store) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [_bar(start + timedelta(hours=i), 1) for i in range(3)]
    provider = ScriptedProvider(bars)
    dl = HistoricalDownloader(provider, CandleStore(settings.data_dir), store)
    dl.download("ETH/USDT", "1h", start, start + timedelta(hours=3))
    row = store.fetchone(
        "SELECT symbol, row_count FROM ohlcv_coverage WHERE symbol=?",
        ("ETH/USDT",),
    )
    assert row["row_count"] == 3
