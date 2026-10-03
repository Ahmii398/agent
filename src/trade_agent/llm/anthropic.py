"""Anthropic Messages API client.

Requires ``ANTHROPIC_API_KEY``. Phase 1 will refuse to call if the key is
missing rather than inventing a request. Real briefings start in Phase 7.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from trade_agent.core.errors import MissingAPIKey, TradeAgentError
from trade_agent.core.logging import get_logger
from trade_agent.core.security import WEB_EXTRACT_REQUIRED_KEYS, assert_json_schema
from trade_agent.interfaces.llm_client import (
    LLMClient,
    LLMRequest,
    LLMResponse,
    LLMTask,
    LLMUsage,
)

log = get_logger("llm.anthropic")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class AnthropicLLMClient(LLMClient):
    """Anthropic API. The key is read from the environment and never logged."""

    provider = "anthropic"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise MissingAPIKey(
                provider="anthropic",
                env_var="ANTHROPIC_API_KEY",
                signup_url="https://console.anthropic.com/settings/keys",
                phase=7,
            )

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.task is LLMTask.WEB_EXTRACT and request.allow_tools:
            raise ValueError("web_extract calls must not enable tools")

        system = " ".join(m["content"] for m in request.messages if m.get("role") == "system")
        user_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in request.messages
            if m.get("role") in ("user", "assistant")
        ]
        payload: dict = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": user_messages or [{"role": "user", "content": ""}],
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=data,
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Do not include response body; it can echo headers.
            raise TradeAgentError(f"Anthropic HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise TradeAgentError("Anthropic endpoint unreachable") from exc

        text = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        )
        usage_raw = body.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("input_tokens") or 0),
            completion_tokens=int(usage_raw.get("output_tokens") or 0),
            cost_usd=0.0,  # filled by BudgetedLLM
        )
        parsed = None
        if request.task is LLMTask.WEB_EXTRACT:
            parsed = assert_json_schema(
                text, request.json_schema_keys or WEB_EXTRACT_REQUIRED_KEYS
            )
        log.info("anthropic model=%s task=%s", self.model, request.task.value)
        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            provider=self.provider,
            model=self.model,
        )
