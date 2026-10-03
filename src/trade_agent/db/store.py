"""SQLite store. All timestamps written by callers must be UTC ISO-8601."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from trade_agent.core.timeutil import utcnow_iso

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Store:
    """Thin SQLite wrapper with WAL and schema migrations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")

    def migrate(self) -> int:
        """Apply ``schema.sql`` if needed. Returns the current schema version."""
        current = self._current_version()
        if current >= SCHEMA_VERSION:
            return current
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        self._conn.executescript(sql)
        self.execute(
            "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, utcnow_iso()),
        )
        return SCHEMA_VERSION

    def _current_version(self) -> int:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if row is None:
            return 0
        ver = self._conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        return int(ver or 0)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, tuple(params))
        self._conn.commit()
        return cur

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, tuple(params)).fetchall()

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, tuple(params)).fetchone()

    def table_names(self) -> list[str]:
        rows = self.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [r["name"] for r in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
