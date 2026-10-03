from __future__ import annotations

import pytest

from trade_agent.core.errors import MissingAPIKey
from trade_agent.llm.anthropic import AnthropicLLMClient


def test_anthropic_without_key_stops_and_names_variable(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingAPIKey) as exc:
        AnthropicLLMClient("claude-sonnet-4-5")
    assert exc.value.env_var == "ANTHROPIC_API_KEY"
    assert exc.value.phase == 7
    assert "console.anthropic.com" in str(exc.value)
