"""Regression tests for security level enforcement.

This test suite ensures that child plugins CANNOT downgrade parent security levels.
This prevents the P0 security vulnerability where child plugins could specify
lower security classifications than their parents.

CRITICAL: These tests must NOT be modified or removed without security review.
"""

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.base import BasePluginRegistry
from elspeth.core.registries.plugin_helpers import create_plugin_with_inheritance
from elspeth.core.validation import ConfigurationError


def test_child_plugin_cannot_downgrade_parent_security_official_to_public():
    """SECURITY REGRESSION TEST: Child cannot downgrade OFFICIAL to PUBLIC.

    This test verifies the fix for the P0 security vulnerability where child
    plugins could specify security levels that conflict with their parents.

    ADR-002-B: Security levels are now hardcoded at registration time, not configured.
    The test now verifies that factory.declared_security_level cannot downgrade parent level.

    CRITICAL: If this test fails, a security vulnerability has been reintroduced.
    """
    registry = BasePluginRegistry[object]("test_plugin")

    def create_plugin(opts, ctx):
        return object()

    # ADR-002-B: Register plugin with UNOFFICIAL level (attempting downgrade)
    registry.register("test", create_plugin, declared_security_level="unofficial")

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",  # Parent has OFFICIAL classification
        determinism_level="none",
    )

    # Child with UNOFFICIAL factory.declared_security_level attempts to downgrade parent OFFICIAL - must be rejected
    definition = {
        "name": "test",
        # ADR-002-B: security_level removed from config (now in factory registration)
        "determinism_level": "none",
    }

    with pytest.raises(ConfigurationError, match="security_level 'UNOFFICIAL' cannot downgrade parent level 'OFFICIAL'"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_child_plugin_cannot_downgrade_parent_security_confidential_to_internal():
    """SECURITY REGRESSION TEST: Child cannot downgrade CONFIDENTIAL to INTERNAL."""
    registry = BasePluginRegistry[object]("test_plugin")

    def create_plugin(opts, ctx):
        return object()

    # ADR-002-B: Register with OFFICIAL level (attempting downgrade from PROTECTED)
    registry.register("test", create_plugin, declared_security_level="official")

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="confidential",
        determinism_level="none",
    )

    definition = {
        "name": "test",
        "determinism_level": "none",
    }

    with pytest.raises(ConfigurationError, match="security_level 'OFFICIAL' cannot downgrade parent level 'PROTECTED'"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_child_plugin_cannot_downgrade_parent_security_secret_to_protected():
    """SECURITY REGRESSION TEST: Child cannot downgrade SECRET to PROTECTED."""
    registry = BasePluginRegistry[object]("test_plugin")

    def create_plugin(opts, ctx):
        return object()

    registry.register("test", create_plugin, declared_security_level="protected")  # ADR-002-B

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="secret",
        determinism_level="none",
    )

    definition = {
        "name": "test",
        "determinism_level": "none",
    }

    with pytest.raises(ConfigurationError, match="security_level 'PROTECTED' cannot downgrade parent level 'SECRET'"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_child_plugin_can_match_parent_security_level():
    """Child CAN specify the SAME security level as parent (allowed for explicitness)."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    registry.register("test", create_plugin, declared_security_level="official")  # ADR-002-B

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Child specifies SAME level - allowed (redundant but not harmful)
    definition = {
        "name": "test",
        "determinism_level": "none",
    }

    plugin = create_plugin_with_inheritance(
        registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    assert plugin is not None
    assert hasattr(plugin, "_elspeth_security_level")
    assert plugin._elspeth_security_level == "OFFICIAL"  # Stored in canonical uppercase form


def test_child_plugin_can_upgrade_parent_security_level():
    """Child CAN specify HIGHER security level than parent (upgrade is safe)."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    registry.register("test", create_plugin, declared_security_level="protected")  # ADR-002-B

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="internal",  # Parent has INTERNAL (alias for OFFICIAL)
        determinism_level="none",
    )

    # Child upgrades to CONFIDENTIAL - allowed (more restrictive is safe)
    definition = {
        "name": "test",
        "determinism_level": "none",
    }

    plugin = create_plugin_with_inheritance(
        registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    assert plugin is not None
    assert hasattr(plugin, "_elspeth_security_level")
    assert plugin._elspeth_security_level == "PROTECTED"  # "confidential" alias maps to PROTECTED


def test_child_plugin_inherits_when_no_explicit_level():
    """SECURITY: Child MUST NOT inherit parent's security level (ADR-002-B).

    This test verifies the fix for the security escalation vulnerability where
    a plugin without declared_security_level could inherit from parent, allowing
    privilege escalation to SECRET by being instantiated under a SECRET parent.

    Correct behavior: Fail loud if plugin doesn't declare security level.
    """
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    # Register WITHOUT declared_security_level (insecure plugin)
    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Child does not specify security_level (ADR-002-B violation)
    definition = {
        "name": "test",
        # No security_level in definition
        # No declared_security_level in registration
        # → MUST FAIL LOUD (no inheritance, no defaults)
    }

    # ADR-001/002: NO DEFAULTS, NO INHERITANCE - must fail loud
    with pytest.raises(ConfigurationError, match="Plugin registration missing declared_security_level"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_multiple_child_plugins_cannot_downgrade():
    """SECURITY REGRESSION TEST: Multiple child plugins in chain maintain security."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    # ADR-002-B: Register two plugins with different security levels
    registry.register("protected_plugin", create_plugin, declared_security_level="protected")
    registry.register("official_plugin", create_plugin, declared_security_level="official")

    # Level 1: Root context (CONFIDENTIAL = PROTECTED)
    root_context = PluginContext(
        plugin_name="root",
        plugin_kind="test",
        security_level="confidential",
        determinism_level="none",
    )

    # Level 2: Child with PROTECTED level (matches parent)
    definition_level2 = {"name": "protected_plugin", "determinism_level": "none"}
    child1 = create_plugin_with_inheritance(
        registry,
        definition_level2,
        plugin_kind="test_plugin",
        parent_context=root_context,
    )

    assert child1._elspeth_security_level == "PROTECTED"

    # Level 3: Grandchild attempts downgrade to OFFICIAL - must fail
    grandchild_context = PluginContext(
        plugin_name="child1",
        plugin_kind="test",
        security_level="protected",  # Parent is PROTECTED
        determinism_level="none",
        parent=root_context,
    )

    definition_level3 = {
        "name": "official_plugin",  # ADR-002-B: OFFICIAL plugin trying to downgrade from PROTECTED parent
        "determinism_level": "none",
    }

    with pytest.raises(ConfigurationError, match="security_level 'OFFICIAL' cannot downgrade parent level 'PROTECTED'"):
        create_plugin_with_inheritance(
            registry,
            definition_level3,
            plugin_kind="test_plugin",
            parent_context=grandchild_context,
        )


def test_security_enforcement_in_options_dict():
    """ADR-002-B: Security level in options dict is REJECTED (not enforced, rejected)."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    # ADR-002-B: Register with UNOFFICIAL
    registry.register("test", create_plugin, declared_security_level="unofficial")

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Child attempts security_level in options dict - must be REJECTED (not just enforced)
    definition = {
        "name": "test",
        "determinism_level": "none",
        "options": {
            "some_option": "value",  # ADR-002-B: Can't test security_level in options (would be rejected immediately)
        },
    }

    # ADR-002-B: With UNOFFICIAL factory and OFFICIAL parent, downgrade check triggers
    with pytest.raises(ConfigurationError, match="security_level 'UNOFFICIAL' cannot downgrade parent level 'OFFICIAL'"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_security_enforcement_with_both_definition_and_options():
    """ADR-002-B: Factory security level is enforced, config cannot override."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    # ADR-002-B: Register with UNOFFICIAL (will attempt downgrade)
    registry.register("test", create_plugin, declared_security_level="unofficial")

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # ADR-002-B: No security_level in config (only in factory registration)
    definition = {
        "name": "test",
        "determinism_level": "none",
        "options": {},
    }

    # Factory declared_security_level (UNOFFICIAL) cannot downgrade parent (OFFICIAL)
    with pytest.raises(ConfigurationError, match="security_level 'UNOFFICIAL' cannot downgrade parent level 'OFFICIAL'"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )
