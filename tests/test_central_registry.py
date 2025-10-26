"""Tests for ADR-003 CentralPluginRegistry - Unified Registry Interface.

SECURITY RATIONALE:
CentralPluginRegistry provides a single enforcement point for all plugin operations,
ensuring every plugin registration goes through security validation. It wraps all
type-specific registries and automatically invokes auto-discovery at initialization.

Security Architecture:
1. Single entry point for all plugin operations (unified interface)
2. Automatic discovery at initialization (forces registration)
3. Validation layer after discovery (catches bypasses)
4. Type-safe plugin retrieval (prevents type confusion)

Attack Vectors Prevented:
1. Scattered Registration - Plugins registered in multiple places without validation
2. Initialization Bypass - Framework starts without discovery
3. Registry Confusion - Wrong plugin type retrieved from wrong registry
4. Manual Registration - Plugins added without going through discovery

Test-Driven Development (TDD) Workflow:
- RED: Tests written first (current state - will fail)
- GREEN: Implementation added to make tests pass
- REFACTOR: Clean up while keeping tests green
"""

import pytest
from unittest.mock import MagicMock, patch


class TestCentralRegistryInit:
    """Tests for CentralPluginRegistry initialization and setup."""

    def test_central_registry_module_exists(self):
        """CentralPluginRegistry class and module must exist.

        RED: This test will fail because we haven't created the module yet.
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        assert CentralPluginRegistry is not None
        assert callable(CentralPluginRegistry)

    def test_central_registry_initializes_with_type_registries(self):
        """CentralPluginRegistry should accept type-specific registry instances.

        The central registry wraps existing type-specific registries:
        - datasource_registry
        - llm_registry
        - sink_registry
        - experiment_registry
        - middleware_registry
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        # Mock type-specific registries with list_plugins() returning expected plugins
        mock_datasource = MagicMock()
        mock_datasource.list_plugins.return_value = ["local_csv", "csv_blob", "azure_blob"]

        mock_llm = MagicMock()
        mock_llm.list_plugins.return_value = ["mock", "azure_openai"]

        mock_sink = MagicMock()
        mock_sink.list_plugins.return_value = ["csv", "signed_artifact", "local_bundle"]

        # Should accept registries as constructor arguments
        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            try:
                registry = CentralPluginRegistry(
                    datasource_registry=mock_datasource,
                    llm_registry=mock_llm,
                    sink_registry=mock_sink,
                )
                assert registry is not None
            except TypeError as e:
                pytest.fail(f"CentralPluginRegistry should accept registry arguments, got: {e}")

    def test_central_registry_auto_discovers_on_init(self):
        """CentralPluginRegistry should call auto_discover_internal_plugins() on initialization.

        SECURITY: This ensures plugins are discovered automatically when registry is created,
        preventing initialization bypass attacks.
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        # Mock registries with list_plugins()
        mock_datasource = MagicMock()
        mock_datasource.list_plugins.return_value = ["local_csv", "csv_blob", "azure_blob"]

        mock_llm = MagicMock()
        mock_llm.list_plugins.return_value = ["mock", "azure_openai"]

        mock_sink = MagicMock()
        mock_sink.list_plugins.return_value = ["csv", "signed_artifact", "local_bundle"]

        # Mock auto_discover to verify it's called
        with patch("elspeth.core.registry.central.auto_discover_internal_plugins") as mock_discover:
            # Create registry
            CentralPluginRegistry(
                datasource_registry=mock_datasource,
                llm_registry=mock_llm,
                sink_registry=mock_sink,
            )

            # Should have called auto_discover once
            assert mock_discover.call_count == 1, (
                "CentralPluginRegistry should call auto_discover_internal_plugins() on init"
            )

    def test_central_registry_validates_discovery_on_init(self):
        """CentralPluginRegistry should call validate_discovery() after auto-discovery.

        SECURITY: This ensures expected plugins are present, catching bypass attempts.
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        mock_datasource = MagicMock(list_plugins=lambda: ["local_csv"])
        mock_llm = MagicMock(list_plugins=lambda: ["mock"])
        mock_sink = MagicMock(list_plugins=lambda: ["csv"])

        # Mock both auto_discover and validate_discovery
        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery") as mock_validate:
                # Create registry
                CentralPluginRegistry(
                    datasource_registry=mock_datasource,
                    llm_registry=mock_llm,
                    sink_registry=mock_sink,
                )

                # Should have called validate_discovery once with registries dict
                assert mock_validate.call_count == 1
                call_args = mock_validate.call_args[0][0]
                assert isinstance(call_args, dict), "Should pass registries dict to validate_discovery"


