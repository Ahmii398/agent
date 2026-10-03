"""Run a YAML spec against stored candles and print metrics."""

from __future__ import annotations

from pathlib import Path

from trade_agent.backtest.engine import run_backtest
from trade_agent.core.config import Settings
from trade_agent.data.candles import CandleStore
from trade_agent.features.pipeline import compute_features
from trade_agent.strategies.schema import load_spec


def cmd_backtest(settings: Settings, args) -> int:
    spec = load_spec(Path(args.spec))
    candles = CandleStore(settings.data_dir)
    df = candles.load("binance", args.symbol, spec.timeframe)
    if df.empty:
        print(f"no candles for {args.symbol} {spec.timeframe}")
        return 2
    htf = candles.load("binance", args.symbol, args.htf)
    feat = compute_features(df, htf=htf if not htf.empty else None, htf_timeframe=args.htf)
    result = run_backtest(df, feat, spec, initial_equity=args.equity, risk_fraction=args.risk)
    m = result.metrics
    print(f"strategy={spec.name} symbol={args.symbol} tf={spec.timeframe}")
    print(
        f"trades={m.trade_count} net={m.net_profit:.2f} pf={m.profit_factor:.3f} "
        f"E[R]={m.expectancy_r:.3f} dd={m.max_drawdown:.3f} sharpe={m.sharpe:.3f} "
        f"sortino={m.sortino:.3f} win={m.win_rate:.3f} avg_bars={m.avg_duration_bars:.2f}"
    )
    for t in result.trades[: args.sample]:
        print(
            f"  {t.side} in={t.entry_ts.isoformat()} out={t.exit_ts.isoformat()} "
            f"R={t.r_multiple:.2f} pnl={t.pnl:.2f} reason={t.reason}"
        )
    if len(result.trades) > args.sample:
        print(f"  ... {len(result.trades) - args.sample} more trades")
    return 0
