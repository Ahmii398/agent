"""Budget-enforcing LLM wrapper and per-task factory."""

from __future__ import annotations

from trade_agent.core.config import Settings
from trade_agent.core.errors import TradeAgentError
from trade_agent.core.security import WEB_EXTRACT_SYSTEM_PROMPT
from trade_agent.interfaces.llm_client import (
    LLMClient,
    LLMRequest,
    LLMResponse,
    LLMTask,
    LLMUsage,
)
from trade_agent.llm.anthropic import AnthropicLLMClient
from trade_agent.llm.budget import LLMBudget
from trade_agent.llm.dummy import DummyLLMClient
from trade_agent.llm.ollama import OllamaLLMClient


class BudgetedLLM(LLMClient):
    """Wrap any ``LLMClient`` with a monthly spend cap.

    Web-extract requests are forced to no-tools + JSON schema regardless of
    what the caller passed.
    """

    def __init__(self, inner: LLMClient, budget: LLMBudget) -> None:
        self.inner = inner
        self.budget = budget
        self.provider = inner.provider
        self.model = inner.model

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.task is LLMTask.WEB_EXTRACT:
            request = LLMRequest(
                task=request.task,
                messages=_ensure_web_system(request.messages),
                json_schema_keys=request.json_schema_keys or ("summary", "sentiment", "tags"),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                allow_tools=False,
                metadata=request.metadata,
            )
        # Refuse before the network call. Token estimate is conservative (chars/4).
        est_prompt = sum(len(m.get("content", "")) for m in request.messages) // 4
        est_cost = self.budget.estimate_cost(
            self.provider, self.model, est_prompt, request.max_tokens
        )
        self.budget.assert_can_spend(est_cost)

        response = self.inner.generate(request)
        cost = response.usage.cost_usd
        if cost == 0.0:
            cost = self.budget.estimate_cost(
                response.provider,
                response.model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
        usage = LLMUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=cost,
        )
        self.budget.record(
            provider=response.provider,
            model=response.model,
            task=request.task.value,
            usage=usage,
        )
        return LLMResponse(
            text=response.text,
            parsed=response.parsed,
            usage=usage,
            provider=response.provider,
            model=response.model,
        )


def build_llm_client(
    settings: Settings,
    budget: LLMBudget,
    task: LLMTask,
    *,
    dummy: bool = False,
) -> BudgetedLLM:
    """Select the configured provider for ``task`` and wrap it with the budget."""
    if dummy:
        return BudgetedLLM(DummyLLMClient(), budget)

    task_cfg = settings.llm.tasks.get(task.value)
    if task_cfg is None:
        raise TradeAgentError(f"No LLM task config for {task.value}")
    provider = task_cfg.provider.lower()
    model = task_cfg.model
    if provider == "ollama":
        inner: LLMClient = OllamaLLMClient(model)
    elif provider == "anthropic":
        inner = AnthropicLLMClient(model)
    elif provider == "dummy":
        inner = DummyLLMClient()
    else:
        raise TradeAgentError(f"Unknown LLM provider: {provider}")
    return BudgetedLLM(inner, budget)


def _ensure_web_system(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if messages and messages[0].get("role") == "system":
        return messages
    return [{"role": "system", "content": WEB_EXTRACT_SYSTEM_PROMPT}, *messages]
