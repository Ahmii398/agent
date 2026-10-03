"""Incremental historical downloader. Covered ranges are never fetched again."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import ensure_utc, to_iso, utcnow_iso
from trade_agent.data.candles import CandleStore, bars_to_frame, drop_unclosed, merge_frames
from trade_agent.data.gaps import detect_gaps, quality_report
from trade_agent.data.timeframes import timeframe_delta
from trade_agent.db.store import Store
from trade_agent.interfaces.data_provider import DataProvider

log = get_logger("data.download")


class HistoricalDownloader:
    """Fetch missing OHLCV into Parquet. Same timestamps are not requested twice."""

    def __init__(self, provider: DataProvider, candles: CandleStore, store: Store) -> None:
        self.provider = provider
        self.candles = candles
        self.store = store

    def download(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Ensure ``[start, end)`` is on disk (closed bars only) and return it."""
        start = ensure_utc(start)
        end = ensure_utc(end)
        existing = drop_unclosed(
            self.candles.load(self.provider.name, symbol, timeframe),
            timeframe,
        )
        needed = _missing_ranges(existing, start, end, timeframe)
        fetched_rows = 0
        pieces = [existing]
        for rng_start, rng_end in needed:
            log.info(
                "fetch exchange=%s symbol=%s tf=%s start=%s end=%s",
                self.provider.name,
                symbol,
                timeframe,
                to_iso(rng_start),
                to_iso(rng_end),
            )
            bars = self.provider.fetch_ohlcv(symbol, timeframe, rng_start, rng_end)
            part = drop_unclosed(bars_to_frame(bars), timeframe)
            fetched_rows += len(part)
            pieces.append(part)
        combined = drop_unclosed(merge_frames(*pieces), timeframe)
        # Keep only what we were asked for plus any previously stored history.
        self.candles.save(self.provider.name, symbol, timeframe, combined)
        window = _slice(combined, start, end)
        self._record_coverage(symbol, timeframe, combined)
        report = quality_report(window, timeframe)
        log.info(
            "stored exchange=%s symbol=%s tf=%s rows=%s fetched_new=%s gaps=%s",
            self.provider.name,
            symbol,
            timeframe,
            report.rows,
            fetched_rows,
            len(report.gaps),
        )
        return window

    def repair_gaps(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Re-fetch only detected holes. Already-present bars are not requested."""
        existing = self.candles.load(self.provider.name, symbol, timeframe)
        gaps = detect_gaps(existing, timeframe)
        if not gaps:
            return existing
        parts = [existing]
        for gap in gaps:
            bars = self.provider.fetch_ohlcv(symbol, timeframe, gap.start, gap.end)
            parts.append(bars_to_frame(bars))
        combined = drop_unclosed(merge_frames(*parts), timeframe)
        self.candles.save(self.provider.name, symbol, timeframe, combined)
        self._record_coverage(symbol, timeframe, combined)
        return combined

    def _record_coverage(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        self.store.execute(
            """
            INSERT INTO ohlcv_coverage (
                exchange, symbol, timeframe, start_ts, end_ts, row_count, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(exchange, symbol, timeframe) DO UPDATE SET
                start_ts = excluded.start_ts,
                end_ts = excluded.end_ts,
                row_count = excluded.row_count,
                fetched_at = excluded.fetched_at
            """,
            (
                self.provider.name,
                symbol,
                timeframe,
                to_iso(df["ts"].iloc[0].to_pydatetime()),
                to_iso(df["ts"].iloc[-1].to_pydatetime()),
                int(len(df)),
                utcnow_iso(),
            ),
        )


def _slice(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    if df.empty:
        return df
    ts = df["ts"]
    return df.loc[(ts >= pd.Timestamp(start)) & (ts < pd.Timestamp(end))].reset_index(drop=True)


def _missing_ranges(
    existing: pd.DataFrame,
    start: datetime,
    end: datetime,
    timeframe: str,
) -> list[tuple[datetime, datetime]]:
    """Compute half-open ranges that are not already stored."""
    if existing.empty:
        return [(start, end)]
    delta = timeframe_delta(timeframe)
    first = ensure_utc(existing["ts"].iloc[0].to_pydatetime())
    last = ensure_utc(existing["ts"].iloc[-1].to_pydatetime())
    ranges: list[tuple[datetime, datetime]] = []
    if start < first:
        ranges.append((start, min(first, end)))
    # Internal holes relative to the requested window.
    window = _slice(existing, start, end)
    for gap in detect_gaps(window, timeframe):
        ranges.append((gap.start, gap.end))
    nxt = last + delta
    if nxt < end:
        ranges.append((nxt, end))
    min_width = timeframe_delta(timeframe)
    return [(a, b) for a, b in ranges if b - a >= min_width]
