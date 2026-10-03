"""Walk-forward, OOS, Monte Carlo, sensitivity. Promote only if every gate passes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from trade_agent import __version__
from trade_agent.backtest.engine import run_backtest
from trade_agent.backtest.metrics import Metrics
from trade_agent.core.timeutil import utcnow_iso
from trade_agent.db.store import Store
from trade_agent.strategies.schema import StrategySpec


@dataclass
class Gate:
    name: str
    passed: bool
    observed: float | int | str
    threshold: float | int | str
    detail: str = ""


@dataclass
class ValidationReport:
    spec_name: str
    passed: bool
    gates: list[Gate] = field(default_factory=list)
    in_sample: Metrics | None = None
    oos: Metrics | None = None
    walk_forward: list[Metrics] = field(default_factory=list)
    experiment_id: int | None = None
    total_tested: int = 0


def validate_strategy(
    ohlcv,
    features,
    spec: StrategySpec,
    store: Store,
    *,
    thresholds: dict[str, Any],
    seed: int = 42,
    extra_frames: list[tuple[object, object]] | None = None,
) -> ValidationReport:
    """Run the full gate set and persist an experiment row (pass or fail)."""
    rng = np.random.default_rng(seed)
    gates: list[Gate] = []
    wf_cfg = thresholds.get("walk_forward", {})
    train_n = int(wf_cfg.get("train_bars", 700))
    test_n = int(wf_cfg.get("test_bars", 200))
    step_n = int(wf_cfg.get("step_bars", 200))

    is_res = run_backtest(ohlcv, features, spec)
    oos_slice = _tail_split(ohlcv, features, train_n)
    oos_res = run_backtest(oos_slice[0], oos_slice[1], spec) if oos_slice else None

    wf_metrics = _walk_forward(ohlcv, features, spec, train_n, test_n, step_n)
    mc = _monte_carlo(
        is_res.trades,
        int(thresholds.get("monte_carlo_paths", 400)),
        float(thresholds.get("monte_carlo_dd_quantile", 0.95)),
        rng,
    )
    sens = _sensitivity(ohlcv, features, spec, thresholds.get("sensitivity", {}))

    def gate(name: str, passed: bool, observed, threshold, detail: str = "") -> None:
        gates.append(Gate(name, passed, observed, threshold, detail))

    min_trades = int(thresholds.get("min_trades", 100))
    gate(
        "min_trades",
        is_res.metrics.trade_count >= min_trades,
        is_res.metrics.trade_count,
        min_trades,
    )
    gate(
        "profit_factor",
        is_res.metrics.profit_factor >= float(thresholds.get("min_profit_factor", 1.3)),
        round(is_res.metrics.profit_factor, 4),
        thresholds.get("min_profit_factor", 1.3),
    )
    gate(
        "expectancy_r",
        is_res.metrics.expectancy_r >= float(thresholds.get("min_expectancy_r", 0.2)),
        round(is_res.metrics.expectancy_r, 4),
        thresholds.get("min_expectancy_r", 0.2),
    )
    gate(
        "max_drawdown",
        is_res.metrics.max_drawdown <= float(thresholds.get("max_drawdown", 0.2)),
        round(is_res.metrics.max_drawdown, 4),
        thresholds.get("max_drawdown", 0.2),
    )
    gate(
        "sharpe",
        is_res.metrics.sharpe >= float(thresholds.get("min_sharpe", 0.5)),
        round(is_res.metrics.sharpe, 4),
        thresholds.get("min_sharpe", 0.5),
    )
    gate(
        "win_rate",
        is_res.metrics.win_rate >= float(thresholds.get("min_win_rate", 0.4)),
        round(is_res.metrics.win_rate, 4),
        thresholds.get("min_win_rate", 0.4),
    )
    if oos_res and oos_res.metrics:
        min_oos = float(thresholds.get("min_oos_profit_factor", 1.1))
        gate(
            "oos_profit_factor",
            oos_res.metrics.profit_factor >= min_oos and oos_res.metrics.trade_count > 0,
            round(oos_res.metrics.profit_factor, 4),
            min_oos,
            f"oos_trades={oos_res.metrics.trade_count}",
        )
    else:
        gate(
            "oos_profit_factor",
            False,
            0,
            thresholds.get("min_oos_profit_factor", 1.1),
            "no OOS window",
        )

    wf_ok = bool(wf_metrics) and all(m.profit_factor >= 1.0 and m.trade_count > 0 for m in wf_metrics)
    gate(
        "walk_forward_all_windows_pf_ge_1",
        wf_ok,
        len(wf_metrics),
        "all windows PF>=1 and trades>0",
        f"windows={[(m.trade_count, round(m.profit_factor, 3)) for m in wf_metrics]}",
    )
    gate(
        "monte_carlo_dd",
        mc["q"] <= float(thresholds.get("max_drawdown", 0.2)),
        round(mc["q"], 4),
        thresholds.get("max_drawdown", 0.2),
        f"paths={mc['paths']}",
    )
    gate(
        "sensitivity_no_sign_flip",
        sens["stable"],
        sens["positive"],
        "majority of nearby params keep E[R]>0",
        json.dumps(sens["grid"]),
    )

    if extra_frames:
        robust = True
        detail = []
        for other_ohlcv, other_feat in extra_frames:
            r = run_backtest(other_ohlcv, other_feat, spec)
            detail.append(
                {"trades": r.metrics.trade_count, "E_R": round(r.metrics.expectancy_r, 3)}
            )
            if r.metrics.trade_count == 0 or r.metrics.expectancy_r <= 0:
                robust = False
        gate("multi_symbol_expectancy", robust, detail, "E[R]>0 on every extra symbol")

    passed = all(g.passed for g in gates)
    report = ValidationReport(
        spec_name=spec.name,
        passed=passed,
        gates=gates,
        in_sample=is_res.metrics,
        oos=oos_res.metrics if oos_res else None,
        walk_forward=wf_metrics,
    )
    report.experiment_id, report.total_tested = _record_experiment(
        store, spec, ohlcv, seed, report
    )
    return report


def _tail_split(ohlcv, features, train_n: int):
    if len(ohlcv) <= train_n + 10:
        return None
    oos_o = ohlcv.iloc[train_n:].reset_index(drop=True)
    oos_f = features.iloc[train_n:].reset_index(drop=True)
    return oos_o, oos_f


def _walk_forward(ohlcv, features, spec, train_n, test_n, step_n) -> list[Metrics]:
    out: list[Metrics] = []
    start = 0
    n = len(ohlcv)
    while start + train_n + 10 <= n:
        test_end = min(n, start + train_n + test_n)
        # Evaluate only the OOS slice; parameters are not fit here (rule spec is fixed).
        sl = slice(start + train_n, test_end)
        if sl.start >= sl.stop:
            break
        res = run_backtest(
            ohlcv.iloc[sl].reset_index(drop=True),
            features.iloc[sl].reset_index(drop=True),
            spec,
        )
        out.append(res.metrics)
        start += step_n
        if start + train_n >= n:
            break
    return out


def _monte_carlo(trades, paths: int, q: float, rng: np.random.Generator) -> dict[str, float]:
    if not trades:
        return {"q": 1.0, "paths": 0}
    rs = np.array([t.r_multiple for t in trades], dtype=float)
    dds = []
    for _ in range(paths):
        shuffled = rng.permutation(rs)
        eq = np.cumsum(shuffled)
        peak = np.maximum.accumulate(eq)
        # R-space drawdown from a 0 start; convert to a positive fraction vs peak+eps
        dd = float(((peak - eq).max()) / (abs(peak).max() + 1e-9)) if len(eq) else 0.0
        dds.append(dd)
    return {"q": float(np.quantile(dds, q)), "paths": float(paths)}


def _sensitivity(ohlcv, features, spec: StrategySpec, cfg: dict[str, Any]) -> dict[str, Any]:
    r_values = cfg.get("r_values") or [spec.target.r]
    stops = cfg.get("time_stops") or [spec.time_stop_bars]
    grid = []
    positive = 0
    for r in r_values:
        for ts in stops:
            clone = spec.model_copy(deep=True)
            clone.target.r = float(r)
            clone.time_stop_bars = int(ts) if ts is not None else None
            m = run_backtest(ohlcv, features, clone).metrics
            grid.append(
                {"r": r, "time_stop": ts, "E_R": round(m.expectancy_r, 4), "n": m.trade_count}
            )
            if m.expectancy_r > 0 and m.trade_count > 0:
                positive += 1
    stable = positive >= max(1, (len(grid) + 1) // 2)
    return {"stable": stable, "positive": positive, "grid": grid}


def _record_experiment(store: Store, spec: StrategySpec, ohlcv, seed: int, report: ValidationReport):
    store.execute("UPDATE experiment_counter SET total_tested = total_tested + 1 WHERE id = 1")
    row = store.fetchone("SELECT total_tested FROM experiment_counter WHERE id=1")
    total = int(row["total_tested"])
    payload = spec.model_dump()
    cfg_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    data_range = "empty"
    if not ohlcv.empty:
        data_range = f"{ohlcv.iloc[0]['ts']}/{ohlcv.iloc[-1]['ts']}"
    fail = "; ".join(f"{g.name}={g.observed}" for g in report.gates if not g.passed)
    cur = store.execute(
        """
        INSERT INTO experiments (
            created_at, strategy_name, config_hash, data_range, code_version,
            random_seed, metrics_json, passed, fail_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utcnow_iso(),
            spec.name,
            cfg_hash,
            str(data_range),
            __version__,
            seed,
            json.dumps(
                {g.name: {"passed": g.passed, "observed": g.observed} for g in report.gates}
            ),
            int(report.passed),
            None if report.passed else fail,
        ),
    )
    return int(cur.lastrowid), total
