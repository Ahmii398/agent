"""Shared fixtures. Each test gets an isolated data dir and migrated SQLite DB."""

from __future__ import annotations

from pathlib import Path

import pytest

from trade_agent.core.config import Settings, load_settings
from trade_agent.db.store import Store


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "var"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return load_settings(data_dir=data_dir, load_env=False)


@pytest.fixture
def store(settings: Settings) -> Store:
    s = Store(settings.db_path)
    s.migrate()
    yield s
    s.close()