class TestCentralRegistryGetPlugin:
    """Tests for unified get_plugin() interface."""

    def test_get_plugin_retrieves_from_correct_registry(self):
        """create_plugin(plugin_type, plugin_name, options) should create from correct type registry.

        Unified interface for plugin creation across all types.
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        # Create mock registries with create() methods
        mock_datasource = MagicMock()
        mock_datasource.create.return_value = MagicMock(name="csv_plugin")

        mock_llm = MagicMock()
        mock_llm.create.return_value = MagicMock(name="openai_plugin")

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                registry = CentralPluginRegistry(
                    datasource_registry=mock_datasource,
                    llm_registry=mock_llm,
                    sink_registry=MagicMock(),
                )

                # Create datasource plugin
                plugin = registry.create_plugin("datasource", "local_csv", options={})
                assert plugin is not None
                mock_datasource.create.assert_called_once_with("local_csv", {})

                # Create llm plugin
                plugin = registry.create_plugin("llm", "azure_openai", options={})
                assert plugin is not None
                mock_llm.create.assert_called_once_with("azure_openai", {})

    def test_get_plugin_raises_on_unknown_type(self):
        """create_plugin() should raise KeyError for unknown plugin types.

        SECURITY: Prevents type confusion attacks where wrong plugin type is retrieved.
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                registry = CentralPluginRegistry(
                    datasource_registry=MagicMock(),
                    llm_registry=MagicMock(),
                    sink_registry=MagicMock(),
                )

                # Should raise KeyError for unknown type
                with pytest.raises(KeyError) as exc_info:
                    registry.create_plugin("invalid_type", "some_plugin", options={})

                assert "invalid_type" in str(exc_info.value)


