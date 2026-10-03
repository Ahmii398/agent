"""Binance (and other ccxt) public OHLCV. No API key required for spot candles."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import ensure_utc, utcnow
from trade_agent.data.candles import bars_to_frame, drop_unclosed, frame_to_bars
from trade_agent.data.gaps import detect_gaps
from trade_agent.data.timeframes import timeframe_delta
from trade_agent.interfaces.data_provider import DataProvider, Gap, OHLCVBar

log = get_logger("data.ccxt")

# Public spot. Do not send keys; we are not trading through this client.
_DEFAULT_EXCHANGE = "binance"


class CcxtOHLCVProvider(DataProvider):
    """Historical OHLCV via ccxt REST. Streaming is implemented by polling."""

    def __init__(
        self, exchange_id: str = _DEFAULT_EXCHANGE, exchange: object | None = None
    ) -> None:
        self.exchange_id = exchange_id
        self.name = exchange_id
        if exchange is not None:
            self._exchange = exchange
        else:
            import ccxt

            cls = getattr(ccxt, exchange_id)
            self._exchange = cls({"enableRateLimit": True, "options": {"defaultType": "spot"}})

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Fetch closed candles in ``[start, end)``. The still-open bar is dropped."""
        start = ensure_utc(start)
        end = ensure_utc(end)
        if end <= start:
            return []
        since = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        rows: list[list[float]] = []
        while since < end_ms:
            batch = self._exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not batch:
                break
            rows.extend(batch)
            last_ts = int(batch[-1][0])
            if last_ts <= since:
                break
            since = last_ts + 1
            if since >= end_ms:
                break
            log.info(
                "provider=%s symbol=%s tf=%s fetched_batch=%s last_open_ms=%s",
                self.name,
                symbol,
                timeframe,
                len(batch),
                last_ts,
            )
        bars = _rows_to_bars(rows, start=start, end=end)
        frame = drop_unclosed(bars_to_frame(bars), timeframe, as_of=utcnow())
        return frame_to_bars(frame)

    def detect_gaps(self, bars: list[OHLCVBar], timeframe: str) -> list[Gap]:
        return detect_gaps(bars_to_frame(bars), timeframe)

    def stream_ohlcv(self, symbol: str, timeframe: str) -> Iterator[OHLCVBar]:
        from trade_agent.data.streamer import poll_closed_candles

        yield from poll_closed_candles(self, symbol, timeframe)

    def available_symbols(self) -> list[str]:
        markets = self._exchange.load_markets()
        return sorted(m for m, info in markets.items() if info.get("spot") and m.endswith("/USDT"))


def _rows_to_bars(rows: list[list[float]], *, start: datetime, end: datetime) -> list[OHLCVBar]:
    seen: set[int] = set()
    bars: list[OHLCVBar] = []
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    for row in rows:
        ts_ms = int(row[0])
        if ts_ms in seen or ts_ms < start_ms or ts_ms >= end_ms:
            continue
        seen.add(ts_ms)
        bars.append(
            OHLCVBar(
                ts=datetime.fromtimestamp(ts_ms / 1000.0, tz=start.tzinfo),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    bars.sort(key=lambda b: b.ts)
    return bars


def closed_as_of(bar: OHLCVBar, timeframe: str, as_of: datetime) -> bool:
    """True iff the bar is fully closed at ``as_of`` (no look-ahead)."""
    return bar.ts + timeframe_delta(timeframe) <= ensure_utc(as_of)
