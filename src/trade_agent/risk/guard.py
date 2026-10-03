"""Risk guard. Limits are bound at import from ``limits.HARD_LIMITS``."""

from __future__ import annotations

from types import MappingProxyType

from trade_agent.core.errors import RiskViolation
from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import utcnow_iso
from trade_agent.db.store import Store
from trade_agent.risk.limits import HARD_LIMITS

log = get_logger("risk")

# Bound at import so replacing ``trade_agent.risk.limits.HARD_LIMITS`` later
# does not change what this module enforces.
_BOUND = MappingProxyType(dict(HARD_LIMITS))


class RiskGuard:
    """Immutable risk checks. Instance attributes cannot be assigned."""

    def __init__(self, store: Store | None = None) -> None:
        object.__setattr__(self, "_store", store)

    def __setattr__(self, name: str, value: object) -> None:
        raise PermissionError("RiskGuard attributes are immutable")

    def __delattr__(self, name: str) -> None:
        raise PermissionError("RiskGuard attributes are immutable")

    @property
    def limits(self) -> MappingProxyType:
        return _BOUND

    def check_trade_risk(self, risk_fraction: float) -> None:
        """Refuse a trade that risks more than the hardcoded per-trade cap."""
        cap = float(_BOUND["max_risk_per_trade"])
        allowed = risk_fraction <= cap + 1e-15
        self._audit("check_trade_risk", allowed, f"risk={risk_fraction} cap={cap}")
        if not allowed:
            raise RiskViolation(f"per-trade risk {risk_fraction} exceeds hard cap {cap}")

    def check_open_positions(self, current_open: int) -> None:
        cap = int(_BOUND["max_open_positions"])
        allowed = current_open < cap
        self._audit("check_open_positions", allowed, f"open={current_open} cap={cap}")
        if not allowed:
            raise RiskViolation(f"open positions {current_open} at hard cap {cap}")

    def check_daily_loss(self, daily_loss_fraction: float) -> None:
        cap = float(_BOUND["max_daily_loss"])
        allowed = daily_loss_fraction < cap
        self._audit("check_daily_loss", allowed, f"loss={daily_loss_fraction} cap={cap}")
        if not allowed:
            raise RiskViolation(f"daily loss {daily_loss_fraction} exceeds hard cap {cap}")

    def check_drawdown(self, drawdown_fraction: float) -> None:
        cap = float(_BOUND["max_drawdown"])
        allowed = drawdown_fraction < cap
        self._audit("check_drawdown", allowed, f"dd={drawdown_fraction} cap={cap}")
        if not allowed:
            raise RiskViolation(f"drawdown {drawdown_fraction} exceeds hard cap {cap}")

    def kill_switch_engaged(self) -> bool:
        return bool(_BOUND["kill_switch"])

    def _audit(self, action: str, allowed: bool, reason: str) -> None:
        store = object.__getattribute__(self, "_store")
        if store is None:
            return
        store.execute(
            "INSERT INTO risk_audit (created_at, action, allowed, reason) VALUES (?, ?, ?, ?)",
            (utcnow_iso(), action, int(allowed), reason),
        )
        if not allowed:
            log.warning("risk reject action=%s %s", action, reason)
