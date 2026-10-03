from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from trade_agent.backtest.costs import Costs
from trade_agent.backtest.engine import run_backtest
from trade_agent.core.errors import RiskViolation
from trade_agent.strategies.schema import StrategySpec, spec_from_dict


def _ohlcv() -> pd.DataFrame:
    """Bar0 down, bar1 entry open=100, bar2 hits target 104, never stops."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.5, 100.5),
        (100.5, 105.0, 100.0, 104.0),
        (104.0, 104.5, 103.0, 103.5),
    ]
    return pd.DataFrame(
        {
            "ts": [start + timedelta(hours=i) for i in range(4)],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": 1.0,
        }
    )


def _always_long() -> tuple[pd.DataFrame, StrategySpec]:
    ohlcv = _ohlcv()
    feat = ohlcv.copy()
    feat["signal"] = True
    feat["last_swing_low"] = 98.0
    feat["atr"] = 1.0
    spec = spec_from_dict(
        {
            "name": "always",
            "side": "long",
            "entry": {"all": [{"feature": "signal", "op": "eq", "value": True}]},
            "stop": {"type": "structure", "field": "last_swing_low"},
            "target": {"type": "r_multiple", "r": 2.0},
            "time_stop_bars": 10,
            "min_rr": 1.0,
        }
    )
    return feat, spec


def test_fill_is_next_open_not_signal_close() -> None:
    ohlcv = _ohlcv()
    feat, spec = _always_long()
    costs = Costs(spread_bps=0, commission_bps=0, slippage_bps=0)
    res = run_backtest(ohlcv, feat, spec, costs=costs, initial_equity=10_000, risk_fraction=0.005)
    assert res.trades
    t = res.trades[0]
    assert t.entry == pytest.approx(float(ohlcv.iloc[1]["open"]))
    assert t.entry != pytest.approx(float(ohlcv.iloc[0]["close"])) or True
    # Signal close is 100, next open is 100 in this fixture — use a shifted fixture.
    ohlcv2 = ohlcv.copy()
    ohlcv2.loc[1, "open"] = 102.0
    res2 = run_backtest(ohlcv2, feat, spec, costs=costs, initial_equity=10_000, risk_fraction=0.005)
    assert res2.trades[0].entry == pytest.approx(102.0)
    assert res2.trades[0].signal_ts == ohlcv2.iloc[0]["ts"]


def test_same_bar_stop_and_target_counts_as_stop() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    ohlcv = pd.DataFrame(
        {
            "ts": [start + timedelta(hours=i) for i in range(3)],
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 110.0, 100.0],
            "low": [100.0, 90.0, 100.0],
            "close": [100.0, 100.0, 100.0],
            "volume": 1.0,
        }
    )
    feat = ohlcv.copy()
    feat["signal"] = [True, False, False]
    feat["last_swing_low"] = 95.0
    spec = spec_from_dict(
        {
            "name": "both",
            "side": "long",
            "entry": {"all": [{"feature": "signal", "op": "eq", "value": True}]},
            "stop": {"type": "structure", "field": "last_swing_low"},
            "target": {"type": "r_multiple", "r": 2.0},
            "min_rr": 1.0,
            "time_stop_bars": 5,
        }
    )
    costs = Costs(0, 0, 0)
    res = run_backtest(ohlcv, feat, spec, costs=costs)
    assert res.trades[0].reason == "stop_same_bar"
    assert res.trades[0].r_multiple < 0


def test_costs_reduce_pnl() -> None:
    ohlcv = _ohlcv()
    feat, spec = _always_long()
    free = run_backtest(ohlcv, feat, spec, costs=Costs(0, 0, 0))
    paid = run_backtest(ohlcv, feat, spec, costs=Costs(10, 10, 10))
    assert paid.trades[0].pnl < free.trades[0].pnl


def test_cannot_risk_more_than_hard_cap() -> None:
    ohlcv = _ohlcv()
    feat, spec = _always_long()
    with pytest.raises(RiskViolation):
        run_backtest(ohlcv, feat, spec, risk_fraction=0.05)


def test_leaky_same_bar_fill_would_differ() -> None:
    """Document the contract: filling at signal close is a leak and is not used."""
    ohlcv = _ohlcv()
    ohlcv.loc[0, "close"] = 90.0
    ohlcv.loc[1, "open"] = 100.0
    feat, spec = _always_long()
    feat["close"] = ohlcv["close"]
    res = run_backtest(ohlcv, feat, spec, costs=Costs(0, 0, 0))
    assert res.trades[0].entry == pytest.approx(100.0)
    assert res.trades[0].entry != pytest.approx(90.0)
