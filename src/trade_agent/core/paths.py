"""Filesystem layout under the configured data directory."""

from __future__ import annotations

from pathlib import Path


def ensure_data_layout(data_dir: Path) -> None:
    """Create cache, candle, and log directories if they do not exist."""
    for child in ("cache", "candles", "logs", "raw"):
        (data_dir / child).mkdir(parents=True, exist_ok=True)


def candle_path(data_dir: Path, exchange: str, symbol: str, timeframe: str) -> Path:
    """Parquet path for one symbol/timeframe. Symbol slashes become dashes."""
    safe = symbol.replace("/", "-")
    return data_dir / "candles" / exchange / safe / f"{timeframe}.parquet"


def cache_body_path(data_dir: Path, sha256: str) -> Path:
    """Content-addressed cache file for an HTTP body."""
    return data_dir / "cache" / sha256[:2] / sha256
