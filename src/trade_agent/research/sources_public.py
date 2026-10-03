"""Structured sources that need no API key."""

from __future__ import annotations

from datetime import UTC, datetime

from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import utcnow
from trade_agent.research.extract import extract_untrusted
from trade_agent.research.http import CachedHTTP, polite_sleep
from trade_agent.research.models import RELIABILITY, ResearchItem

log = get_logger("research.public")


def collect_fear_greed(http: CachedHTTP, assets: list[str]) -> list[ResearchItem]:
    data = http.get_json(
        "https://api.alternative.me/fng/?limit=5&format=json",
        provider="fear_greed",
        ttl=1800,
    )
    items = []
    for row in (data or {}).get("data", []):
        ts = datetime.fromtimestamp(int(row["timestamp"]), tz=UTC)
        value = int(row["value"])
        label = row.get("value_classification", "")
        sentiment = (value - 50) / 50.0
        items.append(
            ResearchItem(
                source="fear_greed",
                url="https://api.alternative.me/fng/",
                published_at=ts,
                fetched_at=utcnow(),
                asset_tags=assets,
                title=f"Fear & Greed {value} ({label})",
                summary=f"Crypto Fear & Greed index={value} classification={label}",
                sentiment=sentiment,
                reliability=RELIABILITY["fear_greed"],
                kind="macro",
                extra={"value": value, "label": label},
            )
        )
    return items


def collect_coingecko(http: CachedHTTP, assets: list[str]) -> list[ResearchItem]:
    items: list[ResearchItem] = []
    global_data = http.get_json(
        "https://api.coingecko.com/api/v3/global",
        provider="coingecko",
        ttl=1800,
    )
    g = ((global_data or {}).get("data") or {})
    if g:
        btc_dom = (g.get("market_cap_percentage") or {}).get("btc")
        items.append(
            ResearchItem(
                source="coingecko",
                url="https://api.coingecko.com/api/v3/global",
                published_at=utcnow(),
                fetched_at=utcnow(),
                asset_tags=assets,
                title=f"BTC dominance {btc_dom}",
                summary=(
                    f"global mcap_usd={g.get('total_market_cap', {}).get('usd')} "
                    f"btc_dominance={btc_dom} "
                    f"change_24h={g.get('market_cap_change_percentage_24h_usd')}"
                ),
                sentiment=0.0,
                reliability=RELIABILITY["coingecko"],
                kind="macro",
                extra={"btc_dominance": btc_dom},
            )
        )
    coin_ids = {"BTC": "bitcoin", "ETH": "ethereum"}
    for tag in assets:
        cid = coin_ids.get(tag.upper())
        if not cid:
            continue
        data = http.get_json(
            f"https://api.coingecko.com/api/v3/coins/{cid}",
            provider="coingecko",
            params={
                "localization": "false",
                "tickers": "false",
                "community_data": "false",
                "developer_data": "false",
            },
            ttl=1800,
        )
        if not data:
            continue
        md = data.get("market_data") or {}
        items.append(
            ResearchItem(
                source="coingecko",
                url=f"https://www.coingecko.com/en/coins/{cid}",
                published_at=utcnow(),
                fetched_at=utcnow(),
                asset_tags=[tag],
                title=f"{data.get('name')} mcap rank {data.get('market_cap_rank')}",
                summary=(
                    f"price_usd={md.get('current_price', {}).get('usd')} "
                    f"chg_24h={md.get('price_change_percentage_24h')} "
                    f"oi? derivatives via market_data"
                ),
                sentiment=_chg_sent(md.get("price_change_percentage_24h")),
                reliability=RELIABILITY["coingecko"],
                kind="quote",
                extra={
                    "price_usd": (md.get("current_price") or {}).get("usd"),
                    "change_24h": md.get("price_change_percentage_24h"),
                },
            )
        )
        polite_sleep(0.3)
    return items


def collect_cftc(http: CachedHTTP, assets: list[str]) -> list[ResearchItem]:
    """Latest financial-futures COT slice (public Socrata)."""
    data = http.get_json(
        "https://publicreporting.cftc.gov/resource/gpe5-46if.json",
        provider="cftc",
        params={"$limit": "8", "$order": "report_date_as_yyyy_mm_dd DESC"},
        ttl=86400,
    )
    items = []
    for row in data or []:
        name = row.get("contract_market_name") or row.get("market_and_exchange_names") or "COT"
        date = row.get("report_date_as_yyyy_mm_dd") or row.get("report_date")
        pub = None
        if date:
            pub = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=UTC)
        items.append(
            ResearchItem(
                source="cftc",
                url="https://publicreporting.cftc.gov/resource/gpe5-46if.json",
                published_at=pub,
                fetched_at=utcnow(),
                asset_tags=assets,
                title=f"COT {name}",
                summary=str(row)[:400],
                sentiment=0.0,
                reliability=RELIABILITY["cftc"],
                kind="macro",
                extra={"contract": name},
                published_at_unknown=pub is None,
            )
        )
    return items


def collect_rss(http: CachedHTTP, assets: list[str]) -> list[ResearchItem]:
    feeds = [
        ("https://www.federalreserve.gov/feeds/press_all.xml", "rss_fed", 0.85),
        ("https://www.coindesk.com/arc/outboundfeeds/rss/", "rss_coindesk", 0.55),
    ]
    items: list[ResearchItem] = []
    for url, source, rel in feeds:
        try:
            text = http.get_text(url, provider=source, ttl=1800)
        except Exception as exc:
            log.warning("rss_fail source=%s err=%s", source, type(exc).__name__)
            continue
        items.extend(_parse_rss(text, source=source, url=url, reliability=rel, assets=assets))
    return items


def _parse_rss(
    xml_text: str, *, source: str, url: str, reliability: float, assets: list[str]
) -> list[ResearchItem]:
    import xml.etree.ElementTree as ET

    items = []
    try:
        root = ET.fromstring(_strip_bom(xml_text))
    except ET.ParseError:
        return items
    for node in root.findall(".//item")[:15]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or url).strip()
        desc = (node.findtext("description") or title).strip()
        pub_s = node.findtext("pubDate") or node.findtext("published")
        pub = _parse_date(pub_s)
        extracted = extract_untrusted(desc, source=source, url=link)
        tags = list({*assets, *extracted["tags"]})
        items.append(
            ResearchItem(
                source=source,
                url=link,
                published_at=pub,
                fetched_at=utcnow(),
                asset_tags=tags,
                title=title[:240],
                summary=extracted["summary"],
                sentiment=extracted["sentiment"],
                reliability=reliability,
                kind="news",
                published_at_unknown=pub is None,
            )
        )
    return items


def _strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    if text.startswith("ï»¿"):
        return text[3:]
    return text


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except Exception:
            return None


def _chg_sent(chg) -> float:
    try:
        return max(-1.0, min(1.0, float(chg) / 10.0))
    except (TypeError, ValueError):
        return 0.0
