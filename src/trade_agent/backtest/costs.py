"""Explicit trading costs. Applied at entry and exit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Costs:
    spread_bps: float = 1.0
    commission_bps: float = 4.0
    slippage_bps: float = 1.0

    def half_spread(self, price: float) -> float:
        return price * (self.spread_bps / 10_000.0) / 2.0

    def slip(self, price: float) -> float:
        return price * (self.slippage_bps / 10_000.0)

    def commission(self, notional: float) -> float:
        return abs(notional) * (self.commission_bps / 10_000.0)

    def fill(self, raw_price: float, side: str, *, is_entry: bool) -> float:
        """Worse-than-mid fill: long pays up on entry, down on exit."""
        adverse = self.half_spread(raw_price) + self.slip(raw_price)
        if side == "long":
            return raw_price + adverse if is_entry else raw_price - adverse
        return raw_price - adverse if is_entry else raw_price + adverse
