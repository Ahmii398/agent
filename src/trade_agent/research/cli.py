"""CLI for research collection and point-in-time inspection."""

from __future__ import annotations

import json

from trade_agent.core.config import Settings
from trade_agent.core.timeutil import from_iso, utcnow
from trade_agent.db.store import Store
from trade_agent.research.collector import collect_all
from trade_agent.research.store import items_as_of, rank_items, upcoming_high_impact


def cmd_research(settings: Settings, args) -> int:
    assets = [a.upper() for a in (args.asset or [])] or None
    with Store(settings.db_path) as store:
        store.migrate()
        report = collect_all(settings, store, assets=assets)
        print(
            f"inserted={report.inserted} skipped_dupes={report.skipped} "
            f"sources={report.by_source} errors={report.errors}"
        )
        as_of = from_iso(args.as_of) if args.as_of else utcnow()
        rows = rank_items(items_as_of(store, as_of, assets=assets), now=as_of)
        print(f"pit_rows={len(rows)} as_of={as_of.isoformat()}")
        for row in rows[: args.sample]:
            print(
                f"  {row['published_at']} {row['source']} {row['kind']} "
                f"rel={row['reliability']} sent={row['sentiment']} {row['title'][:80]}"
            )
        events = upcoming_high_impact(store, as_of, hours=48)
        print(f"high_impact_next_48h={len(events)}")
        for ev in events[:8]:
            print(f"  {ev['scheduled_at']} {ev['impact']} {ev['name']}")
        # Never dump env or secrets. Errors are exception type names only.
        print(f"live_flag_unchanged keys_in_report={_keys_leaked(report)}")
    return 0


def cmd_research_inspect(settings: Settings, args) -> int:
    with Store(settings.db_path) as store:
        store.migrate()
        as_of = from_iso(args.as_of) if args.as_of else utcnow()
        rows = items_as_of(store, as_of)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["source"]] = counts.get(row["source"], 0) + 1
        print(
            json.dumps(
                {"as_of": as_of.isoformat(), "rows": len(rows), "by_source": counts},
                indent=2,
            )
        )
    return 0


def _keys_leaked(report) -> bool:
    """True only if a source error looks like it echoed a secret assignment."""
    blob = json.dumps({"s": report.by_source, "e": report.errors})
    lowered = blob.lower()
    return any(token in lowered for token in ("api_key=", "token=", "apikey=", "x-access-token="))
