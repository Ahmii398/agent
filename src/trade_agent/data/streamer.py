"""Closed-candle streamer. Polls REST; yields a bar only after it has closed."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import datetime

from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import utcnow
from trade_agent.data.timeframes import timeframe_delta
from trade_agent.interfaces.data_provider import DataProvider, OHLCVBar

log = get_logger("data.stream")


def poll_closed_candles(
    provider: DataProvider,
    symbol: str,
    timeframe: str,
    *,
    poll_seconds: float = 2.0,
    lookback_bars: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = utcnow,
    max_yields: int | None = None,
) -> Iterator[OHLCVBar]:
    """Poll ``fetch_ohlcv`` and yield newly closed candles.

    The still-forming bar is never yielded (``fetch_ohlcv`` already drops it).
    ``max_yields`` is for tests and one-shot CLI use.
    """
    seen: set[datetime] = set()
    yielded = 0
    delta = timeframe_delta(timeframe)
    while True:
        as_of = now()
        start = as_of - delta * lookback_bars
        bars = provider.fetch_ohlcv(symbol, timeframe, start, as_of)
        for bar in bars:
            if bar.ts in seen:
                continue
            # Defense in depth: refuse a bar that has not closed.
            if bar.ts + delta > as_of:
                log.warning(
                    "dropped unclosed bar exchange=%s symbol=%s tf=%s ts=%s",
                    provider.name,
                    symbol,
                    timeframe,
                    bar.ts.isoformat(),
                )
                continue
            seen.add(bar.ts)
            log.info(
                "closed_candle exchange=%s symbol=%s tf=%s ts=%s close=%s",
                provider.name,
                symbol,
                timeframe,
                bar.ts.isoformat(),
                bar.close,
            )
            yield bar
            yielded += 1
            if max_yields is not None and yielded >= max_yields:
                return
        sleep(poll_seconds)
