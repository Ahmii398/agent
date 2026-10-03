"""Parquet candle store. UTC only, no still-open (look-ahead) bars."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from trade_agent.core.paths import candle_path
from trade_agent.core.timeutil import ensure_utc, utcnow
from trade_agent.data.timeframes import timeframe_delta
from trade_agent.interfaces.data_provider import OHLCVBar

COLUMNS = ("ts", "open", "high", "low", "close", "volume")


def bars_to_frame(bars: list[OHLCVBar]) -> pd.DataFrame:
    """Convert interface bars to a validated OHLCV frame."""
    if not bars:
        return empty_frame()
    df = pd.DataFrame(
        {
            "ts": [b.ts for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )
    return normalize_frame(df)


def frame_to_bars(df: pd.DataFrame) -> list[OHLCVBar]:
    """Convert a validated frame back to ``OHLCVBar`` rows."""
    out: list[OHLCVBar] = []
    for row in df.itertuples(index=False):
        ts = row.ts.to_pydatetime() if hasattr(row.ts, "to_pydatetime") else row.ts
        out.append(
            OHLCVBar(
                ts=ensure_utc(ts),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
        )
    return out


def empty_frame() -> pd.DataFrame:
    """Empty OHLCV frame with the canonical dtypes."""
    return pd.DataFrame(
        {
            "ts": pd.DatetimeIndex([], tz="UTC"),
            "open": pd.Series(dtype="float64"),
            "high": pd.Series(dtype="float64"),
            "low": pd.Series(dtype="float64"),
            "close": pd.Series(dtype="float64"),
            "volume": pd.Series(dtype="float64"),
        }
    )


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Sort, de-dupe, force UTC, keep canonical columns."""
    if df.empty:
        return empty_frame()
    out = df.loc[:, list(COLUMNS)].copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = out[col].astype("float64")
    out = out.drop_duplicates(subset=["ts"], keep="first")
    out = out.sort_values("ts").reset_index(drop=True)
    return out


def drop_unclosed(df: pd.DataFrame, timeframe: str, as_of: datetime | None = None) -> pd.DataFrame:
    """Remove bars whose close time is still in the future relative to ``as_of``.

    A bar opened at ``ts`` closes at ``ts + timeframe``. Including it before
    that instant is look-ahead. This is the data-layer leak guard.
    """
    if df.empty:
        return df
    when = ensure_utc(as_of) if as_of is not None else utcnow()
    close_at = df["ts"] + pd.Timedelta(timeframe_delta(timeframe))
    cutoff = pd.Timestamp(when)
    return df.loc[close_at <= cutoff].reset_index(drop=True)


def merge_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    """Concatenate frames, keeping the earliest copy of each timestamp."""
    nonempty = [normalize_frame(f) for f in frames if f is not None and not f.empty]
    if not nonempty:
        return empty_frame()
    return normalize_frame(pd.concat(nonempty, ignore_index=True))


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    """Write canonical OHLCV parquet. Parent dirs are created."""
    path.parent.mkdir(parents=True, exist_ok=True)
    normalize_frame(df).to_parquet(path, index=False)


def read_parquet(path: Path) -> pd.DataFrame:
    """Read parquet or return an empty frame if the file is missing."""
    if not path.exists():
        return empty_frame()
    return normalize_frame(pd.read_parquet(path))


class CandleStore:
    """On-disk Parquet store keyed by exchange / symbol / timeframe."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def path(self, exchange: str, symbol: str, timeframe: str) -> Path:
        return candle_path(self.data_dir, exchange, symbol, timeframe)

    def load(self, exchange: str, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load stored candles (may be empty)."""
        return read_parquet(self.path(exchange, symbol, timeframe))

    def save(self, exchange: str, symbol: str, timeframe: str, df: pd.DataFrame) -> Path:
        """Overwrite the parquet file with ``df`` (normalized)."""
        path = self.path(exchange, symbol, timeframe)
        write_parquet(path, df)
        return path

    def upsert(self, exchange: str, symbol: str, timeframe: str, df: pd.DataFrame) -> pd.DataFrame:
        """Merge ``df`` into the existing file and return the combined frame."""
        combined = merge_frames(self.load(exchange, symbol, timeframe), df)
        self.save(exchange, symbol, timeframe, combined)
        return combined
