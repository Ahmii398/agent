"""Local Ollama client (OpenAI-compatible ``/v1/chat/completions``).

Phase 1 implements the client shape and budget hook. Real calls start in Phase 7.
This module does not require a key.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from trade_agent.core.errors import TradeAgentError
from trade_agent.core.logging import get_logger
from trade_agent.core.security import WEB_EXTRACT_REQUIRED_KEYS, assert_json_schema
from trade_agent.interfaces.llm_client import (
    LLMClient,
    LLMRequest,
    LLMResponse,
    LLMTask,
    LLMUsage,
)

log = get_logger("llm.ollama")

DEFAULT_HOST = "http://127.0.0.1:11434"


class OllamaLLMClient(LLMClient):
    """Talk to a local Ollama OpenAI-compatible endpoint."""

    provider = "ollama"

    def __init__(self, model: str, host: str | None = None) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.task is LLMTask.WEB_EXTRACT and request.allow_tools:
            raise ValueError("web_extract calls must not enable tools")

        payload = {
            "model": self.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.task is LLMTask.WEB_EXTRACT or request.json_schema_keys:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.host}/v1/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise TradeAgentError(
                f"Ollama unreachable at {self.host}. "
                "Start Ollama locally or switch the task provider in config."
            ) from exc

        text = body["choices"][0]["message"]["content"]
        usage_raw = body.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
            completion_tokens=int(usage_raw.get("completion_tokens") or 0),
            cost_usd=0.0,
        )
        parsed = None
        if request.task is LLMTask.WEB_EXTRACT:
            parsed = assert_json_schema(
                text, request.json_schema_keys or WEB_EXTRACT_REQUIRED_KEYS
            )
        log.info("ollama model=%s task=%s", self.model, request.task.value)
        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            provider=self.provider,
            model=self.model,
        )
