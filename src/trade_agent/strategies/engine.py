"""Interpret a StrategySpec against one feature row. No Python eval."""

from __future__ import annotations

import pandas as pd

from trade_agent.core.errors import SchemaError
from trade_agent.strategies.schema import Compare, ConditionGroup, StrategySpec

_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


def evaluate_row(row: pd.Series, spec: StrategySpec) -> bool:
    """True if the entry tree passes on this closed bar."""
    return _group(row, spec.entry)


def _group(row: pd.Series, group: ConditionGroup) -> bool:
    if group.all is not None:
        return all(_compare(row, c) for c in group.all)
    assert group.any is not None
    return any(_compare(row, c) for c in group.any)


def _compare(row: pd.Series, pred: Compare) -> bool:
    if pred.feature not in row.index:
        return False
    left = row[pred.feature]
    if pd.isna(left):
        return False
    try:
        return bool(_OPS[pred.op](left, pred.value))
    except TypeError:
        return False


def stop_price(row: pd.Series, spec: StrategySpec) -> float | None:
    """Stop level from information known at signal time."""
    stop = spec.stop
    if stop.type == "price":
        return None if stop.value is None else float(stop.value)
    if stop.type == "atr":
        atr = _num(row, "atr")
        close = _num(row, "close")
        if atr is None or close is None or not stop.atr_mult:
            return None
        return close - stop.atr_mult * atr if spec.side == "long" else close + stop.atr_mult * atr
    field = stop.field or ("last_swing_low" if spec.side == "long" else "last_swing_high")
    return _num(row, field)


def target_price(row: pd.Series, spec: StrategySpec, entry: float, stop: float) -> float | None:
    """Target from signal-time data. ``r_multiple`` uses planned entry/stop."""
    tgt = spec.target
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if tgt.type == "r_multiple":
        if spec.side == "long":
            return entry + tgt.r * risk
        return entry - tgt.r * risk
    if tgt.type == "atr":
        atr = _num(row, "atr")
        if atr is None or not tgt.atr_mult:
            return None
        return entry + tgt.atr_mult * atr if spec.side == "long" else entry - tgt.atr_mult * atr
    field = tgt.field
    if not field:
        raise SchemaError("structure target requires field")
    return _num(row, field)


def planned_rr(entry: float, stop: float, target: float, side: str) -> float | None:
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    reward = (target - entry) if side == "long" else (entry - target)
    return reward / risk


def _num(row: pd.Series, name: str) -> float | None:
    if name not in row.index:
        return None
    val = row[name]
    if pd.isna(val):
        return None
    return float(val)
