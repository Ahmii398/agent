"""Cost-aware backtester. No look-ahead, no repainting."""

from trade_agent.backtest.costs import Costs
from trade_agent.backtest.engine import BacktestResult, Trade, run_backtest
from trade_agent.backtest.metrics import Metrics

__all__ = ["BacktestResult", "Costs", "Metrics", "Trade", "run_backtest"]
