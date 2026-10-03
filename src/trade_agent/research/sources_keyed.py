"""Keyed structured sources. Keys come from KeyPool; logs use index only."""

from __future__ import annotations

from datetime import UTC, datetime

from trade_agent.core.keys import KeyPool
from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import utcnow
from trade_agent.db.store import Store
from trade_agent.research.extract import extract_untrusted
from trade_agent.research.http import CachedHTTP, polite_sleep
from trade_agent.research.models import RELIABILITY, ResearchItem
from trade_agent.research.store import upsert_event

log = get_logger("research.keyed")

FRED_SERIES = {
    "DTWEXBGS": ("DXY", "Trade-weighted USD"),
    "DGS10": ("US10Y", "10-year Treasury"),
    "DGS2": ("US2Y", "2-year Treasury"),
    "VIXCLS": ("VIX", "VIX"),
    "FEDFUNDS": ("FEDFUNDS", "Fed funds"),
}


def collect_fred(http: CachedHTTP, pool: KeyPool, assets: list[str]) -> list[ResearchItem]:
    items = []
    for series, (tag, label) in FRED_SERIES.items():
        data = http.get_json(
            "https://api.stlouisfed.org/fred/series/observations",
            provider="fred",
            params={"series_id": series, "file_type": "json", "sort_order": "desc", "limit": 3},
            pool=pool,
            inject="param:api_key",
            ttl=3600,
        )
        obs = [
            o
            for o in (data or {}).get("observations", [])
            if o.get("value") not in (".", "", None)
        ]
        if not obs:
            continue
        latest = obs[0]
        pub = datetime.fromisoformat(latest["date"]).replace(tzinfo=UTC)
        items.append(
            ResearchItem(
                source="fred",
                url=f"https://fred.stlouisfed.org/series/{series}",
                published_at=pub,
                fetched_at=utcnow(),
                asset_tags=list({*assets, tag}),
                title=f"{label} {latest['value']}",
                summary=f"FRED {series}={latest['value']} asof={latest['date']}",
                sentiment=0.0,
                reliability=RELIABILITY["fred"],
                kind="macro",
                extra={"series": series, "value": latest["value"]},
            )
        )
    return items


def collect_finnhub(
    http: CachedHTTP, pool: KeyPool, store: Store, assets: list[str]
) -> list[ResearchItem]:
    items: list[ResearchItem] = []
    for category in ("crypto", "forex", "general"):
        data = http.get_json(
            "https://finnhub.io/api/v1/news",
            provider="finnhub",
            params={"category": category},
            pool=pool,
            inject="param:token",
            ttl=900,
        )
        for row in (data or [])[:20]:
            pub = datetime.fromtimestamp(int(row.get("datetime") or 0), tz=UTC)
            extracted = extract_untrusted(
                f"{row.get('headline', '')}. {row.get('summary', '')}",
                source="finnhub_news",
                url=row.get("url"),
            )
            tags = list({*assets, *extracted["tags"]})
            items.append(
                ResearchItem(
                    source="finnhub_news",
                    url=row.get("url"),
                    published_at=pub,
                    fetched_at=utcnow(),
                    asset_tags=tags,
                    title=(row.get("headline") or "")[:240],
                    summary=extracted["summary"],
                    sentiment=extracted["sentiment"],
                    reliability=RELIABILITY["finnhub_news"],
                    kind="news",
                )
            )
    try:
        cal = http.get_json(
            "https://finnhub.io/api/v1/calendar/economic",
            provider="finnhub",
            pool=pool,
            inject="param:token",
            ttl=1800,
        )
    except Exception as exc:
        log.warning("finnhub calendar skip err=%s", type(exc).__name__)
        cal = {}
    if isinstance(cal, dict):
        cal_rows = cal.get("economicCalendar") or cal.get("economic_calendar") or []
    else:
        cal_rows = cal or []
    for row in list(cal_rows)[:40]:
        raw_t = row.get("time") or row.get("date")
        sched = _parse_iso(raw_t)
        impact = str(row.get("impact") or "low").lower()
        name = row.get("event") or "economic event"
        if sched:
            upsert_event(
                store,
                name=name,
                impact=impact if impact in {"low", "medium", "high"} else "low",
                scheduled_at=sched,
                assets=assets,
                source="finnhub_calendar",
                url="https://finnhub.io/api/v1/calendar/economic",
            )
        items.append(
            ResearchItem(
                source="finnhub_calendar",
                url="https://finnhub.io/api/v1/calendar/economic",
                published_at=sched or utcnow(),
                fetched_at=utcnow(),
                asset_tags=assets,
                title=f"{impact.upper()} {name}",
                summary=(
                    f"{row.get('country')} {name} "
                    f"actual={row.get('actual')} estimate={row.get('estimate')}"
                ),
                sentiment=0.0,
                reliability=RELIABILITY["finnhub_calendar"],
                kind="calendar",
                extra={"impact": impact, "country": row.get("country")},
                is_high_impact_event=impact == "high",
                published_at_unknown=sched is None,
            )
        )
    return items


