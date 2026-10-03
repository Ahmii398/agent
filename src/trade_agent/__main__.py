"""CLI: ``python -m trade_agent init-db | status | verify``."""

from __future__ import annotations

import argparse
import json
import sys

from trade_agent import __version__
from trade_agent.approval.flags import LIVE_TRADING_ENABLED
from trade_agent.core.config import load_settings
from trade_agent.core.errors import AllKeysCoolingDown, BudgetExceeded, RiskViolation
from trade_agent.core.keys import KeyPool
from trade_agent.core.logging import configure_logging
from trade_agent.db.store import SCHEMA_VERSION, Store
from trade_agent.interfaces.llm_client import LLMRequest, LLMTask
from trade_agent.llm.budget import LLMBudget
from trade_agent.llm.client import build_llm_client
from trade_agent.risk.guard import RiskGuard
from trade_agent.risk.limits import HARD_LIMITS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trade-agent")
    parser.add_argument("--config", default=None, help="Path to YAML config")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="Create/migrate the SQLite database")
    sub.add_parser("status", help="Print config, tables, budget, live-flag")
    sub.add_parser("verify", help="Phase 1 end-to-end smoke against local DB")

    dl = sub.add_parser("download", help="Download Binance OHLCV into Parquet")
    dl.add_argument("--symbol", action="append", default=None)
    dl.add_argument("--timeframe", default="1h")
    dl.add_argument("--days", type=int, default=60)
    dl.add_argument("--start", default=None)
    dl.add_argument("--end", default=None)

    ins = sub.add_parser("inspect", help="Print stored candle quality")
    ins.add_argument("--symbol", default="BTC/USDT")
    ins.add_argument("--timeframe", default="1h")
    ins.add_argument("--sample", type=int, default=3)

    st = sub.add_parser("stream", help="Poll for newly closed candles")
    st.add_argument("--symbol", default="BTC/USDT")
    st.add_argument("--timeframe", default="1m")
    st.add_argument("--max", type=int, default=1)
    st.add_argument("--poll", type=float, default=2.0)

    vd = sub.add_parser("verify-data", help="Phase 2: real Binance download + quality")
    vd.add_argument("--symbol", action="append", default=None)
    vd.add_argument("--timeframe", default="1h")
    vd.add_argument("--days", type=int, default=60)

    args = parser.parse_args(argv)

    settings = load_settings(args.config)
    configure_logging(settings.app.log_level)

    if args.cmd == "init-db":
        return _init_db(settings)
    if args.cmd == "status":
        return _status(settings)
    if args.cmd == "verify":
        return _verify(settings)
    if args.cmd == "download":
        from trade_agent.data.cli import cmd_download

        return cmd_download(settings, args)
    if args.cmd == "inspect":
        from trade_agent.data.cli import cmd_inspect

        return cmd_inspect(settings, args)
    if args.cmd == "stream":
        from trade_agent.data.cli import cmd_stream

        return cmd_stream(settings, args)
    if args.cmd == "verify-data":
        from trade_agent.data.cli import cmd_verify_data

        return cmd_verify_data(settings, args)
    return 1


def _init_db(settings) -> int:
    with Store(settings.db_path) as store:
        version = store.migrate()
        tables = store.table_names()
    print(f"db={settings.db_path}")
    print(f"schema_version={version}")
    print(f"tables={len(tables)}")
    for name in tables:
        print(f"  - {name}")
    return 0


