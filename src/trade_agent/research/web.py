"""General web fetch. Respects robots.txt. Never bypasses login/paywall/anti-bot."""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import utcnow
from trade_agent.research.extract import extract_untrusted
from trade_agent.research.http import CachedHTTP, polite_sleep
from trade_agent.research.models import RELIABILITY, ResearchItem

log = get_logger("research.web")

# Explicit allowlist — we do not spider the open web.
ALLOWED = (
    "https://en.wikipedia.org/wiki/Bitcoin",
    "https://en.wikipedia.org/wiki/Federal_Reserve",
)


def collect_web(http: CachedHTTP, assets: list[str]) -> list[ResearchItem]:
    items: list[ResearchItem] = []
    for url in ALLOWED:
        if not _robots_allows(http, url):
            log.warning("robots_disallow url=%s", url)
            continue
        try:
            html = http.get_text(url, provider="web", ttl=86400)
        except Exception as exc:
            log.warning("web_fail url=%s err=%s", url, type(exc).__name__)
            continue
        extracted = extract_untrusted(html[:8000], source="web", url=url)
        items.append(
            ResearchItem(
                source="web",
                url=url,
                published_at=None,
                fetched_at=utcnow(),
                asset_tags=list({*assets, *extracted["tags"]}),
                title=url.rsplit("/", 1)[-1].replace("_", " "),
                summary=extracted["summary"],
                sentiment=extracted["sentiment"],
                reliability=RELIABILITY["web"],
                kind="web",
                published_at_unknown=True,
            )
        )
        polite_sleep(0.4)
    return items


def _robots_allows(http: CachedHTTP, url: str) -> bool:
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        text = http.get_text(robots_url, provider="robots", ttl=86400)
    except Exception:
        return False
    rp = RobotFileParser()
    rp.parse(text.splitlines())
    return rp.can_fetch("trade-agent-research/0.1", url)
