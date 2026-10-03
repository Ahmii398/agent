"""JSON/YAML strategy specs + rule engine. No generated Python."""

from trade_agent.strategies.engine import evaluate_row
from trade_agent.strategies.schema import StrategySpec, load_spec, spec_from_dict

__all__ = ["StrategySpec", "evaluate_row", "load_spec", "spec_from_dict"]