def collect_newsapi(http: CachedHTTP, pool: KeyPool, assets: list[str]) -> list[ResearchItem]:
    q = " OR ".join(["bitcoin", "ethereum", "federal reserve", "inflation", "gold"])
    data = None
    try:
        data = http.get_json(
            "https://newsapi.org/v2/everything",
            provider="newsapi",
            params={"q": q, "language": "en", "sortBy": "publishedAt", "pageSize": 20},
            pool=pool,
            inject="header:X-Api-Key",
            ttl=1800,
        )
    except Exception as exc:
        log.warning("newsapi everything failed err=%s", type(exc).__name__)
    if not data or data.get("status") == "error" or not data.get("articles"):
        data = http.get_json(
            "https://newsapi.org/v2/top-headlines",
            provider="newsapi",
            params={"category": "business", "language": "en", "pageSize": 20},
            pool=pool,
            inject="header:X-Api-Key",
            ttl=1800,
        )
    items = []
    for row in (data or {}).get("articles", []):
        pub = _parse_iso(row.get("publishedAt"))
        extracted = extract_untrusted(
            f"{row.get('title', '')}. {row.get('description') or ''}",
            source="newsapi",
            url=row.get("url"),
        )
        items.append(
            ResearchItem(
                source="newsapi",
                url=row.get("url"),
                published_at=pub,
                fetched_at=utcnow(),
                asset_tags=list({*assets, *extracted["tags"]}),
                title=(row.get("title") or "")[:240],
                summary=extracted["summary"],
                sentiment=extracted["sentiment"],
                reliability=RELIABILITY["newsapi"],
                kind="news",
                published_at_unknown=pub is None,
            )
        )
    return items


def collect_twelve_data(http: CachedHTTP, pool: KeyPool, assets: list[str]) -> list[ResearchItem]:
    # Free-tier quotes. DXY/SPX/US10Y are plan-gated; FRED covers those macros.
    symbols = ["XAU/USD", "SPY", "EUR/USD"]
    items = []
    for symbol in symbols:
        try:
            data = http.get_json(
                "https://api.twelvedata.com/quote",
                provider="twelve_data",
                params={"symbol": symbol},
                pool=pool,
                inject="param:apikey",
                ttl=300,
            )
        except Exception as exc:
            log.warning("twelve_data skip symbol=%s err=%s", symbol, type(exc).__name__)
            continue
        if not data or data.get("status") == "error":
            log.warning("twelve_data empty symbol=%s", symbol)
            continue
        close = data.get("close") or data.get("price")
        items.append(
            ResearchItem(
                source="twelve_data",
                url="https://twelvedata.com",
                published_at=_parse_iso(data.get("datetime") or data.get("timestamp")) or utcnow(),
                fetched_at=utcnow(),
                asset_tags=list({*assets, symbol.split("/")[0]}),
                title=f"{symbol} {close}",
                summary=(
                    f"{symbol} close={close} change={data.get('change')} "
                    f"percent={data.get('percent_change')}"
                ),
                sentiment=_chg_sent(data.get("percent_change")),
                reliability=RELIABILITY["twelve_data"],
                kind="quote",
                extra={"symbol": symbol, "close": close},
            )
        )
        polite_sleep(0.2)
    return items


def collect_goldapi(http: CachedHTTP, pool: KeyPool, assets: list[str]) -> list[ResearchItem]:
    data = http.get_json(
        "https://www.goldapi.io/api/XAU/USD",
        provider="goldapi",
        pool=pool,
        inject="header:x-access-token",
        ttl=300,
    )
    if not data:
        return []
    price = data.get("price") or data.get("price_gram_24k")
    return [
        ResearchItem(
            source="goldapi",
            url="https://www.goldapi.io/api/XAU/USD",
            published_at=utcnow(),
            fetched_at=utcnow(),
            asset_tags=list({*assets, "XAU"}),
            title=f"XAU/USD {price}",
            summary=(
                f"gold bid={data.get('bid')} ask={data.get('ask')} "
                f"chg={data.get('ch')} open={data.get('open_price')}"
            ),
            sentiment=_chg_sent(data.get("chp")),
            reliability=RELIABILITY["goldapi"],
            kind="quote",
            extra={"price": price},
        )
    ]


