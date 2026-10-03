from trade_agent.db.store import SCHEMA_VERSION


REQUIRED_TABLES = {
    "schema_migrations",
    "http_cache",
    "key_rate_limits",
    "llm_usage",
    "llm_monthly_budget",
    "research_items",
    "economic_events",
    "briefings",
    "setups",
    "hypotheses",
    "strategies",
    "experiments",
    "experiment_counter",
    "paper_fills",
    "calibration_outcomes",
    "risk_audit",
    "live_approvals",
}


def test_migrate_creates_all_tables(store) -> None:
    names = set(store.table_names())
    missing = REQUIRED_TABLES - names
    assert not missing, f"missing tables: {missing}"
    assert store.fetchone("SELECT total_tested FROM experiment_counter WHERE id=1")["total_tested"] == 0


def test_migrate_is_idempotent(store) -> None:
    again = store.migrate()
    assert again == SCHEMA_VERSION
    assert set(REQUIRED_TABLES).issubset(store.table_names())


def test_research_published_at_nullable_for_unknown_pit(store) -> None:
    """Unknown publish time is allowed but must be flagged; backtests will exclude it."""
    store.execute(
        """
        INSERT INTO research_items (
            source, url, published_at, fetched_at, asset_tags, title, summary,
            sentiment, reliability, content_sha256, published_at_unknown
        ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            "rss",
            "https://example.test/a",
            "2026-10-03T00:00:00.000000Z",
            '["BTC"]',
            "t",
            "s",
            0.0,
            0.4,
            "abc",
        ),
    )
    row = store.fetchone("SELECT published_at_unknown FROM research_items")
    assert row["published_at_unknown"] == 1
