"""Bar backtester. Signals on close[t], fills on open[t+1]. No look-ahead."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from trade_agent.backtest.costs import Costs
from trade_agent.backtest.metrics import Metrics, compute_metrics
from trade_agent.core.errors import RiskViolation
from trade_agent.risk.limits import HARD_LIMITS
from trade_agent.strategies.engine import evaluate_row, planned_rr, stop_price, target_price
from trade_agent.strategies.schema import StrategySpec


@dataclass
class Trade:
    side: str
    signal_ts: datetime
    entry_ts: datetime
    exit_ts: datetime
    entry: float
    exit: float
    stop: float
    target: float
    qty: float
    r_multiple: float
    pnl: float
    mae: float
    mfe: float
    bars_held: int
    reason: str


@dataclass
class BacktestResult:
    spec_name: str
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    metrics: Metrics | None = None


def run_backtest(
    ohlcv: pd.DataFrame,
    features: pd.DataFrame,
    spec: StrategySpec,
    *,
    costs: Costs | None = None,
    initial_equity: float = 10_000.0,
    risk_fraction: float = 0.005,
    max_trades: int | None = None,
) -> BacktestResult:
    """Simulate one position at a time with fixed-fraction risk.

    ``risk_fraction`` cannot exceed the hardcoded per-trade cap.
    """
    cap = float(HARD_LIMITS["max_risk_per_trade"])
    if risk_fraction > cap + 1e-15:
        raise RiskViolation(f"backtest risk_fraction {risk_fraction} > hard cap {cap}")
    costs = costs or Costs()
    if len(ohlcv) != len(features):
        raise ValueError("ohlcv and features must be aligned")
    n = len(ohlcv)
    equity = initial_equity
    curve = [equity]
    trades: list[Trade] = []
    i = 0
    while i < n - 1:
        row = features.iloc[i]
        if evaluate_row(row, spec):
            raw_entry = float(ohlcv.iloc[i + 1]["open"])
            entry = costs.fill(raw_entry, spec.side, is_entry=True)
            stop = stop_price(row, spec)
            if stop is None:
                i += 1
                continue
            target = target_price(row, spec, entry, stop)
            if target is None:
                i += 1
                continue
            rr = planned_rr(entry, stop, target, spec.side)
            if rr is None or rr < spec.min_rr:
                i += 1
                continue
            risk_dist = abs(entry - stop)
            if risk_dist <= 0:
                i += 1
                continue
            qty = (equity * risk_fraction) / risk_dist
            trade = _simulate_trade(
                ohlcv,
                spec.side,
                signal_i=i,
                entry_i=i + 1,
                entry=entry,
                stop=stop,
                target=target,
                qty=qty,
                costs=costs,
                time_stop=spec.time_stop_bars,
            )
            equity += trade.pnl
            curve.append(equity)
            trades.append(trade)
            if max_trades is not None and len(trades) >= max_trades:
                break
            i = trade.bars_held + i + 1
            continue
        i += 1
        curve.append(equity)
    result = BacktestResult(spec_name=spec.name, trades=trades, equity_curve=curve)
    result.metrics = compute_metrics(trades, curve, initial_equity)
    return result


def _simulate_trade(
    ohlcv: pd.DataFrame,
    side: str,
    *,
    signal_i: int,
    entry_i: int,
    entry: float,
    stop: float,
    target: float,
    qty: float,
    costs: Costs,
    time_stop: int | None,
) -> Trade:
    mae = 0.0
    mfe = 0.0
    exit_i = entry_i
    reason = "eod"
    n = len(ohlcv)
    last = n - 1
    end = last if time_stop is None else min(last, entry_i + time_stop)
    for j in range(entry_i, end + 1):
        bar = ohlcv.iloc[j]
        high, low = float(bar["high"]), float(bar["low"])
        if side == "long":
            mae = max(mae, entry - low)
            mfe = max(mfe, high - entry)
            hit_stop = low <= stop
            hit_tgt = high >= target
        else:
            mae = max(mae, high - entry)
            mfe = max(mfe, entry - low)
            hit_stop = high >= stop
            hit_tgt = low <= target
        if hit_stop and hit_tgt:
            # Conservative: same-bar both-touch counts as stop.
            reason = "stop_same_bar"
            exit_i = j
            raw_exit = stop
            break
        if hit_stop:
            reason = "stop"
            exit_i = j
            raw_exit = stop
            break
        if hit_tgt:
            reason = "target"
            exit_i = j
            raw_exit = target
            break
        if j == end:
            reason = "time_stop" if time_stop is not None and end < last else "eod"
            exit_i = j
            raw_exit = float(bar["close"])
            break
    fill_exit = costs.fill(raw_exit, side, is_entry=False)
    notional_in = entry * qty
    notional_out = fill_exit * qty
    commission = costs.commission(notional_in) + costs.commission(notional_out)
    gross = (fill_exit - entry) * qty if side == "long" else (entry - fill_exit) * qty
    pnl = gross - commission
    risk = abs(entry - stop) * qty
    r_mult = pnl / risk if risk else 0.0
    return Trade(
        side=side,
        signal_ts=_ts(ohlcv, signal_i),
        entry_ts=_ts(ohlcv, entry_i),
        exit_ts=_ts(ohlcv, exit_i),
        entry=entry,
        exit=fill_exit,
        stop=stop,
        target=target,
        qty=qty,
        r_multiple=r_mult,
        pnl=pnl,
        mae=mae,
        mfe=mfe,
        bars_held=exit_i - entry_i + 1,
        reason=reason,
    )


def _ts(df: pd.DataFrame, i: int):
    val = df.iloc[i]["ts"]
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime()
    return val
