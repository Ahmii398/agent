"""CLI: validate a spec and print every gate."""

from __future__ import annotations

from pathlib import Path

from trade_agent.core.config import Settings
from trade_agent.data.candles import CandleStore
from trade_agent.db.store import Store
from trade_agent.features.pipeline import compute_features
from trade_agent.strategies.schema import load_spec
from trade_agent.validation.suite import validate_strategy


def cmd_validate(settings: Settings, args) -> int:
    spec = load_spec(Path(args.spec))
    candles = CandleStore(settings.data_dir)
    with Store(settings.db_path) as store:
        store.migrate()
        frames = []
        extra = []
        for symbol in args.symbol:
            df = candles.load("binance", symbol, spec.timeframe)
            if df.empty:
                print(f"skip {symbol}: no candles")
                continue
            htf = candles.load("binance", symbol, args.htf)
            feat = compute_features(df, htf=htf if not htf.empty else None, htf_timeframe=args.htf)
            frames.append((symbol, df, feat))
        if not frames:
            return 2
        primary = frames[0]
        extra = [(df, feat) for _, df, feat in frames[1:]]
        thresholds = settings.validation or {
            "min_trades": 100,
            "min_profit_factor": 1.3,
            "min_expectancy_r": 0.2,
            "max_drawdown": 0.2,
            "min_sharpe": 0.5,
            "min_win_rate": 0.4,
            "min_oos_profit_factor": 1.1,
            "monte_carlo_paths": 200,
        }
        report = validate_strategy(
            primary[1],
            primary[2],
            spec,
            store,
            thresholds=thresholds,
            seed=settings.app.random_seed,
            extra_frames=extra or None,
        )
    print(
        f"strategy={report.spec_name} passed={report.passed} "
        f"experiment={report.experiment_id} total_tested={report.total_tested}"
    )
    for g in report.gates:
        flag = "PASS" if g.passed else "FAIL"
        print(f"  {flag} {g.name} observed={g.observed} threshold={g.threshold} {g.detail}")
    return 0 if report.passed else 3
