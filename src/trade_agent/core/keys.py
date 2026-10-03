"""Round-robin API key pool with per-key rate limits and 429 cooldown.

Logs and persisted state use *key_index* only. The secret never leaves memory
except as the return value of ``acquire`` to the caller that must send it.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from trade_agent.core.errors import AllKeysCoolingDown, MissingAPIKey
from trade_agent.core.logging import get_logger
from trade_agent.core.timeutil import from_iso, to_iso, utcnow
from trade_agent.db.store import Store

log = get_logger("keys")


@dataclass(frozen=True)
class KeyLease:
    """A leased key. ``secret`` must not be logged."""

    provider: str
    key_index: int
    secret: str


@dataclass
class _KeyState:
    window_started_at: str | None = None
    request_count: int = 0
    last_status: int | None = None
    consecutive_429: int = 0
    cooldown_until: str | None = None
    last_used_at: str | None = None


class KeyPool:
    """Pool of keys for one provider.

    Args:
        provider: Short name used in logs (e.g. ``finnhub``).
        env_var: Environment variable holding a comma-separated key list.
        store: SQLite store for cooldown persistence.
        max_requests_per_window: Soft quota per key per window.
        window_seconds: Quota window length.
        signup_url: Shown in ``MissingAPIKey`` so the operator knows where to go.
        needed_in_phase: Phase number that requires this pool.
        base_cooldown_seconds: First 429 wait; doubles each consecutive 429.
        max_cooldown_seconds: Cap on exponential backoff.
    """

    def __init__(
        self,
        provider: str,
        env_var: str,
        store: Store,
        *,
        max_requests_per_window: int = 60,
        window_seconds: int = 60,
        signup_url: str = "see provider dashboard",
        needed_in_phase: int = 0,
        base_cooldown_seconds: float = 2.0,
        max_cooldown_seconds: float = 300.0,
        keys: list[str] | None = None,
    ) -> None:
        self.provider = provider
        self.env_var = env_var
        self.store = store
        self.max_requests_per_window = max_requests_per_window
        self.window_seconds = window_seconds
        self.signup_url = signup_url
        self.needed_in_phase = needed_in_phase
        self.base_cooldown_seconds = base_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self._keys = keys if keys is not None else keys_from_env(env_var)
        self._lock = threading.Lock()
        self._rr = 0
        self._state: dict[int, _KeyState] = {i: _KeyState() for i in range(len(self._keys))}
        self._load_persisted()

    @property
    def size(self) -> int:
        return len(self._keys)

    def acquire(self, *, wait: bool = False, max_wait_seconds: float = 30.0) -> KeyLease:
        """Return the next usable key (round-robin, skip cooling-down / over-quota).

        Raises:
            MissingAPIKey: pool is empty.
            AllKeysCoolingDown: every key is cooling down and ``wait`` is False
                (or the wait budget expired).
        """
        if not self._keys:
            raise MissingAPIKey(
                self.provider, self.env_var, self.signup_url, self.needed_in_phase
            )

        deadline = time.monotonic() + max_wait_seconds
        while True:
            with self._lock:
                lease = self._try_acquire_locked()
                if lease is not None:
                    return lease
                sleep_for = self._soonest_wait_locked()
            if not wait or time.monotonic() + sleep_for > deadline:
                raise AllKeysCoolingDown(
                    f"provider={self.provider} all {self.size} keys cooling down"
                )
            time.sleep(min(sleep_for, 0.05))

    def report(self, key_index: int, status_code: int) -> None:
        """Record the HTTP status for a key. 429 starts exponential cooldown."""
        with self._lock:
            state = self._state[key_index]
            now = utcnow()
            state.last_status = status_code
            state.last_used_at = to_iso(now)
            if status_code == 429:
                state.consecutive_429 += 1
                delay = min(
                    self.base_cooldown_seconds * (2 ** (state.consecutive_429 - 1)),
                    self.max_cooldown_seconds,
                )
                from datetime import timedelta

                state.cooldown_until = to_iso(now + timedelta(seconds=delay))
                log.warning(
                    "provider=%s key_index=%s status=429 consecutive=%s cooldown_s=%.1f",
                    self.provider,
                    key_index,
                    state.consecutive_429,
                    delay,
                )
            else:
                if 200 <= status_code < 300:
                    state.consecutive_429 = 0
                    state.cooldown_until = None
                log.info(
                    "provider=%s key_index=%s status=%s",
                    self.provider,
                    key_index,
                    status_code,
                )
            self._persist_locked(key_index)

    def _try_acquire_locked(self) -> KeyLease | None:
        n = len(self._keys)
        now = utcnow()
        for step in range(n):
            idx = (self._rr + step) % n
            state = self._state[idx]
            if self._is_cooling(state, now):
                continue
            self._maybe_roll_window(state, now)
            if state.request_count >= self.max_requests_per_window:
                continue
            state.request_count += 1
            state.last_used_at = to_iso(now)
            self._rr = (idx + 1) % n
            self._persist_locked(idx)
            log.info("provider=%s acquired key_index=%s", self.provider, idx)
            return KeyLease(provider=self.provider, key_index=idx, secret=self._keys[idx])
        return None

    def _soonest_wait_locked(self) -> float:
        now = utcnow()
        waits: list[float] = []
        for state in self._state.values():
            if state.cooldown_until:
                remaining = (from_iso(state.cooldown_until) - now).total_seconds()
                waits.append(max(remaining, 0.01))
            elif state.window_started_at:
                remaining = self.window_seconds - (
                    now - from_iso(state.window_started_at)
                ).total_seconds()
                waits.append(max(remaining, 0.01))
        return min(waits) if waits else 0.05

    def _is_cooling(self, state: _KeyState, now) -> bool:
        if not state.cooldown_until:
            return False
        until = from_iso(state.cooldown_until)
        if now >= until:
            state.cooldown_until = None
            return False
        return True

    def _maybe_roll_window(self, state: _KeyState, now) -> None:
        if state.window_started_at is None:
            state.window_started_at = to_iso(now)
            state.request_count = 0
            return
        started = from_iso(state.window_started_at)
        if (now - started).total_seconds() >= self.window_seconds:
            state.window_started_at = to_iso(now)
            state.request_count = 0

    def _load_persisted(self) -> None:
        rows = self.store.fetchall(
            "SELECT key_index, window_started_at, request_count, last_status, "
            "consecutive_429, cooldown_until, last_used_at "
            "FROM key_rate_limits WHERE provider = ?",
            (self.provider,),
        )
        for row in rows:
            idx = int(row["key_index"])
            if idx not in self._state:
                continue
            self._state[idx] = _KeyState(
                window_started_at=row["window_started_at"],
                request_count=int(row["request_count"] or 0),
                last_status=row["last_status"],
                consecutive_429=int(row["consecutive_429"] or 0),
                cooldown_until=row["cooldown_until"],
                last_used_at=row["last_used_at"],
            )

    def _persist_locked(self, key_index: int) -> None:
        state = self._state[key_index]
        self.store.execute(
            """
            INSERT INTO key_rate_limits (
                provider, key_index, window_started_at, request_count,
                last_status, consecutive_429, cooldown_until, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, key_index) DO UPDATE SET
                window_started_at = excluded.window_started_at,
                request_count = excluded.request_count,
                last_status = excluded.last_status,
                consecutive_429 = excluded.consecutive_429,
                cooldown_until = excluded.cooldown_until,
                last_used_at = excluded.last_used_at
            """,
            (
                self.provider,
                key_index,
                state.window_started_at,
                state.request_count,
                state.last_status,
                state.consecutive_429,
                state.cooldown_until,
                state.last_used_at,
            ),
        )


_ALIASES: dict[str, tuple[str, ...]] = {
    "FINNHUB_KEYS": ("FINNHUB_API_KEY", "FINNHUB_KEY"),
    "NEWSAPI_KEYS": ("NEWSAPI_KEY", "NEWS_API_KEY"),
    "TWELVE_DATA_KEYS": ("TWELVE_DATA_API_KEY", "TWELVE_DATA_KEY"),
    "ALPHA_VANTAGE_KEYS": ("ALPHA_VANTAGE_KEY", "ALPHA_VANTAGE_API_KEY"),
    "FRED_API_KEY": ("FRED_KEY",),
    "GOLD_API_KEY": ("GOLDAPI_KEY", "GOLD_API_KEYS"),
}


def keys_from_env(env_var: str) -> list[str]:
    """Load a key pool from ``env_var``, comma lists, and numbered aliases.

    Example: ``FINNHUB_KEYS=a,b`` plus ``FINNHUB_KEYS_1=c`` yields ``[a, b, c]``.
    Also accepts ``TWELVE_DATA_API_KEY_1`` when the pool name is ``TWELVE_DATA_KEYS``.
    """
    found: list[str] = []
    for name in _env_aliases(env_var):
        raw = os.environ.get(name, "")
        for part in _parse_pool(raw):
            if part not in found:
                found.append(part)
    return found


def _env_aliases(env_var: str) -> list[str]:
    names = [env_var, *(_ALIASES.get(env_var, ()))]
    numbered: list[str] = []
    for name in names:
        for i in range(1, 16):
            numbered.append(f"{name}_{i}")
    out: list[str] = []
    for n in [*names, *numbered]:
        if n not in out:
            out.append(n)
    return out


def _parse_pool(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]