class TestCentralRegistryListPlugins:
    """Tests for list_plugins() and list_all_plugins() methods."""

    def test_list_plugins_returns_names_for_type(self):
        """list_plugins(plugin_type) should return plugin names for specific type."""
        from elspeth.core.registry.central import CentralPluginRegistry

        mock_datasource = MagicMock()
        mock_datasource.list_plugins.return_value = ["local_csv", "csv_blob", "azure_blob"]

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                registry = CentralPluginRegistry(
                    datasource_registry=mock_datasource,
                    llm_registry=MagicMock(),
                    sink_registry=MagicMock(),
                )

                # List datasource plugins
                plugins = registry.list_plugins("datasource")
                assert plugins == ["local_csv", "csv_blob", "azure_blob"]
                mock_datasource.list_plugins.assert_called_once()

    def test_list_all_plugins_returns_dict_of_all_types(self):
        """list_all_plugins() should return dict mapping plugin type -> plugin names.

        Convenience method for discovering all registered plugins across all types.
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        mock_datasource = MagicMock()
        mock_datasource.list_plugins.return_value = ["local_csv", "csv_blob"]

        mock_llm = MagicMock()
        mock_llm.list_plugins.return_value = ["mock", "azure_openai"]

        mock_sink = MagicMock()
        mock_sink.list_plugins.return_value = ["csv", "json", "markdown"]

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                registry = CentralPluginRegistry(
                    datasource_registry=mock_datasource,
                    llm_registry=mock_llm,
                    sink_registry=mock_sink,
                )

                # Get all plugins
                all_plugins = registry.list_all_plugins()

                # Should return dict with all types
                assert isinstance(all_plugins, dict)
                assert all_plugins["datasource"] == ["local_csv", "csv_blob"]
                assert all_plugins["llm"] == ["mock", "azure_openai"]
                assert all_plugins["sink"] == ["csv", "json", "markdown"]


class TestCentralRegistryConvenience:
    """Tests for convenience methods (get_datasource, get_llm, get_sink, etc.)."""

    def test_get_datasource_convenience_method(self):
        """create_datasource(name, options) should be shorthand for create_plugin('datasource', name, options)."""
        from elspeth.core.registry.central import CentralPluginRegistry

        mock_datasource = MagicMock()
        mock_datasource.create.return_value = MagicMock(name="csv_plugin")

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                registry = CentralPluginRegistry(
                    datasource_registry=mock_datasource,
                    llm_registry=MagicMock(),
                    sink_registry=MagicMock(),
                )

                # Use convenience method
                plugin = registry.create_datasource("local_csv", options={})
                assert plugin is not None
                mock_datasource.create.assert_called_once_with("local_csv", {})

    def test_get_llm_convenience_method(self):
        """create_llm(name, options) should be shorthand for create_plugin('llm', name, options)."""
        from elspeth.core.registry.central import CentralPluginRegistry

        mock_llm = MagicMock()
        mock_llm.create.return_value = MagicMock(name="openai_plugin")

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                registry = CentralPluginRegistry(
                    datasource_registry=MagicMock(),
                    llm_registry=mock_llm,
                    sink_registry=MagicMock(),
                )

                # Use convenience method
                plugin = registry.create_llm("azure_openai", options={})
                assert plugin is not None
                mock_llm.create.assert_called_once_with("azure_openai", {})

    def test_get_sink_convenience_method(self):
        """create_sink(name, options) should be shorthand for create_plugin('sink', name, options)."""
        from elspeth.core.registry.central import CentralPluginRegistry

        mock_sink = MagicMock()
        mock_sink.create.return_value = MagicMock(name="csv_sink")

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                registry = CentralPluginRegistry(
                    datasource_registry=MagicMock(),
                    llm_registry=MagicMock(),
                    sink_registry=mock_sink,
                )

                # Use convenience method
                plugin = registry.create_sink("csv", options={})
                assert plugin is not None
                mock_sink.create.assert_called_once_with("csv", {})


class TestCentralRegistryGlobalInstance:
    """Tests for global registry instance pattern."""

    def test_global_registry_instance_exists(self):
        """Module should export a global 'central_registry' instance.

        This allows framework code to use a single shared registry instance.
        """
        from elspeth.core.registry.central import central_registry

        assert central_registry is not None
        # Should be a CentralPluginRegistry instance
        from elspeth.core.registry.central import CentralPluginRegistry

        assert isinstance(central_registry, CentralPluginRegistry)

    def test_global_registry_has_all_type_registries(self):
        """Global registry should be initialized with all type-specific registries."""
        from elspeth.core.registry.central import central_registry

        # Should have datasource, llm, sink registries at minimum
        # Test by calling list_plugins for each type
        try:
            central_registry.list_plugins("datasource")
            central_registry.list_plugins("llm")
            central_registry.list_plugins("sink")
        except KeyError as e:
            pytest.fail(f"Global registry missing required plugin type: {e}")


class TestCentralRegistrySecurity:
    """Security-focused tests for central registry."""

    def test_central_registry_validates_on_init_failure(self):
        """CentralPluginRegistry should raise SecurityValidationError if validation fails.

        SECURITY: If expected plugins are missing, registry creation should fail fast.
        """
        from elspeth.core.registry.central import CentralPluginRegistry
        from elspeth.core.validation.base import SecurityValidationError

        # Mock registries with missing plugins
        mock_datasource = MagicMock(list_plugins=lambda: [])  # Empty - missing expected!
        mock_llm = MagicMock(list_plugins=lambda: [])
        mock_sink = MagicMock(list_plugins=lambda: [])

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            # Should raise SecurityValidationError during init
            with pytest.raises(SecurityValidationError):
                CentralPluginRegistry(
                    datasource_registry=mock_datasource,
                    llm_registry=mock_llm,
                    sink_registry=mock_sink,
                )

    def test_central_registry_provides_audit_trail(self):
        """CentralPluginRegistry should log initialization and discovery for audit trail.

        SECURITY: Audit logging helps detect unexpected plugins or bypass attempts.
        """
        from elspeth.core.registry.central import CentralPluginRegistry

        with patch("elspeth.core.registry.central.auto_discover_internal_plugins"):
            with patch("elspeth.core.registry.central.validate_discovery"):
                with patch("elspeth.core.registry.central.logger") as mock_logger:
                    CentralPluginRegistry(
                        datasource_registry=MagicMock(),
                        llm_registry=MagicMock(),
                        sink_registry=MagicMock(),
                    )

                    # Should have logged initialization
                    assert (
                        mock_logger.info.call_count > 0 or mock_logger.debug.call_count > 0
                    ), "Should log initialization for audit trail"
