"""Gap detection and quality checks on UTC OHLCV frames."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trade_agent.core.timeutil import ensure_utc
from trade_agent.data.timeframes import timeframe_delta
from trade_agent.interfaces.data_provider import Gap


@dataclass(frozen=True)
class QualityReport:
    rows: int
    first_ts: str | None
    last_ts: str | None
    duplicate_ts: int
    unsorted: bool
    ohlc_violations: int
    negative_volume: int
    naive_or_non_utc: int
    future_bars: int
    gaps: list[Gap]

    @property
    def ok(self) -> bool:
        return (
            self.duplicate_ts == 0
            and not self.unsorted
            and self.ohlc_violations == 0
            and self.negative_volume == 0
            and self.naive_or_non_utc == 0
            and self.future_bars == 0
        )


def detect_gaps(df: pd.DataFrame, timeframe: str) -> list[Gap]:
    """Return missing closed-bar intervals. Empty/single-row frames have no gaps."""
    if df is None or len(df) < 2:
        return []
    delta = pd.Timedelta(timeframe_delta(timeframe))
    ts = pd.to_datetime(df["ts"], utc=True).sort_values().reset_index(drop=True)
    gaps: list[Gap] = []
    for prev, nxt in zip(ts.iloc[:-1], ts.iloc[1:], strict=True):
        expected = prev + delta
        if nxt > expected + pd.Timedelta(milliseconds=1):
            missing = int(round((nxt - expected) / delta))
            if missing > 0:
                gaps.append(
                    Gap(
                        start=ensure_utc(expected.to_pydatetime()),
                        end=ensure_utc(nxt.to_pydatetime()),
                        missing_bars=missing,
                    )
                )
    return gaps


def quality_report(
    df: pd.DataFrame, timeframe: str, *, now: pd.Timestamp | None = None
) -> QualityReport:
    """Inspect a frame for the defects we refuse to silently paper over."""
    if df.empty:
        return QualityReport(0, None, None, 0, False, 0, 0, 0, 0, [])
    ts = pd.to_datetime(df["ts"], utc=True)
    naive = 0
    if hasattr(df["ts"].dtype, "tz") and df["ts"].dtype.tz is None:
        naive = int(len(df))
    ohlc = int(
        (
            (df["high"] < df[["open", "close"]].max(axis=1))
            | (df["low"] > df[["open", "close"]].min(axis=1))
            | (df["high"] < df["low"])
        ).sum()
    )
    cutoff = now if now is not None else pd.Timestamp.now(tz="UTC")
    close_at = ts + pd.Timedelta(timeframe_delta(timeframe))
    future = int((close_at > cutoff).sum())
    first = ts.min().strftime("%Y-%m-%dT%H:%M:%SZ")
    last = ts.max().strftime("%Y-%m-%dT%H:%M:%SZ")
    return QualityReport(
        rows=int(len(df)),
        first_ts=first,
        last_ts=last,
        duplicate_ts=int(ts.duplicated().sum()),
        unsorted=bool(not ts.is_monotonic_increasing),
        ohlc_violations=ohlc,
        negative_volume=int((df["volume"] < 0).sum()),
        naive_or_non_utc=naive,
        future_bars=future,
        gaps=detect_gaps(df, timeframe),
    )
