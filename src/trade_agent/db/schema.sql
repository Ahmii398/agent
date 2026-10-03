-- Canonical SQLite schema. All timestamps are ISO-8601 UTC (suffix Z).
-- Candles live in Parquet under {data_dir}/candles/; they are NOT stored here.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS http_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT,
    status_code INTEGER,
    content_type TEXT,
    body_path TEXT NOT NULL,
    body_sha256 TEXT NOT NULL
);

-- Rate-limit / cooldown state. Secrets are never persisted.
CREATE TABLE IF NOT EXISTS key_rate_limits (
    provider TEXT NOT NULL,
    key_index INTEGER NOT NULL,
    window_started_at TEXT,
    request_count INTEGER NOT NULL DEFAULT 0,
    last_status INTEGER,
    consecutive_429 INTEGER NOT NULL DEFAULT 0,
    cooldown_until TEXT,
    last_used_at TEXT,
    PRIMARY KEY (provider, key_index)
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    year_month TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    task TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    stopped_by_budget INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_monthly_budget (
    year_month TEXT PRIMARY KEY,
    cap_usd REAL NOT NULL,
    spent_usd REAL NOT NULL DEFAULT 0
);

-- Point-in-time research. Backtests may only read rows with published_at < sim time.
CREATE TABLE IF NOT EXISTS research_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    url TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    asset_tags TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    sentiment REAL,
    reliability REAL NOT NULL,
    content_sha256 TEXT NOT NULL,
    dedupe_key TEXT,
    is_high_impact_event INTEGER NOT NULL DEFAULT 0,
    published_at_unknown INTEGER NOT NULL DEFAULT 0,
    raw_path TEXT,
    kind TEXT NOT NULL DEFAULT 'news',
    extra_json TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_research_dedupe
    ON research_items(dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_published ON research_items(published_at);
CREATE INDEX IF NOT EXISTS idx_research_fetched ON research_items(fetched_at);

CREATE TABLE IF NOT EXISTS economic_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    impact TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    assets TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_scheduled ON economic_events(scheduled_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedupe
    ON economic_events(source, name, scheduled_at);

CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    created_at TEXT NOT NULL,
    as_of TEXT NOT NULL,
    higher_tf_bias TEXT,
    thesis TEXT,
    invalidation TEXT,
    scenarios_json TEXT NOT NULL,
    confidence REAL,
    decision TEXT,
    checklist_json TEXT,
    devil_advocate TEXT,
    rebuttal TEXT,
    model TEXT
);

CREATE TABLE IF NOT EXISTS setups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    market TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    session TEXT,
    regime TEXT,
    setup_type TEXT,
    feature_snapshot_json TEXT NOT NULL,
    briefing_id INTEGER REFERENCES briefings(id),
    outcome_r REAL,
    mae REAL,
    mfe REAL,
    opened_at TEXT,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_setups_query ON setups(setup_type, regime, market);

CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    source_setup_id INTEGER,
    status TEXT NOT NULL DEFAULT 'proposed',
    validation_experiment_id INTEGER
);

CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    spec_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    retired_at TEXT,
    retire_reason TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    strategy_id INTEGER,
    strategy_name TEXT,
    config_hash TEXT NOT NULL,
    data_range TEXT NOT NULL,
    code_version TEXT NOT NULL,
    random_seed INTEGER NOT NULL,
    metrics_json TEXT,
    passed INTEGER,
    fail_reason TEXT
);

-- Running count of every strategy ever tested (multiple-testing bias).
CREATE TABLE IF NOT EXISTS experiment_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_tested INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO experiment_counter (id, total_tested) VALUES (1, 0);

CREATE TABLE IF NOT EXISTS paper_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    strategy_id INTEGER,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    order_type TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS calibration_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    briefing_id INTEGER NOT NULL,
    stated_confidence REAL NOT NULL,
    outcome INTEGER NOT NULL,
    brier REAL NOT NULL,
    resolved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    action TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    reason TEXT NOT NULL
);

-- Explicit human approval records for paper → live. Empty by default.
CREATE TABLE IF NOT EXISTS ohlcv_coverage (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (exchange, symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS live_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    note TEXT,
    revoked_at TEXT
);
