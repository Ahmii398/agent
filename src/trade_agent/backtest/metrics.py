"""Backtest metrics from closed trades and the equity curve."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from trade_agent.backtest.engine import Trade


@dataclass
class Metrics:
    trade_count: int
    net_profit: float
    profit_factor: float
    expectancy_r: float
    max_drawdown: float
    sharpe: float
    sortino: float
    win_rate: float
    avg_duration_bars: float


def compute_metrics(trades: list[Trade], equity_curve: list[float], initial_equity: float) -> Metrics:
    """Compute the Phase-4 metric set. Empty trade lists return zeros."""
    if not trades:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    pnls = np.array([t.pnl for t in trades], dtype=float)
    rs = np.array([t.r_multiple for t in trades], dtype=float)
    wins = pnls[pnls > 0].sum()
    losses = -pnls[pnls < 0].sum()
    pf = float(wins / losses) if losses > 0 else float("inf") if wins > 0 else 0.0
    eq = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak == 0, 1, peak)
    max_dd = float(dd.max()) if len(dd) else 0.0
    sharpe = _ratio(rs, downside=False)
    sortino = _ratio(rs, downside=True)
    return Metrics(
        trade_count=len(trades),
        net_profit=float(pnls.sum()),
        profit_factor=pf,
        expectancy_r=float(rs.mean()),
        max_drawdown=max_dd,
        sharpe=sharpe,
        sortino=sortino,
        win_rate=float((pnls > 0).mean()),
        avg_duration_bars=float(np.mean([t.bars_held for t in trades])),
    )


def _ratio(rs: np.ndarray, *, downside: bool) -> float:
    if len(rs) < 2:
        return 0.0
    mu = float(rs.mean())
    if downside:
        neg = rs[rs < 0]
        sigma = float(neg.std(ddof=1)) if len(neg) > 1 else 0.0
    else:
        sigma = float(rs.std(ddof=1))
    if sigma == 0:
        return 0.0
    return mu / sigma
