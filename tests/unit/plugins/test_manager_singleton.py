"""Tests for the shared plugin manager singleton."""

from __future__ import annotations

from elspeth.plugins.infrastructure.manager import PluginManager, get_shared_plugin_manager


class TestGetSharedPluginManager:
    """Tests for get_shared_plugin_manager()."""

    def test_returns_plugin_manager_instance(self) -> None:
        pm = get_shared_plugin_manager()
        assert isinstance(pm, PluginManager)

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        pm1 = get_shared_plugin_manager()
        pm2 = get_shared_plugin_manager()
        assert pm1 is pm2

    def test_has_builtin_sources_registered(self) -> None:
        pm = get_shared_plugin_manager()
        assert len(pm.get_sources()) > 0

    def test_has_builtin_transforms_registered(self) -> None:
        pm = get_shared_plugin_manager()
        assert len(pm.get_transforms()) > 0

    def test_has_builtin_sinks_registered(self) -> None:
        pm = get_shared_plugin_manager()
        assert len(pm.get_sinks()) > 0
