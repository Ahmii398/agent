"""Monthly LLM spend cap. Further calls are refused once the cap is hit."""

from __future__ import annotations

from trade_agent.core.config import Settings
from trade_agent.core.errors import BudgetExceeded
from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import utcnow, utcnow_iso, year_month
from trade_agent.db.store import Store
from trade_agent.interfaces.llm_client import LLMUsage

log = get_logger("llm.budget")


class LLMBudget:
    """Persisted monthly budget. Thread-hostile; one writer expected."""

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self._ensure_month()

    @property
    def cap_usd(self) -> float:
        return float(self.settings.llm.monthly_budget_usd)

    @property
    def month(self) -> str:
        return year_month(utcnow())

    def spent_usd(self) -> float:
        row = self.store.fetchone(
            "SELECT spent_usd FROM llm_monthly_budget WHERE year_month = ?",
            (self.month,),
        )
        return float(row["spent_usd"]) if row else 0.0

    def remaining_usd(self) -> float:
        return max(self.cap_usd - self.spent_usd(), 0.0)

    def can_spend(self, estimated_cost_usd: float) -> bool:
        """True if ``estimated_cost_usd`` fits under the remaining monthly cap."""
        return self.spent_usd() + estimated_cost_usd <= self.cap_usd + 1e-12

    def assert_can_spend(self, estimated_cost_usd: float) -> None:
        """Raise ``BudgetExceeded`` and persist a stopped row if the cap is hit."""
        if self.can_spend(estimated_cost_usd):
            return
        self.store.execute(
            """
            INSERT INTO llm_usage (
                created_at, year_month, provider, model, task,
                prompt_tokens, completion_tokens, cost_usd, stopped_by_budget
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 1)
            """,
            (utcnow_iso(), self.month, "-", "-", "blocked"),
        )
        log.warning(
            "LLM budget cap hit month=%s spent=%.6f cap=%.6f",
            self.month,
            self.spent_usd(),
            self.cap_usd,
        )
        raise BudgetExceeded(
            f"LLM monthly budget exhausted: spent={self.spent_usd():.4f} "
            f"cap={self.cap_usd:.4f} month={self.month}"
        )

    def record(
        self,
        *,
        provider: str,
        model: str,
        task: str,
        usage: LLMUsage,
    ) -> None:
        """Add one call's tokens and cost to the monthly ledger."""
        self._ensure_month()
        self.store.execute(
            """
            INSERT INTO llm_usage (
                created_at, year_month, provider, model, task,
                prompt_tokens, completion_tokens, cost_usd, stopped_by_budget
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                utcnow_iso(),
                self.month,
                provider,
                model,
                task,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.cost_usd,
            ),
        )
        self.store.execute(
            """
            UPDATE llm_monthly_budget
            SET spent_usd = spent_usd + ?
            WHERE year_month = ?
            """,
            (usage.cost_usd, self.month),
        )
        log.info(
            "llm usage provider=%s model=%s task=%s prompt=%s completion=%s cost=%.6f remaining=%.6f",
            provider,
            model,
            task,
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.cost_usd,
            self.remaining_usd(),
        )

    def estimate_cost(self, provider: str, model: str, prompt: int, completion: int) -> float:
        """USD cost from configured per-1M-token prices."""
        price = self.settings.price_for(provider, model)
        return (prompt * price.input + completion * price.output) / 1_000_000.0

    def _ensure_month(self) -> None:
        row = self.store.fetchone(
            "SELECT year_month FROM llm_monthly_budget WHERE year_month = ?",
            (self.month,),
        )
        if row is None:
            self.store.execute(
                "INSERT INTO llm_monthly_budget (year_month, cap_usd, spent_usd) VALUES (?, ?, 0)",
                (self.month, self.cap_usd),
            )
