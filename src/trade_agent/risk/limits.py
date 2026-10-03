"""HARD-CODED risk limits. There is no setter and YAML cannot change these.

The improvement loop, config loader, and strategy specs have no import that
writes these values. ``LIMITS`` is a frozen dataclass; item assignment fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class HardLimits:
    max_risk_per_trade: float = 0.005  # 0.5% of equity
    max_daily_loss: float = 0.02
    max_drawdown: float = 0.10
    max_open_positions: int = 3
    news_blackout_minutes: int = 30
    kill_switch: bool = False


LIMITS = HardLimits()

# Immutable mapping snapshot taken at import. Guard reads this object, not YAML.
HARD_LIMITS = MappingProxyType(
    {
        "max_risk_per_trade": LIMITS.max_risk_per_trade,
        "max_daily_loss": LIMITS.max_daily_loss,
        "max_drawdown": LIMITS.max_drawdown,
        "max_open_positions": LIMITS.max_open_positions,
        "news_blackout_minutes": LIMITS.news_blackout_minutes,
        "kill_switch": LIMITS.kill_switch,
    }
)
