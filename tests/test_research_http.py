"""HTTP cache keys and logs must never retain API secrets."""

from __future__ import annotations

from types import SimpleNamespace

from trade_agent.core.keys import KeyPool
from trade_agent.research.http import CachedHTTP, _cache_key, redact_url


def test_redact_url_strips_secret_query() -> None:
    raw = "https://api.example/v1?apikey=SUPERSECRET&q=btc&token=tok123"
    safe = redact_url(raw)
    assert "SUPERSECRET" not in safe
    assert "tok123" not in safe
    assert "apikey=***" in safe
    assert "token=***" in safe
    assert "q=btc" in safe


def test_cache_key_ignores_secret_params() -> None:
    a = _cache_key(
        "fred",
        "https://api.stlouisfed.org/fred/series/observations",
        {"api_key": "SECRET_A", "series_id": "DGS10"},
        "param:api_key",
    )
    b = _cache_key(
        "fred",
        "https://api.stlouisfed.org/fred/series/observations",
        {"api_key": "SECRET_B", "series_id": "DGS10"},
        "param:api_key",
    )
    assert a == b


def test_cached_http_does_not_persist_secret(store, settings, monkeypatch) -> None:
    secret = "unit-test-only-secret-zzzz"
    pool = KeyPool(
        provider="demo",
        env_var="DEMO_KEYS",
        store=store,
        keys=[secret],
        max_requests_per_window=50,
    )
    http = CachedHTTP(store, settings.data_dir, default_ttl=3600)

    class _Resp:
        status_code = 200
        text = '{"ok": true}'
        url = "https://api.example/v1?apikey=unit-test-only-secret-zzzz&q=1"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(http.session, "get", lambda *a, **k: _Resp())
    body = http.get_text(
        "https://api.example/v1",
        provider="demo",
        params={"q": 1},
        pool=pool,
        inject="param:apikey",
    )
    assert body == '{"ok": true}'
    row = store.fetchone("SELECT url FROM http_cache")
    assert secret not in row["url"]
    dumped = " ".join(str(dict(r)) for r in store.fetchall("SELECT * FROM http_cache"))
    assert secret not in dumped
    assert "apikey=***" in row["url"]


def test_cache_hit_skips_network(store, settings) -> None:
    http = CachedHTTP(store, settings.data_dir, default_ttl=3600)
    called = SimpleNamespace(n=0)

    class _Resp:
        status_code = 200
        text = "first"
        url = "https://api.example/cached"

        def raise_for_status(self) -> None:
            return None

    def _get(*_a, **_k):
        called.n += 1
        return _Resp()

    http.session.get = _get  # type: ignore[method-assign]
    assert http.get_text("https://api.example/cached", provider="demo") == "first"
    assert http.get_text("https://api.example/cached", provider="demo") == "first"
    assert called.n == 1
