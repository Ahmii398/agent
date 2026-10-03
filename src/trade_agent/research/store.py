"""Persist and query research items with a hard point-in-time rule."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from trade_agent.core.timeutil import ensure_utc, to_iso, utcnow
from trade_agent.db.store import Store
from trade_agent.research.models import HIGH_IMPACT_TERMS, ResearchItem


def upsert_item(store: Store, item: ResearchItem) -> int | None:
    """Insert one item. Duplicate ``dedupe_key`` is ignored. Returns row id or None."""
    if not item.dedupe_key:
        basis = (item.url or "") + "|" + (item.title or "") + "|" + (item.source or "")
        item.dedupe_key = hashlib.sha256(basis.encode()).hexdigest()
    if not item.content_sha256:
        item.content_sha256 = hashlib.sha256((item.summary or item.title).encode()).hexdigest()
    if not item.published_at:
        item.published_at_unknown = True
    title_l = (item.title or "").lower()
    if any(term in title_l for term in HIGH_IMPACT_TERMS):
        item.is_high_impact_event = True
    try:
        cur = store.execute(
            """
            INSERT INTO research_items (
                source, url, published_at, fetched_at, asset_tags, title, summary,
                sentiment, reliability, content_sha256, dedupe_key,
                is_high_impact_event, published_at_unknown, raw_path, kind, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                item.source,
                item.url,
                to_iso(item.published_at) if item.published_at else None,
                to_iso(item.fetched_at),
                json.dumps(item.asset_tags),
                item.title,
                item.summary,
                item.sentiment,
                item.reliability,
                item.content_sha256,
                item.dedupe_key,
                int(item.is_high_impact_event),
                int(item.published_at_unknown),
                item.kind,
                json.dumps(item.extra) if item.extra else None,
            ),
        )
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None


def items_as_of(
    store: Store,
    as_of: datetime,
    *,
    assets: list[str] | None = None,
    include_unknown_published: bool = False,
) -> list[dict]:
    """Rows whose ``published_at`` is strictly before ``as_of``.

    Unknown publish times are excluded by default so a backtest cannot
    accidentally use a story that may have arrived later.
    """
    cutoff = to_iso(ensure_utc(as_of))
    rows = store.fetchall(
        """
        SELECT * FROM research_items
        WHERE published_at IS NOT NULL
          AND published_at < ?
          AND (? = 1 OR published_at_unknown = 0)
        ORDER BY published_at DESC
        """,
        (cutoff, int(include_unknown_published)),
    )
    out = [dict(r) for r in rows]
    if assets:
        wanted = {a.upper() for a in assets}
        filtered = []
        for row in out:
            tags = {t.upper() for t in json.loads(row["asset_tags"] or "[]")}
            if tags & wanted:
                filtered.append(row)
        return filtered
    return out


def upcoming_high_impact(store: Store, now: datetime | None = None, hours: int = 24) -> list[dict]:
    """Scheduled high-impact calendar rows in the next ``hours`` (UTC)."""
    when = ensure_utc(now) if now else utcnow()
    start = to_iso(when)
    from datetime import timedelta

    end = to_iso(when + timedelta(hours=hours))
    rows = store.fetchall(
        """
        SELECT * FROM economic_events
        WHERE scheduled_at >= ? AND scheduled_at <= ? AND impact IN ('high', 'HIGH')
        ORDER BY scheduled_at
        """,
        (start, end),
    )
    return [dict(r) for r in rows]


def rank_items(rows: list[dict], *, now: datetime | None = None) -> list[dict]:
    """Sort by reliability × recency. Does not change stored data."""
    when = ensure_utc(now) if now else utcnow()
    scored = []
    for row in rows:
        pub = row.get("published_at")
        age_h = 24.0
        if pub:
            from trade_agent.core.timeutil import from_iso

            age_h = max((when - from_iso(pub)).total_seconds() / 3600.0, 0.0)
        recency = 1.0 / (1.0 + age_h / 12.0)
        score = float(row["reliability"]) * 0.6 + recency * 0.4
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored]


def upsert_event(
    store: Store,
    *,
    name: str,
    impact: str,
    scheduled_at: datetime,
    assets: list[str],
    source: str,
    url: str | None = None,
) -> None:
    try:
        store.execute(
            """
            INSERT INTO economic_events
                (name, impact, scheduled_at, assets, source, url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                impact.lower(),
                to_iso(ensure_utc(scheduled_at)),
                json.dumps(assets),
                source,
                url,
                to_iso(utcnow()),
            ),
        )
    except sqlite3.IntegrityError:
        return
