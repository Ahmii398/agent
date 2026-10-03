from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from trade_agent.strategies.schema import spec_from_dict
from trade_agent.validation.suite import validate_strategy


def test_low_trade_count_is_not_promoted(store) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    n = 40
    ohlcv = pd.DataFrame(
        {
            "ts": [start + timedelta(hours=i) for i in range(n)],
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": 1.0,
        }
    )
    feat = ohlcv.copy()
    feat["signal"] = False
    spec = spec_from_dict(
        {
            "name": "never",
            "side": "long",
            "entry": {"all": [{"feature": "signal", "op": "eq", "value": True}]},
        }
    )
    report = validate_strategy(
        ohlcv,
        feat,
        spec,
        store,
        thresholds={"min_trades": 100, "monte_carlo_paths": 20},
        seed=1,
    )
    assert report.passed is False
    names = {g.name: g.passed for g in report.gates}
    assert names["min_trades"] is False
    assert report.total_tested == 1
    row = store.fetchone("SELECT total_tested FROM experiment_counter WHERE id=1")
    assert row["total_tested"] == 1
    exp = store.fetchone("SELECT passed, fail_reason FROM experiments ORDER BY id DESC")
    assert exp["passed"] == 0


def test_counter_increments_across_runs(store) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    ohlcv = pd.DataFrame(
        {
            "ts": [start + timedelta(hours=i) for i in range(12)],
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        }
    )
    feat = ohlcv.copy()
    feat["signal"] = False
    spec = spec_from_dict(
        {
            "name": "never2",
            "side": "short",
            "entry": {"all": [{"feature": "signal", "op": "eq", "value": True}]},
        }
    )
    validate_strategy(ohlcv, feat, spec, store, thresholds={"min_trades": 100}, seed=2)
    validate_strategy(ohlcv, feat, spec, store, thresholds={"min_trades": 100}, seed=3)
    assert store.fetchone("SELECT total_tested FROM experiment_counter")["total_tested"] == 2
