# tests/e2e/conftest.py
"""E2E test configuration.

File-based SQLite databases and real payload stores.
No mocks except for external services.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from tests.fixtures.landscape import make_recorder


@pytest.fixture(autouse=True)
def _inject_default_on_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure all BaseSink subclasses have _on_write_failure set.

    Production code injects this via cli_helpers from SinkSettings.
    E2E tests that construct sinks directly bypass that path.
    """
    from elspeth.plugins.infrastructure.base import BaseSink

    monkeypatch.setattr(BaseSink, "_on_write_failure", "discard")


@pytest.fixture
def system_landscape_db(tmp_path: Path) -> LandscapeDB:
    """Function-scoped file-based LandscapeDB for E2E tests."""
    db_path = tmp_path / "audit.db"
    return LandscapeDB(f"sqlite:///{db_path}")


@pytest.fixture
def system_recorder(system_landscape_db: LandscapeDB) -> LandscapeRecorder:
    """Function-scoped recorder for E2E tests."""
    return make_recorder(system_landscape_db)


@pytest.fixture
def payload_store_path(tmp_path: Path) -> Path:
    """Create a payload store directory for E2E tests."""
    store_path = tmp_path / "payloads"
    store_path.mkdir()
    return store_path


@pytest.fixture
def example_pipeline_dir() -> Path:
    """Locate the examples/ directory in the repository."""
    return Path(__file__).resolve().parents[2] / "examples"
