"""Tests for ADR-003 PLUGIN_TYPE_REGISTRY - Security-Critical Infrastructure.

SECURITY RATIONALE:
PLUGIN_TYPE_REGISTRY is the authoritative source for all plugin types that must
undergo security validation. Missing entries = bypassed validation = security breach.

These tests enforce completeness:
1. test_plugin_registry_complete() - Verifies ALL plugin attributes are registered
2. test_plugin_registry_cardinality() - Verifies singleton vs list classification
3. test_collect_all_plugins_from_runner() - Verifies collection actually works
4. test_collect_all_plugins_handles_none() - Verifies robustness with optional plugins

Test-Driven Development (TDD) Workflow:
- RED: Tests written first (current state - will fail)
- GREEN: Implementation added to make tests pass
- REFACTOR: Clean up while keeping tests green
"""

import pytest

from elspeth.core.experiments.runner import ExperimentRunner


class TestPluginTypeRegistryCompleteness:
    """SECURITY TESTS: Verify PLUGIN_TYPE_REGISTRY covers all plugin attributes.

    These tests prevent the "forgot to register a plugin type" attack where
    plugins bypass security validation by not being included in the registry.
    """

    def test_plugin_registry_exists(self):
        """PLUGIN_TYPE_REGISTRY module and constant must exist.

        RED: This test will fail because we haven't created the module yet.
        """
        from elspeth.core.base.plugin_types import PLUGIN_TYPE_REGISTRY

        assert PLUGIN_TYPE_REGISTRY is not None
        assert isinstance(PLUGIN_TYPE_REGISTRY, dict)

    def test_plugin_registry_complete(self):
        """SECURITY: Verify ALL plugin attributes in ExperimentRunner are registered.

        This test prevents bypass attacks where a new plugin attribute is added
        but not registered, allowing it to skip security validation.

        Strategy:
        1. Inspect ExperimentRunner attributes (ground truth)
        2. Filter for plugin-like attributes (end with _plugin, _client, _sink, etc.)
        3. Verify each is in PLUGIN_TYPE_REGISTRY
        4. FAIL LOUDLY if any are missing (security breach)
        """
        from elspeth.core.base.plugin_types import PLUGIN_TYPE_REGISTRY

        # Ground truth: All potential plugin attributes in ExperimentRunner
        # These are attributes that could contain BasePlugin instances
        expected_plugin_attrs = {
            "llm_client",  # LLMClientProtocol singleton
            "sinks",  # list[ResultSink]
            "row_plugins",  # list[RowExperimentPlugin] | None
            "aggregator_plugins",  # list[AggregationExperimentPlugin] | None
            "validation_plugins",  # list[ValidationPlugin] | None
            "rate_limiter",  # RateLimiter | None singleton
            "cost_tracker",  # CostTracker | None singleton
            "llm_middlewares",  # list[LLMMiddleware] | None
            "early_stop_plugins",  # list[EarlyStopPlugin] | None
            "malformed_data_sink",  # ResultSink | None singleton
        }

        # Get registered attributes from PLUGIN_TYPE_REGISTRY
        registered_attrs = set(PLUGIN_TYPE_REGISTRY.keys())

        # Find missing attributes (SECURITY BREACH if any)
        missing = expected_plugin_attrs - registered_attrs

        assert not missing, (
            f"SECURITY VIOLATION: Plugin attributes exist in ExperimentRunner but NOT in PLUGIN_TYPE_REGISTRY: {missing}\n"
            f"These plugins will BYPASS security validation!\n"
            f"Add them to PLUGIN_TYPE_REGISTRY in src/elspeth/core/base/plugin_types.py"
        )

        # Find extra attributes (code cleanup needed if any)
        extra = registered_attrs - expected_plugin_attrs

        # Extra attributes are less critical but indicate registry drift
        if extra:
            pytest.fail(
                f"PLUGIN_TYPE_REGISTRY contains attributes not in ExperimentRunner: {extra}\n"
                f"These may be obsolete entries that should be removed."
            )

    def test_plugin_registry_cardinality(self):
        """Verify plugin attributes have correct cardinality (singleton vs list).

        SECURITY: Incorrect cardinality classification could cause collect_all_plugins()
        to mishandle plugins, leading to incomplete security validation.
        """
        from elspeth.core.base.plugin_types import PLUGIN_TYPE_REGISTRY

        # Expected cardinalities based on ExperimentRunner type hints
        expected_cardinalities = {
            # Singletons (single plugin instance)
            "llm_client": "singleton",
            "rate_limiter": "singleton",
            "cost_tracker": "singleton",
            "malformed_data_sink": "singleton",
            # Lists (multiple plugin instances)
            "sinks": "list",
            "row_plugins": "list",
            "aggregator_plugins": "list",
            "validation_plugins": "list",
            "llm_middlewares": "list",
            "early_stop_plugins": "list",
        }

        for attr_name, expected_cardinality in expected_cardinalities.items():
            assert attr_name in PLUGIN_TYPE_REGISTRY, f"Attribute {attr_name} missing from registry"

            entry = PLUGIN_TYPE_REGISTRY[attr_name]
            actual_cardinality = entry.get("cardinality")

            assert actual_cardinality == expected_cardinality, (
                f"Cardinality mismatch for {attr_name}: "
                f"expected '{expected_cardinality}', got '{actual_cardinality}'"
            )


class TestCollectAllPlugins:
    """Tests for collect_all_plugins() helper function.

    This function is used by compute_minimum_clearance_envelope() to gather
    all plugins for security validation. Missing plugins = security breach.
    """

    def test_collect_all_plugins_exists(self):
        """collect_all_plugins() function must exist.

        RED: This test will fail because we haven't created the function yet.
        """
        from elspeth.core.base.plugin_types import collect_all_plugins

        assert collect_all_plugins is not None
        assert callable(collect_all_plugins)

    def test_collect_all_plugins_from_runner(self):
        """collect_all_plugins() should extract plugins from ExperimentRunner.

        Tests the actual collection logic by creating a mock runner with plugins.
        """
        from elspeth.core.base.plugin import BasePlugin
        from elspeth.core.base.plugin_types import collect_all_plugins
        from elspeth.core.base.types import SecurityLevel

        # Create mock plugins with security levels
        class MockLLMClient(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.OFFICIAL, allow_downgrade=True)

        class MockSink(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)

        class MockRowPlugin(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)

        class MockRateLimiter(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)

        # Create a mock runner with some plugins
        class MockRunner:
            def __init__(self):
                self.llm_client = MockLLMClient()  # Singleton
                self.sinks = [MockSink(), MockSink()]  # List of 2
                self.row_plugins = [MockRowPlugin()]  # List of 1
                self.aggregator_plugins = None  # None (optional)
                self.validation_plugins = []  # Empty list
                self.rate_limiter = MockRateLimiter()  # Singleton
                self.cost_tracker = None  # None
                self.llm_middlewares = []  # Empty list
                self.early_stop_plugins = None  # None
                self.malformed_data_sink = None  # None

        runner = MockRunner()
        plugins = collect_all_plugins(runner)

        # Should collect: llm_client (1) + sinks (2) + row_plugins (1) + rate_limiter (1) = 5
        assert len(plugins) == 5, f"Expected 5 plugins, got {len(plugins)}"

        # Verify all collected items are BasePlugin instances
        for plugin in plugins:
            assert isinstance(plugin, BasePlugin), f"Non-BasePlugin collected: {type(plugin)}"

        # Verify specific plugins were collected
        plugin_types = [type(p).__name__ for p in plugins]
        assert "MockLLMClient" in plugin_types
        assert plugin_types.count("MockSink") == 2
        assert "MockRowPlugin" in plugin_types
        assert "MockRateLimiter" in plugin_types

    def test_collect_all_plugins_handles_none_values(self):
        """collect_all_plugins() should gracefully handle None and empty lists.

        SECURITY: Must not crash or skip validation when optional plugins are None.
        """
        from elspeth.core.base.plugin import BasePlugin
        from elspeth.core.base.plugin_types import collect_all_plugins
        from elspeth.core.base.types import SecurityLevel

        class MockLLMClient(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.OFFICIAL, allow_downgrade=True)

        # Create a runner with minimal plugins (most are None)
        class MockRunner:
            def __init__(self):
                self.llm_client = MockLLMClient()  # Only non-None singleton
                self.sinks = []  # Empty list
                self.row_plugins = None  # None
                self.aggregator_plugins = None
                self.validation_plugins = None
                self.rate_limiter = None  # None singleton
                self.cost_tracker = None
                self.llm_middlewares = None
                self.early_stop_plugins = None
                self.malformed_data_sink = None

        runner = MockRunner()
        plugins = collect_all_plugins(runner)

        # Should collect only llm_client
        assert len(plugins) == 1
        assert isinstance(plugins[0], BasePlugin)
        assert type(plugins[0]).__name__ == "MockLLMClient"

    def test_collect_all_plugins_ignores_non_baseplugin(self):
        """collect_all_plugins() should only collect BasePlugin instances.

        SECURITY: Prevents collecting non-plugin objects that don't need validation.
        """
        from elspeth.core.base.plugin import BasePlugin
        from elspeth.core.base.plugin_types import collect_all_plugins
        from elspeth.core.base.types import SecurityLevel

        class MockLLMClient(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.OFFICIAL, allow_downgrade=True)

        class NotAPlugin:
            """Not a BasePlugin - should be ignored."""

            pass

        # Create a runner with mix of BasePlugin and non-BasePlugin
        class MockRunner:
            def __init__(self):
                self.llm_client = NotAPlugin()  # Not a BasePlugin (e.g., raw LLM client)
                self.sinks = [BasePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)]
                self.row_plugins = None
                self.aggregator_plugins = None
                self.validation_plugins = None
                self.rate_limiter = None
                self.cost_tracker = None
                self.llm_middlewares = None
                self.early_stop_plugins = None
                self.malformed_data_sink = None

        runner = MockRunner()
        plugins = collect_all_plugins(runner)

        # Should collect only the sink (BasePlugin), not the llm_client (NotAPlugin)
        assert len(plugins) == 1
        assert isinstance(plugins[0], BasePlugin)


class TestPluginTypeRegistryDocumentation:
    """Documentation and structure tests for PLUGIN_TYPE_REGISTRY."""

    def test_registry_entries_have_required_fields(self):
        """Each registry entry must have 'cardinality' field."""
        from elspeth.core.base.plugin_types import PLUGIN_TYPE_REGISTRY

        for attr_name, entry in PLUGIN_TYPE_REGISTRY.items():
            assert "cardinality" in entry, f"Entry '{attr_name}' missing 'cardinality' field"
            assert entry["cardinality"] in ["singleton", "list"], (
                f"Entry '{attr_name}' has invalid cardinality: {entry['cardinality']}"
            )