def _status(settings) -> int:
    with Store(settings.db_path) as store:
        store.migrate()
        budget = LLMBudget(store, settings)
        payload = {
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "db": str(settings.db_path),
            "data_dir": str(settings.data_dir),
            "timezone": settings.app.timezone,
            "universe": settings.universe.crypto,
            "llm_cap_usd": budget.cap_usd,
            "llm_spent_usd": budget.spent_usd(),
            "llm_remaining_usd": budget.remaining_usd(),
            "live_trading_enabled": LIVE_TRADING_ENABLED,
            "hard_limits": dict(HARD_LIMITS),
            "yaml_live_trading_enabled": settings.live_trading.enabled,
        }
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _verify(settings) -> int:
    """Exercise KeyPool, budget, risk guard, dummy LLM. No real API keys needed."""
    print("=== Phase 1 verify ===")
    print(f"version={__version__} tz={settings.app.timezone} seed={settings.app.random_seed}")

    with Store(settings.db_path) as store:
        store.migrate()
        tables = store.table_names()
        print(f"db={settings.db_path} tables={len(tables)} schema={SCHEMA_VERSION}")

        # KeyPool with in-memory dummy secrets — never printed.
        dummy_keys = ["SECRET_ALPHA", "SECRET_BRAVO", "SECRET_CHARLIE"]
        pool = KeyPool(
            provider="demo",
            env_var="DEMO_KEYS",
            store=store,
            keys=dummy_keys,
            max_requests_per_window=100,
            window_seconds=60,
            base_cooldown_seconds=0.2,
            max_cooldown_seconds=2.0,
        )
        first = pool.acquire()
        second = pool.acquire()
        print(
            f"keypool size={pool.size} first_index={first.key_index} "
            f"second_index={second.key_index}"
        )
        pool.report(first.key_index, 429)
        third = pool.acquire()
        print(f"after_429_on_{first.key_index} next_index={third.key_index}")
        try:
            # Exhaust remaining keys with 429 so acquire fails.
            pool.report(second.key_index, 429)
            pool.report(third.key_index, 429)
            pool.acquire(wait=False)
            print("ERROR: expected AllKeysCoolingDown")
            return 1
        except AllKeysCoolingDown as exc:
            print(f"all_keys_cooling_down={exc}")

        # LLM budget: tiny cap, dummy client, then refuse.
        settings.llm.monthly_budget_usd = 0.000001
        # Force a non-zero price so the cap can actually trip.
        from trade_agent.core.config import LLMPriceConfig

        settings.llm.prices["dummy/dummy-0"] = LLMPriceConfig(input=1000.0, output=1000.0)
        budget = LLMBudget(store, settings)
        client = build_llm_client(settings, budget, LLMTask.BULK, dummy=True)
        req = LLMRequest(
            task=LLMTask.BULK,
            messages=[{"role": "user", "content": "ping " * 200}],
        )
        try:
            client.generate(req)
        except BudgetExceeded:
            pass  # estimate may already exceed
        # Drain whatever remains with a recorded spend, then prove a further call dies.
        if budget.remaining_usd() > 0:
            from trade_agent.interfaces.llm_client import LLMUsage

            budget.record(
                provider="dummy",
                model="dummy-0",
                task="bulk",
                usage=LLMUsage(
                    prompt_tokens=1,
                    completion_tokens=1,
                    cost_usd=budget.remaining_usd(),
                ),
            )
        blocked = False
        try:
            client.generate(req)
        except BudgetExceeded:
            blocked = True
        print(
            f"budget cap={budget.cap_usd} spent={budget.spent_usd():.8f} "
            f"further_call_blocked={blocked}"
        )
        if not blocked:
            print("ERROR: budget did not block")
            return 1

        # Risk: YAML display can claim 50%; guard still uses 0.5%.
        guard = RiskGuard(store)
        print(f"hard_max_risk={guard.limits['max_risk_per_trade']}")
        print(f"yaml_display_max_risk={settings.risk_display.get('max_risk_per_trade')}")
        try:
            guard.check_trade_risk(0.50)
            print("ERROR: 50% risk was allowed")
            return 1
        except RiskViolation as exc:
            print(f"risk_reject={exc}")

        print(f"live_trading_enabled={LIVE_TRADING_ENABLED}")
        if LIVE_TRADING_ENABLED:
            print("ERROR: live trading must be disabled")
            return 1

        # Confirm dummy secrets never appear in the key_rate_limits table.
        leaked = store.fetchall("SELECT * FROM key_rate_limits")
        blob = " ".join(str(dict(r)) for r in leaked)
        for secret in dummy_keys:
            if secret in blob:
                print("ERROR: secret persisted")
                return 1
        print("secrets_not_persisted=true")
        print("=== Phase 1 verify OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
