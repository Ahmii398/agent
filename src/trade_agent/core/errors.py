"""Domain errors. Messages must never include secret material."""


class TradeAgentError(Exception):
    """Base error for the agent."""


class MissingAPIKey(TradeAgentError):
    """A required key pool is empty. Tells the operator which env var to fill."""

    def __init__(self, provider: str, env_var: str, signup_url: str, phase: int) -> None:
        self.provider = provider
        self.env_var = env_var
        self.signup_url = signup_url
        self.phase = phase
        super().__init__(
            f"No keys configured for provider={provider}. "
            f"Set {env_var} in .env (comma-separated pool). "
            f"Get a key at {signup_url}. Needed for phase {phase}."
        )


class AllKeysCoolingDown(TradeAgentError):
    """Every key in the pool is rate-limited."""


class BudgetExceeded(TradeAgentError):
    """Monthly LLM spend cap has been reached. Further LLM calls are refused."""


class RiskViolation(TradeAgentError):
    """A proposed action would break a hardcoded risk limit."""


class LiveTradingDisabled(TradeAgentError):
    """Live order path is compiled off. Paper trading only."""


class SchemaError(TradeAgentError):
    """JSON/YAML spec failed validation."""
