from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from trade_agent.core.config import load_settings
from trade_agent.core.errors import RiskViolation
from trade_agent.risk.guard import RiskGuard
from trade_agent.risk.limits import HARD_LIMITS, LIMITS


def test_mapping_is_immutable() -> None:
    with pytest.raises(TypeError):
        HARD_LIMITS["max_risk_per_trade"] = 1.0  # type: ignore[index]


def test_dataclass_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        LIMITS.max_risk_per_trade = 1.0  # type: ignore[misc]


def test_guard_setattr_blocked(store) -> None:
    guard = RiskGuard(store)
    with pytest.raises(PermissionError):
        guard.limits = {}  # type: ignore[misc]


def test_yaml_cannot_weaken_limits(tmp_path: Path, store) -> None:
    cfg = tmp_path / "weak.yaml"
    cfg.write_text(
        "risk_display:\n  max_risk_per_trade: 0.50\n  max_daily_loss: 0.99\n",
        encoding="utf-8",
    )
    settings = load_settings(cfg, data_dir=tmp_path / "var", load_env=False)
    guard = RiskGuard(store)
    assert guard.limits["max_risk_per_trade"] == 0.005
    assert settings.risk_display["max_risk_per_trade"] == 0.50
    with pytest.raises(RiskViolation):
        guard.check_trade_risk(0.50)
    # Legal size still passes.
    guard.check_trade_risk(0.005)


def test_replacing_module_limits_does_not_affect_bound_guard(store, monkeypatch) -> None:
    import trade_agent.risk.limits as limits_mod

    monkeypatch.setattr(limits_mod, "HARD_LIMITS", {"max_risk_per_trade": 1.0})
    guard = RiskGuard(store)
    with pytest.raises(RiskViolation):
        guard.check_trade_risk(0.50)


def test_position_and_loss_caps(store) -> None:
    guard = RiskGuard(store)
    guard.check_open_positions(2)
    with pytest.raises(RiskViolation):
        guard.check_open_positions(3)
    with pytest.raises(RiskViolation):
        guard.check_daily_loss(0.02)
    with pytest.raises(RiskViolation):
        guard.check_drawdown(0.10)
