"""Abstract market-data provider. Implementations live in ``trade_agent.data``."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OHLCVBar:
    """One UTC candle. ``ts`` is the open time."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Gap:
    """Missing closed-candle interval detected in stored data."""

    start: datetime
    end: datetime
    missing_bars: int


class DataProvider(ABC):
    """Historical + streaming OHLCV. All timestamps must be UTC-aware."""

    name: str

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Return closed candles in ``[start, end)`` with no look-ahead."""

    @abstractmethod
    def detect_gaps(
        self,
        bars: list[OHLCVBar],
        timeframe: str,
    ) -> list[Gap]:
        """Find missing bars given an expected timeframe."""

    def stream_ohlcv(
        self,
        symbol: str,
        timeframe: str,
    ) -> Iterator[OHLCVBar]:
        """Yield closed candles as they form. Optional for REST-only providers."""
        raise NotImplementedError(f"{self.name} does not implement streaming")

    def available_symbols(self) -> list[str]:
        return []

    def extra_snapshot(self, symbol: str) -> dict[str, Any]:
        """Optional derivatives / book snapshot. Default empty."""
        return {}
