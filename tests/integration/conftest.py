# tests/integration/conftest.py
"""Integration test configuration.

Function-scoped databases for full isolation per test.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from elspeth.contracts.payload_store import PayloadStore
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.plugins.infrastructure.manager import PluginManager
from tests.fixtures.landscape import make_landscape_db, make_recorder
from tests.fixtures.stores import MockPayloadStore


@pytest.fixture(autouse=True)
def _inject_default_on_write_failure() -> Iterator[None]:
    """Ensure all BaseSink subclasses have _on_write_failure set.

    Production code injects this via cli_helpers from SinkSettings.
    Integration tests that construct sinks directly bypass that path.

    Patches BaseSink.__init__ to set _on_write_failure="discard" instead
    of None, so every sink constructed during integration tests gets the
    default. Uses direct patching because _on_write_failure is deliberately
    an annotation-only attribute (no class-level default).
    """
    from elspeth.plugins.infrastructure.base import BaseSink

    _original_init = BaseSink.__init__

    def _patched_init(self: BaseSink, config: Any) -> None:
        _original_init(self, config)
        self._on_write_failure = "discard"

    BaseSink.__init__ = _patched_init  # type: ignore[method-assign]
    yield
    BaseSink.__init__ = _original_init  # type: ignore[method-assign]


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
    url = request.config.getoption("--keyvault-url") or os.environ.get("TEST_KEYVAULT_URL")
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
    return make_landscape_db()


@pytest.fixture
def recorder(landscape_db: LandscapeDB) -> LandscapeRecorder:
    """Function-scoped LandscapeRecorder."""
    return make_recorder(landscape_db)


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
    recorder = make_recorder(db)

    return {
        "db": db,
        "payload_store": payload_store,
        "checkpoint_manager": checkpoint_mgr,
        "recovery_manager": recovery_mgr,
        "checkpoint_config": checkpoint_config,
        "recorder": recorder,
        "tmp_path": tmp_path,
    }
