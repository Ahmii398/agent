"""Abstract broker. Live implementations stay behind a feature flag (Phase 9)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from trade_agent.approval.flags import LIVE_TRADING_ENABLED
from trade_agent.core.errors import LiveTradingDisabled


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Order:
    symbol: str
    side: Side
    qty: float
    price: float | None = None
    order_type: str = "market"


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: float
    price: float
    ts: datetime
    paper: bool


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    avg_price: float


class Broker(ABC):
    """Order routing. Subclasses must set ``is_paper``."""

    name: str
    is_paper: bool

    @abstractmethod
    def submit(self, order: Order) -> Fill:
        """Submit an order. Live brokers must call ``assert_live_allowed`` first."""

    @abstractmethod
    def cancel(self, order_id: str) -> None:
        """Cancel a working order."""

    @abstractmethod
    def positions(self) -> list[Position]:
        """Open positions."""

    @abstractmethod
    def equity(self) -> float:
        """Account equity in quote currency."""

    def assert_live_allowed(self) -> None:
        """Hard stop: live path is off until Phase 9 + explicit approval."""
        if not self.is_paper and not LIVE_TRADING_ENABLED:
            raise LiveTradingDisabled(
                "Live broker is disabled. Paper trading only. "
                "LIVE_TRADING_ENABLED is a source constant, not a config flag."
            )
