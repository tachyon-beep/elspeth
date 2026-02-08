# tests_v2/integration/conftest.py
"""Integration test configuration.

Function-scoped databases for full isolation per test.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from elspeth.contracts.payload_store import PayloadStore
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.plugins.manager import PluginManager
from tests_v2.fixtures.stores import MockPayloadStore


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply integration marker to all tests in this directory."""
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options for integration tests."""
    parser.addoption(
        "--keyvault-url",
        action="store",
        default=None,
        help="Azure Key Vault URL for integration tests",
    )


@pytest.fixture
def keyvault_url(request: pytest.FixtureRequest) -> str:
    """Get Key Vault URL from command line or environment."""
    url = request.config.getoption("--keyvault-url") or os.environ.get(
        "TEST_KEYVAULT_URL"
    )
    if not url:
        pytest.skip("Key Vault URL not configured.")
    return url


@pytest.fixture
def payload_store() -> PayloadStore:
    """In-memory PayloadStore for integration tests."""
    return MockPayloadStore()


@pytest.fixture
def landscape_db() -> LandscapeDB:
    """Function-scoped in-memory LandscapeDB — fresh per test."""
    return LandscapeDB.in_memory()


@pytest.fixture
def recorder(landscape_db: LandscapeDB) -> LandscapeRecorder:
    """Function-scoped LandscapeRecorder."""
    return LandscapeRecorder(landscape_db)


@pytest.fixture
def plugin_manager() -> PluginManager:
    """Standard plugin manager with builtin plugins registered."""
    manager = PluginManager()
    manager.register_builtin_plugins()
    return manager


@pytest.fixture
def resume_test_env(tmp_path: Path) -> dict[str, Any]:
    """Complete test environment for resume/checkpoint tests."""
    from elspeth.contracts.config.runtime import RuntimeCheckpointConfig
    from elspeth.core.checkpoint import CheckpointManager, RecoveryManager
    from elspeth.core.config import CheckpointSettings
    from elspeth.core.payload_store import FilesystemPayloadStore

    db = LandscapeDB(f"sqlite:///{tmp_path}/test.db")
    payload_store = FilesystemPayloadStore(tmp_path / "payloads")
    checkpoint_mgr = CheckpointManager(db)
    recovery_mgr = RecoveryManager(db, checkpoint_mgr)
    checkpoint_settings = CheckpointSettings(frequency="every_row")
    checkpoint_config = RuntimeCheckpointConfig.from_settings(checkpoint_settings)
    recorder = LandscapeRecorder(db)

    return {
        "db": db,
        "payload_store": payload_store,
        "checkpoint_manager": checkpoint_mgr,
        "recovery_manager": recovery_mgr,
        "checkpoint_config": checkpoint_config,
        "recorder": recorder,
        "tmp_path": tmp_path,
    }
