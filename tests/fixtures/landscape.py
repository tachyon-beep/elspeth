# tests/fixtures/landscape.py
"""Landscape database and recorder fixtures.

All fixtures are function-scoped for full test isolation.
No module-scoped databases — every test gets a fresh database.
"""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder


def make_landscape_db() -> LandscapeDB:
    """Factory for in-memory LandscapeDB."""
    return LandscapeDB.in_memory()


def make_recorder(db: LandscapeDB | None = None) -> LandscapeRecorder:
    """Factory for LandscapeRecorder."""
    if db is None:
        db = make_landscape_db()
    return LandscapeRecorder(db)


@pytest.fixture
def landscape_db() -> LandscapeDB:
    """Function-scoped in-memory LandscapeDB — fresh per test."""
    return make_landscape_db()


@pytest.fixture
def recorder(landscape_db: LandscapeDB) -> LandscapeRecorder:
    """Function-scoped LandscapeRecorder."""
    return LandscapeRecorder(landscape_db)


@pytest.fixture
def real_landscape_recorder_with_payload_store(landscape_db: LandscapeDB, tmp_path: Any) -> LandscapeRecorder:
    """LandscapeRecorder with real filesystem payload store."""
    from elspeth.core.payload_store import FilesystemPayloadStore

    payload_dir = tmp_path / "payloads"
    payload_store = FilesystemPayloadStore(payload_dir)
    return LandscapeRecorder(landscape_db, payload_store=payload_store)
