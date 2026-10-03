"""Timeframe strings to UTC timedeltas. Used to drop still-open candles."""

from __future__ import annotations

from datetime import timedelta

_UNITS = {
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def timeframe_delta(timeframe: str) -> timedelta:
    """Parse ``1m``, ``5m``, ``15m``, ``1h``, ``4h``, ``1d`` into a timedelta.

    Raises:
        ValueError: unknown format.
    """
    tf = timeframe.strip().lower()
    if len(tf) < 2 or tf[-1] not in _UNITS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    try:
        n = int(tf[:-1])
    except ValueError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe}") from exc
    if n <= 0:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return timedelta(seconds=n * _UNITS[tf[-1]])


def expected_bar_count(start, end, timeframe: str) -> int:
    """Number of closed bars whose open is in ``[start, end)``."""
    delta = timeframe_delta(timeframe)
    seconds = (end - start).total_seconds()
    return max(int(seconds // delta.total_seconds()), 0)
