"""Strategy specs are data, never generated Python."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class Compare(BaseModel):
    """One predicate against a feature column known at signal time."""

    feature: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in"]
    value: Any


class ConditionGroup(BaseModel):
    all: list[Compare] | None = None
    any: list[Compare] | None = None

    @model_validator(mode="after")
    def _one_combiner(self) -> ConditionGroup:
        if (self.all is None) == (self.any is None):
            raise ValueError("ConditionGroup needs exactly one of all/any")
        return self


class StopSpec(BaseModel):
    type: Literal["structure", "atr", "price"] = "structure"
    field: str | None = "last_swing_low"
    atr_mult: float | None = None
    value: float | None = None


class TargetSpec(BaseModel):
    type: Literal["r_multiple", "structure", "atr"] = "r_multiple"
    r: float = 2.0
    field: str | None = None
    atr_mult: float | None = None


class StrategySpec(BaseModel):
    name: str
    version: int = 1
    timeframe: str = "1h"
    side: Literal["long", "short"]
    entry: ConditionGroup
    stop: StopSpec = Field(default_factory=StopSpec)
    target: TargetSpec = Field(default_factory=TargetSpec)
    time_stop_bars: int | None = 48
    min_rr: float = 1.5
    notes: str = ""


def load_spec(path: Path) -> StrategySpec:
    """Load and validate a YAML/JSON strategy spec."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return StrategySpec.model_validate(raw)


def spec_from_dict(data: dict[str, Any]) -> StrategySpec:
    """Validate an in-memory spec (used by the improvement loop later)."""
    return StrategySpec.model_validate(data)
