# tests/unit/core/conftest.py
"""Core unit test fixtures.

Provides lightweight fixtures needed by core unit tests.
No database fixtures. No I/O.
"""

from __future__ import annotations

import pytest

from elspeth.plugins.manager import PluginManager


@pytest.fixture
def plugin_manager() -> PluginManager:
    """Standard plugin manager with builtin plugins registered.

    Used by DAG tests that build ExecutionGraph from config.
    Lightweight: just registers plugin hooks, no DB or I/O.
    """
    manager = PluginManager()
    manager.register_builtin_plugins()
    return manager
