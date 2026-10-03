from __future__ import annotations

import pytest
from pydantic import ValidationError

from trade_agent.core.paths import project_root
from trade_agent.strategies.engine import evaluate_row
from trade_agent.strategies.schema import load_spec, spec_from_dict

# project_root lives on Settings helper
from trade_agent.core.config import project_root


def test_bundled_spec_loads() -> None:
    spec = load_spec(project_root() / "config/strategies/london_sweep_long.yaml")
    assert spec.side == "long"
    assert spec.min_rr == 1.5
    assert spec.entry.all is not None


def test_group_requires_all_or_any() -> None:
    with pytest.raises(ValidationError):
        spec_from_dict({"name": "x", "side": "long", "entry": {}})


def test_evaluate_row() -> None:
    spec = spec_from_dict(
        {
            "name": "x",
            "side": "long",
            "entry": {
                "all": [
                    {"feature": "session_london", "op": "eq", "value": True},
                    {"feature": "structure_bias", "op": "eq", "value": 1},
                ]
            },
        }
    )
    import pandas as pd

    ok = pd.Series({"session_london": True, "structure_bias": 1})
    no = pd.Series({"session_london": False, "structure_bias": 1})
    assert evaluate_row(ok, spec)
    assert not evaluate_row(no, spec)
