"""Point-in-time research must never leak later-published or undated items."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trade_agent.research.collector import collect_all
from trade_agent.research.models import ResearchItem
from trade_agent.research.store import items_as_of, rank_items, upsert_event, upsert_item


def _item(*, title: str, published, source: str = "unit", unknown: bool = False) -> ResearchItem:
    return ResearchItem(
        source=source,
        url=f"https://example.test/{title}",
        published_at=published,
        fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
        asset_tags=["BTC"],
        title=title,
        summary=title,
        sentiment=0.0,
        reliability=0.8,
        kind="news",
        published_at_unknown=unknown,
    )


def test_items_as_of_excludes_future_same_instant_and_unknown(store) -> None:
    as_of = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    upsert_item(store, _item(title="past", published=datetime(2026, 6, 1, tzinfo=UTC)))
    upsert_item(store, _item(title="boundary", published=as_of))
    upsert_item(store, _item(title="future", published=datetime(2026, 7, 1, tzinfo=UTC)))
    upsert_item(store, _item(title="unknown", published=None, unknown=True))

    rows = items_as_of(store, as_of)
    titles = {row["title"] for row in rows}
    assert titles == {"past"}

    ranked = rank_items(rows, now=as_of)
    assert [row["title"] for row in ranked] == ["past"]


def test_items_as_of_asset_filter(store) -> None:
    upsert_item(
        store,
        ResearchItem(
            source="unit",
            url="https://example.test/eth",
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
            asset_tags=["ETH"],
            title="eth-only",
            summary="eth",
            reliability=0.7,
        ),
    )
    upsert_item(store, _item(title="btc-story", published=datetime(2026, 5, 2, tzinfo=UTC)))
    rows = items_as_of(store, datetime(2026, 6, 1, tzinfo=UTC), assets=["BTC"])
    assert {row["title"] for row in rows} == {"btc-story"}


def test_duplicate_dedupe_key_skipped(store) -> None:
    first = upsert_item(store, _item(title="dup", published=datetime(2026, 5, 1, tzinfo=UTC)))
    second = upsert_item(store, _item(title="dup", published=datetime(2026, 5, 1, tzinfo=UTC)))
    assert first is not None
    assert second is None


def test_upcoming_high_impact_window(store) -> None:
    now = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    upsert_event(
        store,
        name="NFP",
        impact="high",
        scheduled_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        assets=["USD"],
        source="finnhub_calendar",
    )
    upsert_event(
        store,
        name="already happened",
        impact="high",
        scheduled_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        assets=["USD"],
        source="finnhub_calendar",
    )
    upsert_event(
        store,
        name="too far",
        impact="high",
        scheduled_at=datetime(2026, 6, 10, tzinfo=UTC),
        assets=["USD"],
        source="finnhub_calendar",
    )
    from trade_agent.research.store import upcoming_high_impact

    names = {row["name"] for row in upcoming_high_impact(store, now, hours=48)}
    assert names == {"NFP"}


def test_collector_refuses_when_live_enabled(store, settings, monkeypatch) -> None:
    monkeypatch.setattr("trade_agent.research.collector.LIVE_TRADING_ENABLED", True)
    with pytest.raises(RuntimeError, match="live trading"):
        collect_all(settings, store)
