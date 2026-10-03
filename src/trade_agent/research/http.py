"""Cached HTTP GET. Secrets never logged; query tokens are redacted."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from trade_agent.core.keys import KeyLease, KeyPool
from trade_agent.core.logging import get_logger
from trade_agent.core.paths import cache_body_path
from trade_agent.core.timeutil import from_iso, to_iso, utcnow
from trade_agent.db.store import Store

log = get_logger("research.http")

_SECRET_QS = re.compile(r"(?i)(api[_-]?key|token|apikey|access_token|x-api-key)")


class CachedHTTP:
    """GET with on-disk body cache and optional KeyPool."""

    def __init__(self, store: Store, data_dir, default_ttl: int = 3600) -> None:
        self.store = store
        self.data_dir = data_dir
        self.default_ttl = default_ttl
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "trade-agent-research/0.1 (+local research)"})

    def get_json(
        self,
        url: str,
        *,
        provider: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pool: KeyPool | None = None,
        inject: str = "param:apikey",
        ttl: int | None = None,
        timeout: float = 30.0,
    ) -> Any:
        raw = self.get_text(
            url,
            provider=provider,
            params=params,
            headers=headers,
            pool=pool,
            inject=inject,
            ttl=ttl,
            timeout=timeout,
        )
        return json.loads(raw) if raw else None

    def get_text(
        self,
        url: str,
        *,
        provider: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pool: KeyPool | None = None,
        inject: str = "param:apikey",
        ttl: int | None = None,
        timeout: float = 30.0,
    ) -> str:
        ttl = self.default_ttl if ttl is None else ttl
        params = dict(params or {})
        headers = dict(headers or {})
        cache_key = _cache_key(provider, url, params, inject)
        cached = self._read_cache(cache_key, ttl)
        if cached is not None:
            log.info("cache_hit provider=%s url=%s", provider, redact_url(url))
            return cached

        lease: KeyLease | None = None
        if pool is not None:
            lease = pool.acquire()
            _inject(lease, params, headers, inject)
        safe = redact_url(url)
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout)
            status = resp.status_code
            if lease is not None:
                pool.report(lease.key_index, status)
            if status == 429:
                log.warning("http 429 provider=%s url=%s", provider, safe)
                resp.raise_for_status()
            resp.raise_for_status()
            text = resp.text
            self._write_cache(cache_key, provider, redact_url(resp.url), status, text)
            log.info("http %s provider=%s url=%s bytes=%s", status, provider, safe, len(text))
            return text
        except requests.HTTPError as exc:
            if lease is not None and exc.response is not None:
                pool.report(lease.key_index, exc.response.status_code)
            raise

    def _read_cache(self, cache_key: str, ttl: int) -> str | None:
        row = self.store.fetchone("SELECT * FROM http_cache WHERE cache_key = ?", (cache_key,))
        if row is None:
            return None
        fetched = from_iso(row["fetched_at"])
        if (utcnow() - fetched).total_seconds() > ttl:
            return None
        path = cache_body_path(self.data_dir, row["body_sha256"])
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def _write_cache(self, cache_key: str, provider: str, url: str, status: int, body: str) -> None:
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        path = cache_body_path(self.data_dir, digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        now = to_iso(utcnow())
        self.store.execute(
            """
            INSERT INTO http_cache (
                cache_key, provider, url, fetched_at, expires_at, status_code,
                content_type, body_path, body_sha256
            ) VALUES (?, ?, ?, ?, NULL, ?, 'application/json', ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                status_code = excluded.status_code,
                body_path = excluded.body_path,
                body_sha256 = excluded.body_sha256
            """,
            (cache_key, provider, url, now, status, str(path), digest),
        )


def _inject(lease: KeyLease, params: dict, headers: dict, inject: str) -> None:
    kind, _, name = inject.partition(":")
    if kind == "header":
        headers[name] = lease.secret
    else:
        params[name or "apikey"] = lease.secret


def _cache_key(provider: str, url: str, params: dict, inject: str) -> str:
    # Do not include the secret in the cache key — only provider + path + public params.
    public = {k: v for k, v in params.items() if not _SECRET_QS.search(str(k))}
    blob = json.dumps({"p": provider, "u": url, "q": public, "i": inject}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def redact_url(url: str) -> str:
    """Strip secret-looking query parameters for logs."""
    parts = urlsplit(url)
    kept = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        if _SECRET_QS.search(k):
            kept.append((k, "***"))
        else:
            kept.append((k, v))
    query = urlencode(kept, safe="*")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def polite_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