def collect_alpha_vantage(http: CachedHTTP, pool: KeyPool, assets: list[str]) -> list[ResearchItem]:
    data = http.get_json(
        "https://www.alphavantage.co/query",
        provider="alpha_vantage",
        params={"function": "NEWS_SENTIMENT", "tickers": "CRYPTO:BTC,FOREX:USD", "limit": 15},
        pool=pool,
        inject="param:apikey",
        ttl=3600,
    )
    items = []
    for row in (data or {}).get("feed", [])[:15]:
        pub = _parse_av_time(row.get("time_published"))
        extracted = extract_untrusted(
            f"{row.get('title', '')}. {row.get('summary', '')}",
            source="alpha_vantage",
            url=row.get("url"),
        )
        try:
            sent = float(row.get("overall_sentiment_score") or extracted["sentiment"])
        except (TypeError, ValueError):
            sent = extracted["sentiment"]
        items.append(
            ResearchItem(
                source="alpha_vantage",
                url=row.get("url"),
                published_at=pub,
                fetched_at=utcnow(),
                asset_tags=list({*assets, *extracted["tags"]}),
                title=(row.get("title") or "")[:240],
                summary=extracted["summary"],
                sentiment=max(-1.0, min(1.0, sent)),
                reliability=RELIABILITY["alpha_vantage"],
                kind="news",
                published_at_unknown=pub is None,
            )
        )
    return items


def collect_bitget(http: CachedHTTP, assets: list[str]) -> list[ResearchItem]:
    """Public Bitget mix market data. API key is not required and not sent."""
    items = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        try:
            fund = http.get_json(
                "https://api.bitget.com/api/v2/mix/market/history-fund-rate",
                provider="bitget",
                params={"symbol": symbol, "productType": "USDT-FUTURES", "pageSize": "1"},
                ttl=300,
            )
            ticker = http.get_json(
                "https://api.bitget.com/api/v2/mix/market/ticker",
                provider="bitget",
                params={"symbol": symbol, "productType": "USDT-FUTURES"},
                ttl=300,
            )
            oi = http.get_json(
                "https://api.bitget.com/api/v2/mix/market/open-interest",
                provider="bitget",
                params={"symbol": symbol, "productType": "USDT-FUTURES"},
                ttl=300,
            )
        except Exception as exc:
            log.warning("bitget skip symbol=%s err=%s", symbol, type(exc).__name__)
            continue
        fund_row = _first(fund)
        tick_row = _first(ticker)
        oi_row = _first(oi)
        if isinstance(oi_row, dict) and oi_row.get("openInterestList"):
            oi_row = _first({"data": oi_row.get("openInterestList")})
        rate = fund_row.get("fundingRate")
        mark = tick_row.get("lastPr") or tick_row.get("markPrice")
        open_int = oi_row.get("size") or oi_row.get("openInterest")
        items.append(
            ResearchItem(
                source="bitget",
                url="https://api.bitget.com/api/v2/mix/market/history-fund-rate",
                published_at=utcnow(),
                fetched_at=utcnow(),
                asset_tags=[symbol.replace("USDT", "")],
                title=f"{symbol} funding {rate}",
                summary=f"bitget {symbol} funding={rate} last={mark} oi={open_int}",
                sentiment=0.0,
                reliability=RELIABILITY["bitget"],
                kind="derivatives",
                extra={"funding": rate, "symbol": symbol, "oi": open_int, "last": mark},
            )
        )
    return items


def _first(payload) -> dict:
    inner = (payload or {}).get("data") if isinstance(payload, dict) else payload
    if isinstance(inner, list):
        return inner[0] if inner and isinstance(inner[0], dict) else {}
    return inner if isinstance(inner, dict) else {}


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_av_time(value: str | None) -> datetime | None:
    if not value or len(value) < 8:
        return None
    # 20261003T080000
    try:
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return _parse_iso(value)


def _chg_sent(chg) -> float:
    try:
        return max(-1.0, min(1.0, float(chg) / 5.0))
    except (TypeError, ValueError):
        return 0.0
