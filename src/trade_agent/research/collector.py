"""Per-asset research collection. Fetched text cannot change config or risk."""

from __future__ import annotations

from dataclasses import dataclass, field

from trade_agent.approval.flags import LIVE_TRADING_ENABLED
from trade_agent.core.config import Settings
from trade_agent.core.keys import KeyPool
from trade_agent.core.logging import get_logger
from trade_agent.db.store import Store
from trade_agent.research.http import CachedHTTP
from trade_agent.research.models import ResearchItem
from trade_agent.research.sources_keyed import (
    collect_alpha_vantage,
    collect_bitget,
    collect_finnhub,
    collect_fred,
    collect_goldapi,
    collect_newsapi,
    collect_twelve_data,
)
from trade_agent.research.sources_public import (
    collect_cftc,
    collect_coingecko,
    collect_fear_greed,
    collect_rss,
)
from trade_agent.research.store import upsert_item
from trade_agent.research.web import collect_web
from trade_agent.risk.limits import HARD_LIMITS

log = get_logger("research.collect")


@dataclass
class CollectReport:
    inserted: int = 0
    skipped: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def asset_tags_from_universe(settings: Settings) -> list[str]:
    tags = []
    for sym in settings.universe.crypto + settings.universe.forex:
        tags.append(sym.split("/")[0].upper())
    return sorted(set(tags)) or ["BTC", "ETH"]


def collect_all(
    settings: Settings, store: Store, *, assets: list[str] | None = None
) -> CollectReport:
    """Run structured sources first, then a tiny robots-respecting web allowlist."""
    if LIVE_TRADING_ENABLED:
        raise RuntimeError("collector refuses to run while live trading is enabled")
    _ = dict(HARD_LIMITS)  # bind; collector has no write path

    assets = assets or asset_tags_from_universe(settings)
    http = CachedHTTP(store, settings.data_dir, default_ttl=settings.cache.default_ttl_seconds)
    report = CollectReport()

    def run(name: str, fn) -> list[ResearchItem]:
        try:
            items = fn()
            report.by_source[name] = len(items)
            return items
        except Exception as exc:
            report.errors[name] = f"{type(exc).__name__}"
            log.warning("source_fail name=%s err=%s", name, type(exc).__name__)
            return []

    def pool(provider: str, env_var: str, **kw) -> KeyPool | None:
        cfg = settings.providers.get(provider)
        if cfg is not None and not cfg.enabled:
            report.errors[provider] = "disabled"
            return None
        p = KeyPool(
            provider=provider,
            env_var=env_var,
            store=store,
            max_requests_per_window=cfg.rate_limit_per_key if cfg else 20,
            window_seconds=cfg.rate_limit_window_seconds if cfg else 60,
            signup_url=cfg.signup_url if cfg and cfg.signup_url else "see .env.example",
            needed_in_phase=6,
            **kw,
        )
        if p.size == 0:
            report.errors[provider] = f"missing {env_var}"
            return None
        return p

    batches: list[list[ResearchItem]] = []
    batches.append(run("fear_greed", lambda: collect_fear_greed(http, assets)))
    batches.append(run("coingecko", lambda: collect_coingecko(http, assets)))
    batches.append(run("cftc", lambda: collect_cftc(http, assets)))
    batches.append(run("rss", lambda: collect_rss(http, assets)))
    batches.append(run("bitget", lambda: collect_bitget(http, assets)))

    fred = pool("fred", "FRED_API_KEY")
    if fred:
        batches.append(run("fred", lambda: collect_fred(http, fred, assets)))
    finn = pool("finnhub", "FINNHUB_KEYS")
    if finn:
        batches.append(run("finnhub", lambda: collect_finnhub(http, finn, store, assets)))
    news = pool("newsapi", "NEWSAPI_KEYS")
    if news:
        batches.append(run("newsapi", lambda: collect_newsapi(http, news, assets)))
    twelve = pool("twelve_data", "TWELVE_DATA_KEYS")
    if twelve:
        batches.append(run("twelve_data", lambda: collect_twelve_data(http, twelve, assets)))
    gold = pool("goldapi", "GOLD_API_KEY")
    if gold:
        batches.append(run("goldapi", lambda: collect_goldapi(http, gold, assets)))
    av = pool("alpha_vantage", "ALPHA_VANTAGE_KEYS")
    if av:
        batches.append(run("alpha_vantage", lambda: collect_alpha_vantage(http, av, assets)))

    batches.append(run("web", lambda: collect_web(http, assets)))

    for items in batches:
        for item in items:
            rid = upsert_item(store, item)
            if rid is None:
                report.skipped += 1
            else:
                report.inserted += 1
    return report
