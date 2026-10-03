"""LLM client contract. Web-extract calls have no tools and return JSON only."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LLMTask(str, Enum):
    REASONING = "reasoning"
    BULK = "bulk"
    WEB_EXTRACT = "web_extract"


@dataclass
class LLMRequest:
    task: LLMTask
    messages: list[dict[str, str]]
    json_schema_keys: tuple[str, ...] | None = None
    max_tokens: int = 1024
    temperature: float = 0.2
    allow_tools: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


@dataclass
class LLMResponse:
    text: str
    parsed: dict[str, Any] | None
    usage: LLMUsage
    provider: str
    model: str
    stopped_by_budget: bool = False


class LLMClient(ABC):
    """Provider-specific completion. Budget is checked by the factory wrapper."""

    provider: str
    model: str

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Run one completion. Implementations must not log prompts that contain keys."""

    def supports_tools(self) -> bool:
        return False
