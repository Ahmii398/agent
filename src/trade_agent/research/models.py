"""Research item shape. Fetched text is untrusted data, never instructions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ResearchItem:
    source: str
    fetched_at: datetime
    asset_tags: list[str]
    reliability: float
    title: str = ""
    summary: str = ""
    url: str | None = None
    published_at: datetime | None = None
    sentiment: float | None = None
    kind: str = "news"
    extra: dict[str, Any] = field(default_factory=dict)
    is_high_impact_event: bool = False
    published_at_unknown: bool = False
    content_sha256: str = ""
    dedupe_key: str = ""


HIGH_IMPACT_TERMS = (
    "nfp",
    "nonfarm",
    "cpi",
    "fomc",
    "interest rate",
    "fed decision",
    "ecb",
    "boe",
    "gdp",
    "payroll",
    "pce",
    "jackson hole",
    "rate hike",
    "rate cut",
)

RELIABILITY = {
    "fred": 0.95,
    "cftc": 0.90,
    "finnhub_calendar": 0.85,
    "goldapi": 0.80,
    "twelve_data": 0.78,
    "coingecko": 0.75,
    "alpha_vantage": 0.72,
    "finnhub_news": 0.70,
    "newsapi": 0.65,
    "fear_greed": 0.60,
    "bitget": 0.70,
    "rss": 0.55,
    "web": 0.35,
}
