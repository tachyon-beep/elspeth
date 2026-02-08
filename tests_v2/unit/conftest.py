# tests_v2/unit/conftest.py
"""Unit test configuration.

No database fixtures. No I/O. Pure logic tests only.
Provides shared in-memory fixtures (payload store, plugin manager).
"""

import pytest

from elspeth.contracts.payload_store import PayloadStore
from elspeth.plugins.manager import PluginManager
from tests_v2.fixtures.stores import MockPayloadStore


@pytest.fixture
def payload_store() -> PayloadStore:
    """In-memory PayloadStore for tests that need artifact storage."""
    return MockPayloadStore()


@pytest.fixture
def plugin_manager() -> PluginManager:
    """Standard plugin manager with builtin plugins registered."""
    manager = PluginManager()
    manager.register_builtin_plugins()
    return manager
