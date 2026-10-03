"""Deterministic LLM used in tests and Phase 1 verification. No network."""

from __future__ import annotations

import json

from trade_agent.core.security import WEB_EXTRACT_REQUIRED_KEYS, assert_json_schema
from trade_agent.interfaces.llm_client import (
    LLMClient,
    LLMRequest,
    LLMResponse,
    LLMTask,
    LLMUsage,
)


class DummyLLMClient(LLMClient):
    """Returns a canned briefing-shaped payload. Honors web-extract constraints."""

    provider = "dummy"
    model = "dummy-0"

    def __init__(self, canned_text: str | None = None) -> None:
        self.canned_text = canned_text or "NO_TRADE: insufficient edge"

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.task is LLMTask.WEB_EXTRACT:
            if request.allow_tools:
                raise ValueError("web_extract calls must not enable tools")
            parsed = {"summary": "neutral test extract", "sentiment": 0.0, "tags": ["test"]}
            assert_json_schema(parsed, request.json_schema_keys or WEB_EXTRACT_REQUIRED_KEYS)
            text = json.dumps(parsed)
        else:
            parsed = None
            text = self.canned_text
        usage = LLMUsage(prompt_tokens=8, completion_tokens=4, cost_usd=0.0)
        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            provider=self.provider,
            model=self.model,
        )
