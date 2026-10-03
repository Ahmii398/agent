from __future__ import annotations

import logging
import os

import pytest

from trade_agent.core.errors import AllKeysCoolingDown, MissingAPIKey
from trade_agent.core.keys import KeyPool, keys_from_env


def test_round_robin_and_429_skips_hot_key(store, caplog) -> None:
    keys = ["alpha-secret-value", "bravo-secret-value"]
    pool = KeyPool(
        provider="finnhub",
        env_var="FINNHUB_KEYS",
        store=store,
        keys=keys,
        max_requests_per_window=50,
        window_seconds=60,
        base_cooldown_seconds=30,
        max_cooldown_seconds=60,
    )
    a = pool.acquire()
    b = pool.acquire()
    assert a.key_index == 0
    assert b.key_index == 1
    assert a.secret == "alpha-secret-value"

    caplog.set_level(logging.INFO)
    pool.report(0, 429)
    c = pool.acquire()
    assert c.key_index == 1  # key 0 is cooling down

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "key_index=0" in messages
    assert "alpha-secret-value" not in messages
    assert "bravo-secret-value" not in messages
    assert "FINNHUB" not in messages or "key_index" in messages


def test_missing_keys_names_env_var(store) -> None:
    pool = KeyPool(
        provider="finnhub",
        env_var="FINNHUB_KEYS",
        store=store,
        keys=[],
        signup_url="https://finnhub.io/register",
        needed_in_phase=6,
    )
    with pytest.raises(MissingAPIKey) as exc:
        pool.acquire()
    assert exc.value.env_var == "FINNHUB_KEYS"
    assert exc.value.phase == 6
    assert "https://finnhub.io/register" in str(exc.value)


def test_all_keys_cooling_down(store) -> None:
    pool = KeyPool(
        provider="demo",
        env_var="DEMO_KEYS",
        store=store,
        keys=["k0", "k1"],
        base_cooldown_seconds=60,
    )
    i0 = pool.acquire().key_index
    i1 = pool.acquire().key_index
    pool.report(i0, 429)
    pool.report(i1, 429)
    with pytest.raises(AllKeysCoolingDown):
        pool.acquire(wait=False)


def test_secrets_never_written_to_sqlite(store) -> None:
    pool = KeyPool(
        provider="demo",
        env_var="DEMO_KEYS",
        store=store,
        keys=["super-secret-key-xyz"],
    )
    lease = pool.acquire()
    pool.report(lease.key_index, 200)
    rows = store.fetchall("SELECT * FROM key_rate_limits")
    dumped = " ".join(str(tuple(r)) for r in rows)
    assert "super-secret-key-xyz" not in dumped


def test_keys_from_env_merges_comma_and_numbered_aliases(monkeypatch) -> None:
    for name in list(os.environ):
        if "FINNHUB" in name:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FINNHUB_KEYS", "aaa,bbb")
    monkeypatch.setenv("FINNHUB_KEYS_1", "ccc")
    monkeypatch.setenv("FINNHUB_API_KEY_2", "ddd")
    assert keys_from_env("FINNHUB_KEYS") == ["aaa", "bbb", "ccc", "ddd"]


def test_keys_from_env_twelve_data_numbered(monkeypatch) -> None:
    for name in list(os.environ):
        if "TWELVE_DATA" in name:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TWELVE_DATA_API_KEY_1", "t1")
    monkeypatch.setenv("TWELVE_DATA_API_KEY_2", "t2")
    assert keys_from_env("TWELVE_DATA_KEYS") == ["t1", "t2"]


def test_quota_window_skips_exhausted_key(store) -> None:
    pool = KeyPool(
        provider="demo",
        env_var="DEMO_KEYS",
        store=store,
        keys=["k0", "k1"],
        max_requests_per_window=1,
        window_seconds=3600,
    )
    first = pool.acquire()
    assert first.key_index == 0
    second = pool.acquire()
    assert second.key_index == 1
