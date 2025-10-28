"""
VULN-004 Layer 2: Registry Sanitization Tests

SECURITY: Verify create_*_from_definition() functions reject security_level
in configuration at runtime.

ADR-002-B mandates security policy is declared in plugin code and immutable.
YAML configuration must NOT be able to override via definition-level fields.

Layer 2: Runtime validation in create_*_from_definition() rejects security_level
at registration time (after schema validation, before plugin creation).
"""

import pytest
from elspeth.core.validation.base import ConfigurationError
from elspeth.core.registries.llm import create_llm_from_definition
from elspeth.core.base.plugin_context import PluginContext


class TestLayer2RegistrySanitization:
    """VULN-004 Layer 2: Runtime validation must reject security policy override."""

    def test_llm_rejects_definition_level_security_level(self):
        """SECURITY: create_llm_from_definition must reject security_level in definition (Layer 2).

        ADR-002-B: Security policy is immutable and declared in plugin code, not YAML.
        Even if schema validation is bypassed, registry must reject at runtime.
        """
        # Create minimal parent context
        parent_context = PluginContext(
            plugin_name="test_parent",
            plugin_kind="experiment",
            security_level="UNOFFICIAL",
            determinism_level="high",
        )

        # Definition with security_level at top level (ATTACK VECTOR)
        definition = {
            "plugin": "mock",
            "security_level": "SECRET",  # ⚠️ Attack: Try to override to SECRET
            "options": {
                "seed": 42,
            }
        }

        # Should raise ConfigurationError with ADR-002-B reference
        with pytest.raises(
            ConfigurationError,
            match=r"security_level cannot be specified in configuration.*ADR-002-B"
        ):
            create_llm_from_definition(
                definition,
                parent_context=parent_context,
            )

    def test_llm_rejects_options_level_security_level(self):
        """SECURITY: create_llm_from_definition must reject security_level in options.

        This tests the options-level rejection (defense-in-depth with Layer 1 schema).
        """
        parent_context = PluginContext(
            plugin_name="test_parent",
            plugin_kind="experiment",
            security_level="UNOFFICIAL",
            determinism_level="high",
        )

        # Definition with security_level INSIDE options (double attack)
        definition = {
            "plugin": "mock",
            "options": {
                "seed": 42,
                "security_level": "SECRET",  # ⚠️ Attack: Try to inject via options
            }
        }

        with pytest.raises(
            ConfigurationError,
            match=r"security_level cannot be specified in configuration.*ADR-002-B"
        ):
            create_llm_from_definition(
                definition,
                parent_context=parent_context,
            )

    def test_llm_accepts_valid_config_without_security_level(self):
        """Verify legitimate LLM configuration still works after Layer 2 enforcement."""
        parent_context = PluginContext(
            plugin_name="test_parent",
            plugin_kind="experiment",
            security_level="UNOFFICIAL",
            determinism_level="high",
        )

        # Valid definition WITHOUT security_level
        definition = {
            "plugin": "mock",
            "options": {
                "seed": 42,
            }
        }

        # Should succeed - security_level inherited from parent_context
        try:
            llm = create_llm_from_definition(
                definition,
                parent_context=parent_context,
            )
            # Verify plugin was created
            assert llm is not None
            # Verify it inherited security_level from context
            assert llm.security_level == "UNOFFICIAL"
        except ConfigurationError as exc:
            pytest.fail(f"Valid config rejected: {exc}")

    def test_llm_rejects_allow_downgrade_in_definition(self):
        """SECURITY: create_llm_from_definition must also reject allow_downgrade.

        ADR-002-B: allow_downgrade is part of immutable security policy.
        """
        parent_context = PluginContext(
            plugin_name="test_parent",
            plugin_kind="experiment",
            security_level="UNOFFICIAL",
            determinism_level="high",
        )

        definition = {
            "plugin": "mock",
            "allow_downgrade": True,  # ⚠️ Attack: Try to enable downgrade
            "options": {"seed": 42}
        }

        # Should raise ConfigurationError
        # Note: Current implementation may only check security_level, not allow_downgrade
        # This test documents expected behavior per ADR-002-B
        with pytest.raises(ConfigurationError):
            create_llm_from_definition(
                definition,
                parent_context=parent_context,
            )

    def test_llm_rejects_max_operating_level_in_definition(self):
        """SECURITY: create_llm_from_definition must also reject max_operating_level.

        ADR-002-B: max_operating_level is part of immutable security policy.
        """
        parent_context = PluginContext(
            plugin_name="test_parent",
            plugin_kind="experiment",
            security_level="UNOFFICIAL",
            determinism_level="high",
        )

        definition = {
            "plugin": "mock",
            "max_operating_level": "SECRET",  # ⚠️ Attack: Try to set max operating level
            "options": {"seed": 42}
        }

        # Should raise ConfigurationError
        with pytest.raises(ConfigurationError):
            create_llm_from_definition(
                definition,
                parent_context=parent_context,
            )

    def test_llm_allows_determinism_level_in_definition(self):
        """Verify determinism_level IS allowed (runtime context, not security policy).

        Contrast test: determinism_level is user-configurable, not immutable.
        """
        parent_context = PluginContext(
            plugin_name="test_parent",
            plugin_kind="experiment",
            security_level="UNOFFICIAL",
            determinism_level="low",
        )

        # Definition WITH determinism_level (should be allowed)
        definition = {
            "plugin": "mock",
            "determinism_level": "high",  # ✅ Allowed (runtime context)
            "options": {"seed": 42}
        }

        # Should succeed
        try:
            llm = create_llm_from_definition(
                definition,
                parent_context=parent_context,
            )
            assert llm is not None
            # Should use definition determinism_level, not parent
            # (determinism_level is configurable)
        except ConfigurationError as exc:
            pytest.fail(f"Valid config with determinism_level rejected: {exc}")
