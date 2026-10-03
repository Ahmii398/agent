"""YAML + environment configuration.

Secrets are read from ``.env`` only. Risk numbers in YAML are display-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from trade_agent.core.paths import ensure_data_layout


class AppConfig(BaseModel):
    name: str = "trade-agent"
    timezone: str = "UTC"
    data_dir: str = "var"
    db_filename: str = "trade_agent.db"
    log_level: str = "INFO"
    random_seed: int = 42


class UniverseConfig(BaseModel):
    crypto: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    forex: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=lambda: ["1h", "4h", "1d"])


class LLMTaskConfig(BaseModel):
    provider: str = "ollama"
    model: str = "llama3.1"
    allow_tools: bool = True
    json_only: bool = False


class LLMPriceConfig(BaseModel):
    input: float = 0.0
    output: float = 0.0


class LLMConfig(BaseModel):
    monthly_budget_usd: float = 25.0
    tasks: dict[str, LLMTaskConfig] = Field(
        default_factory=lambda: {
            "reasoning": LLMTaskConfig(),
            "bulk": LLMTaskConfig(),
            "web_extract": LLMTaskConfig(allow_tools=False, json_only=True),
        }
    )
    prices: dict[str, LLMPriceConfig] = Field(default_factory=dict)


class CacheConfig(BaseModel):
    default_ttl_seconds: int = 3600


class ProviderConfig(BaseModel):
    enabled: bool = False
    needs_key: bool = True
    env_var: str | None = None
    signup_url: str | None = None
    needed_in_phase: int | None = None
    rate_limit_per_key: int = 60
    rate_limit_window_seconds: int = 60


class LiveTradingConfig(BaseModel):
    """YAML cannot enable live trading. See ``trade_agent.approval.flags``."""

    enabled: bool = False


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    live_trading: LiveTradingConfig = Field(default_factory=LiveTradingConfig)
    risk_display: dict[str, Any] = Field(default_factory=dict)
    config_path: Path | None = None

    @property
    def data_dir(self) -> Path:
        return Path(self.app.data_dir).resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.app.db_filename

    def price_for(self, provider: str, model: str) -> LLMPriceConfig:
        """Look up USD-per-1M-token prices; unknown models cost 0 and must be added."""
        return self.llm.prices.get(f"{provider}/{model}", LLMPriceConfig())


def project_root() -> Path:
    """Repository root (directory that contains ``pyproject.toml`` or cwd)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def load_settings(
    config_path: Path | None = None,
    *,
    data_dir: Path | None = None,
    load_env: bool = True,
) -> Settings:
    """Load YAML config, ``.env``, and create the data directory layout.

    Args:
        config_path: YAML file. Defaults to ``<repo>/config/default.yaml``.
        data_dir: Override ``app.data_dir`` (used by tests).
        load_env: When True, load ``.env`` from the project root if present.
    """
    root = project_root()
    if load_env:
        load_dotenv(root / ".env", override=False)

    path = config_path or (root / "config" / "default.yaml")
    raw: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config must be a mapping: {path}")
        raw = loaded

    settings = Settings.model_validate(raw)
    settings.config_path = path
    if data_dir is not None:
        settings.app.data_dir = str(Path(data_dir).resolve())
    ensure_data_layout(settings.data_dir)
    return settings
