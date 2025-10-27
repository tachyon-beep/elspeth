"""Tests for ADR-003 Automated Plugin Discovery - Security-Critical Infrastructure.

SECURITY RATIONALE:
Automated discovery prevents registration bypass attacks where plugins are loaded
directly without going through security validation. By automatically importing all
plugin modules, we ensure EVERY internal plugin undergoes validation.

Attack Vectors Prevented:
1. Direct Import Bypass - Developer imports plugin directly without registration
2. Forgotten Registration - Plugin exists but registration call omitted
3. Import Order Attack - Side effects skipped due to import ordering
4. Configuration Drift - New plugins added without registry updates

Test-Driven Development (TDD) Workflow:
- RED: Tests written first (current state - will fail)
- GREEN: Implementation added to make tests pass
- REFACTOR: Clean up while keeping tests green
"""

import logging
from unittest.mock import MagicMock, patch

import pytest


class TestAutoDiscovery:
    """Tests for automated plugin discovery infrastructure."""

    def test_auto_discover_module_exists(self):
        """auto_discover module and function must exist.

        RED: This test will fail because we haven't created the module yet.
        """
        from elspeth.core.registry.auto_discover import auto_discover_internal_plugins

        assert auto_discover_internal_plugins is not None
        assert callable(auto_discover_internal_plugins)

    def test_auto_discover_scans_plugins_directory(self):
        """auto_discover_internal_plugins() should scan src/elspeth/plugins/ recursively.

        Strategy:
        1. Call auto_discover_internal_plugins()
        2. Verify it attempts to import plugin modules
        3. Check that key plugin modules are discovered
        """
        from elspeth.core.registry.auto_discover import auto_discover_internal_plugins

        # Mock importlib.import_module to track what gets imported
        with patch("importlib.import_module") as mock_import:
            # Don't actually import (would trigger side effects)
            mock_import.return_value = MagicMock()

            # Call discovery
            auto_discover_internal_plugins()

            # Should have attempted to import multiple plugin modules
            assert mock_import.call_count > 0, "Should attempt to import plugin modules"

            # Get all module names that were imported
            imported_modules = [call[0][0] for call in mock_import.call_args_list]

            # Verify key plugin modules were discovered
            # (using any() to handle different discovery orders)
            has_datasource = any("datasource" in mod or "sources" in mod for mod in imported_modules)
            has_sink = any("sink" in mod for mod in imported_modules)
            has_llm = any("llm" in mod or "transforms" in mod for mod in imported_modules)

            assert has_datasource, f"Should discover datasource plugins, got: {imported_modules}"
            assert has_sink, f"Should discover sink plugins, got: {imported_modules}"
            assert has_llm, f"Should discover LLM plugins, got: {imported_modules}"

    def test_auto_discover_handles_import_errors_gracefully(self):
        """auto_discover_internal_plugins() should handle broken plugins gracefully.

        SECURITY: A broken plugin should not prevent discovery of other plugins.
        We log the error but continue discovery to maximize security coverage.
        """
        from elspeth.core.registry.auto_discover import auto_discover_internal_plugins

        # Mock importlib.import_module to fail on some imports
        with patch("importlib.import_module") as mock_import:

            def selective_fail(module_name):
                if "broken_plugin" in module_name:
                    raise ImportError(f"Simulated import error for {module_name}")
                return MagicMock()

            mock_import.side_effect = selective_fail

            # Should not raise despite import errors
            try:
                auto_discover_internal_plugins()
                # Success - graceful degradation
            except Exception as e:
                pytest.fail(f"auto_discover should handle import errors gracefully, but raised: {e}")

    def test_auto_discover_logs_discovered_modules(self):
        """auto_discover_internal_plugins() should log discovered modules for audit trail.

        SECURITY: Audit logging helps detect unexpected plugins or bypass attempts.
        """
        from elspeth.core.registry.auto_discover import auto_discover_internal_plugins

        # Run actual discovery (not mocked) to verify logging
        # This will import real plugins and log discovery activity
        with patch("elspeth.core.registry.auto_discover.logger") as mock_logger:
            auto_discover_internal_plugins()

            # Should have logged discovery activity (debug for each module, info for summary)
            assert mock_logger.debug.call_count > 0 or mock_logger.info.call_count > 0, (
                "Should log discovery activity for audit trail"
            )

    def test_auto_discover_skips_private_modules(self):
        """auto_discover_internal_plugins() should skip __pycache__, __init__, etc.

        SECURITY: Private modules and cache directories shouldn't be imported
        (they may contain test fixtures or generated code).
        """
        from elspeth.core.registry.auto_discover import auto_discover_internal_plugins

        with patch("importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()

            auto_discover_internal_plugins()

            # Get all module names that were imported
            imported_modules = [call[0][0] for call in mock_import.call_args_list]

            # Verify no private modules were imported
            for module in imported_modules:
                assert "__pycache__" not in module, f"Should not import __pycache__: {module}"
                # __init__ modules are OK to import (they register plugins)
                # but verify no .pyc files
                assert not module.endswith(".pyc"), f"Should not import .pyc files: {module}"


class TestDiscoveryValidation:
    """Tests for discovery validation layer - catches missing plugins."""

    def test_validate_discovery_function_exists(self):
        """validate_discovery() function must exist.

        RED: This test will fail because we haven't created the function yet.
        """
        from elspeth.core.registry.auto_discover import validate_discovery

        assert validate_discovery is not None
        assert callable(validate_discovery)

    def test_validate_discovery_checks_expected_plugins(self):
        """validate_discovery() should verify expected plugins are registered.

        SECURITY: This prevents bypass attacks where plugins exist but aren't registered.
        If a developer adds a plugin without registering it, this test catches it.
        """
        from elspeth.core.registry.auto_discover import validate_discovery

        # Mock registries with ALL expected plugins registered (from EXPECTED_PLUGINS)
        # Updated for VULN-010 fix: Expanded from 8 to 29 plugins (100% coverage)
        mock_registries = {
            "datasource": MagicMock(list_plugins=lambda: ["local_csv", "csv_blob", "azure_blob"]),
            "llm": MagicMock(list_plugins=lambda: ["mock", "azure_openai", "http_openai", "static_test"]),
            "sink": MagicMock(list_plugins=lambda: [
                "csv", "signed_artifact", "local_bundle",
                "excel_workbook",
                "azure_blob", "azure_blob_artifacts",
                "zip_bundle", "reproducibility_bundle",
                "github_repo", "azure_devops_repo", "azure_devops_artifact_repo",
                "analytics_report", "analytics_visual", "enhanced_visual",
                "embeddings_store", "file_copy",
            ]),
            "middleware": MagicMock(list_plugins=lambda: [
                "audit_logger", "azure_content_safety", "azure_environment",
                "classified_material", "health_monitor", "pii_shield", "prompt_shield",
            ]),
        }

        # Should pass with expected plugins present
        try:
            validate_discovery(mock_registries)
            # Success
        except Exception as e:
            pytest.fail(f"validate_discovery should pass with expected plugins, but raised: {e}")

    def test_validate_discovery_fails_on_missing_plugins(self):
        """validate_discovery() should raise SecurityValidationError if expected plugins missing.

        SECURITY: This is critical - missing plugins = bypassed validation = breach.
        """
        from elspeth.core.registry.auto_discover import validate_discovery
        from elspeth.core.validation.base import SecurityValidationError

        # Mock registries with MISSING expected plugins
        mock_registries = {
            "datasource": MagicMock(list_plugins=lambda: []),  # Empty - missing expected plugins!
            "llm": MagicMock(list_plugins=lambda: []),
            "sink": MagicMock(list_plugins=lambda: []),
        }

        # Should raise SecurityValidationError
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_discovery(mock_registries)

        error_msg = str(exc_info.value).lower()

        # Error should mention missing plugins
        assert "missing" in error_msg or "expected" in error_msg, (
            f"Error should mention missing plugins, got: {exc_info.value}"
        )

    def test_validate_discovery_logs_validation_results(self):
        """validate_discovery() should log validation results for audit trail.

        SECURITY: Audit trail helps track which plugins were validated.
        """
        from elspeth.core.registry.auto_discover import validate_discovery

        mock_registries = {
            "datasource": MagicMock(list_plugins=lambda: ["local_csv"]),
            "llm": MagicMock(list_plugins=lambda: ["mock"]),
            "sink": MagicMock(list_plugins=lambda: ["csv"]),
        }

        # Mock logger to verify logging
        with patch("elspeth.core.registry.auto_discover.logger") as mock_logger:
            try:
                validate_discovery(mock_registries)
            except Exception:
                pass  # May fail, but we're testing logging

            # Should have logged validation activity
            # (debug, info, or error depending on outcome)
            logged = (
                mock_logger.debug.call_count > 0
                or mock_logger.info.call_count > 0
                or mock_logger.error.call_count > 0
            )
            assert logged, "Should log validation activity for audit trail"


class TestDiscoverySecurity:
    """Security-focused tests for discovery bypass prevention."""

    def test_discovery_prevents_direct_instantiation_bypass(self):
        """SECURITY TEST: Verify direct instantiation without registration is unsafe.

        This test documents the security issue that auto-discovery prevents:
        If you instantiate a plugin directly (without registry), you bypass validation.

        Auto-discovery fixes this by ensuring ALL plugins go through registry.
        """
        from elspeth.core.base.plugin import BasePlugin
        from elspeth.core.base.types import SecurityLevel

        # Create a plugin directly (BYPASS - no registry involved)
        class UnsafePlugin(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)

        # Direct instantiation works (but bypasses validation)
        plugin = UnsafePlugin()
        assert plugin is not None

        # This is the security issue: plugin exists but was never validated
        # by security validation layer (no registry check, no ADR-002 enforcement)
        #
        # Auto-discovery prevents this by forcing all plugins through registry:
        # 1. Framework imports all plugin modules (triggers registration)
        # 2. validate_discovery() verifies expected plugins registered
        # 3. Fail-fast if plugins missing (catches bypasses)

    def test_auto_discover_function_signature(self):
        """Verify auto_discover_internal_plugins() signature for integration.

        The function should:
        - Take no required arguments (called at framework init)
        - Return discovery metadata (for validation/logging)
        - Be idempotent (safe to call multiple times)
        """
        from elspeth.core.registry.auto_discover import auto_discover_internal_plugins

        # Should be callable with no args
        try:
            # Use patch to avoid actual imports
            with patch("importlib.import_module"):
                result = auto_discover_internal_plugins()

            # Should return something (discovery metadata or None)
            # Type doesn't matter as long as it's consistent
            assert result is None or isinstance(result, (dict, list, int)), (
                f"Should return metadata or None, got: {type(result)}"
            )
        except TypeError as e:
            pytest.fail(f"auto_discover_internal_plugins() should be callable with no args, got: {e}")

    def test_validate_discovery_signature(self):
        """Verify validate_discovery() signature for integration.

        The function should:
        - Take registries dict as argument
        - Raise SecurityValidationError on validation failure
        - Be idempotent (safe to call multiple times)
        """
        from elspeth.core.registry.auto_discover import validate_discovery

        # Should accept registries dict
        try:
            mock_registries = {
                "datasource": MagicMock(list_plugins=lambda: ["local_csv"]),
            }

            # Should either succeed or raise SecurityValidationError (not other errors)
            from elspeth.core.validation.base import SecurityValidationError

            try:
                validate_discovery(mock_registries)
            except SecurityValidationError:
                # Expected on validation failure
                pass
        except TypeError as e:
            pytest.fail(f"validate_discovery() should accept registries dict, got: {e}")
