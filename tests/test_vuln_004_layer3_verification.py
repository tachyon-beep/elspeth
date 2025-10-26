"""
VULN-004 Layer 3: Post-Creation Verification Tests

SECURITY: Verify plugin instances match their declared security level after creation.

ADR-002-B mandates security policy is declared at registration time (immutable).
Layer 3 catches implementation bugs where a plugin's constructor has incorrect
security_level hard-coded, diverging from the registry declaration.

Layer 3: Post-creation verification - Verify declared vs actual after instantiation.
"""

import pytest
from elspeth.core.validation.base import ConfigurationError
from elspeth.core.registries.base import BasePluginRegistry
from elspeth.core.base.plugin_context import PluginContext


class MockPlugin:
    """Mock plugin for testing with configurable security_level."""

    def __init__(self, security_level: str = "UNOFFICIAL", **kwargs):
        self._security_level = security_level
        self.options = kwargs

    @property
    def security_level(self):
        return self._security_level


class TestLayer3PostCreationVerification:
    """VULN-004 Layer 3: Post-creation verification must catch declared vs actual mismatch."""

    def test_plugin_with_mismatched_security_level_rejected(self):
        """SECURITY: Plugin declaring UNOFFICIAL but implementing SECRET must be rejected (Layer 3).

        ADR-002-B: Plugin declares security_level at registration, and implementation
        must match. This catches bugs where constructor has wrong security_level.
        """
        registry = BasePluginRegistry[MockPlugin]("test")

        # Register plugin declaring UNOFFICIAL security level
        # But factory creates plugin with SECRET (simulating implementation bug)
        def create_buggy_plugin(options: dict, context: PluginContext) -> MockPlugin:
            # BUG: Implementation returns SECRET instead of declared UNOFFICIAL
            return MockPlugin(security_level="SECRET", **options)

        registry.register(
            "buggy",
            create_buggy_plugin,
            declared_security_level="UNOFFICIAL",  # Declared at registration
        )

        # Attempt to create plugin - should detect mismatch
        with pytest.raises(
            ConfigurationError,
            match=r"Plugin declares security_level=UNOFFICIAL.*actual security_level=SECRET"
        ):
            registry.create(
                "buggy",
                options={},
                require_determinism=False,  # Focus on security_level verification
            )

    def test_plugin_with_matching_security_level_accepted(self):
        """Verify plugin with matching declared and actual security_level is accepted."""
        registry = BasePluginRegistry[MockPlugin]("test")

        # Register plugin with matching declaration and implementation
        def create_correct_plugin(options: dict, context: PluginContext) -> MockPlugin:
            return MockPlugin(security_level="UNOFFICIAL", **options)

        registry.register(
            "correct",
            create_correct_plugin,
            declared_security_level="UNOFFICIAL",
        )

        # Should succeed - declared matches actual
        try:
            plugin = registry.create(
                "correct",
                options={},
                require_determinism=False,
            )
            assert plugin is not None
            assert plugin.security_level == "UNOFFICIAL"
        except ConfigurationError as exc:
            pytest.fail(f"Valid matching plugin rejected: {exc}")

    def test_all_security_levels_verified(self):
        """Test verification for all security levels."""
        test_cases = [
            ("UNOFFICIAL", "PROTECTED"),     # Declared UNOFFICIAL, actual PROTECTED
            ("PROTECTED", "SECRET"),         # Declared PROTECTED, actual SECRET
            ("SECRET", "UNOFFICIAL"),        # Declared SECRET, actual UNOFFICIAL
            ("OFFICIAL", "SECRET"),          # Declared OFFICIAL, actual SECRET
        ]

        for declared, actual in test_cases:
            registry = BasePluginRegistry[MockPlugin]("test")

            def create_mismatched(options: dict, context: PluginContext) -> MockPlugin:
                return MockPlugin(security_level=actual, **options)

            registry.register(
                f"test_{declared}_{actual}",
                create_mismatched,
                declared_security_level=declared,
            )

            with pytest.raises(
                ConfigurationError,
                match=f"Plugin declares security_level={declared}.*actual security_level={actual}"
            ):
                registry.create(
                    f"test_{declared}_{actual}",
                    options={},
                    require_determinism=False,
                )
