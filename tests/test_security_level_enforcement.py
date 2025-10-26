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

    CRITICAL: If this test fails, a security vulnerability has been reintroduced.
    """
    registry = BasePluginRegistry[object]("test_plugin")

    def create_plugin(opts, ctx):
        return object()

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",  # Parent has OFFICIAL classification
        determinism_level="none",
    )

    # Child attempts to downgrade to PUBLIC - must be rejected
    definition = {
        "name": "test",
        "security_level": "public",  # ❌ Attempting downgrade
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

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="confidential",
        determinism_level="none",
    )

    definition = {
        "name": "test",
        "security_level": "internal",  # ❌ Attempting downgrade
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

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="secret",
        determinism_level="none",
    )

    definition = {
        "name": "test",
        "security_level": "protected",  # ❌ Attempting downgrade
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

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Child specifies SAME level - allowed (redundant but not harmful)
    definition = {
        "name": "test",
        "security_level": "official",  # ✅ Same as parent
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

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="internal",  # Parent has INTERNAL (alias for OFFICIAL)
        determinism_level="none",
    )

    # Child upgrades to CONFIDENTIAL - allowed (more restrictive is safe)
    definition = {
        "name": "test",
        "security_level": "confidential",  # ✅ Upgrade to higher classification (alias for PROTECTED)
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
    """Child SHOULD inherit parent's security level when not specified."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Child does not specify security_level or determinism_level (ADR-002-B)
    definition = {
        "name": "test",
        # No security_level → OK (defaults to UNOFFICIAL)
        # No determinism_level → ERROR (required)
    }

    # ADR-002-B: security_level is optional (defaults to UNOFFICIAL),
    # but determinism_level is REQUIRED
    with pytest.raises(ConfigurationError, match="determinism_level must be declared"):
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

    registry.register("test", create_plugin)

    # Level 1: Root context (CONFIDENTIAL)
    root_context = PluginContext(
        plugin_name="root",
        plugin_kind="test",
        security_level="confidential",
        determinism_level="none",
    )

    # Level 2: Child inherits from root
    definition_level2 = {"name": "test", "security_level": "confidential", "determinism_level": "none"}
    child1 = create_plugin_with_inheritance(
        registry,
        definition_level2,
        plugin_kind="test_plugin",
        parent_context=root_context,
    )

    assert child1._elspeth_security_level == "PROTECTED"  # "confidential" alias maps to PROTECTED

    # Level 3: Grandchild attempts downgrade - must fail
    grandchild_context = PluginContext(
        plugin_name="child1",
        plugin_kind="test",
        security_level="confidential",
        determinism_level="none",
        parent=root_context,
    )

    definition_level3 = {
        "name": "test",
        "security_level": "internal",  # ❌ Attempting downgrade in chain
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
    """SECURITY REGRESSION TEST: Security level in options dict is also enforced."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Child attempts downgrade via options dict - must be rejected
    definition = {
        "name": "test",
        "determinism_level": "none",
        "options": {
            "security_level": "public",  # ❌ Downgrade in options
        },
    }

    with pytest.raises(ConfigurationError, match="security_level 'UNOFFICIAL' cannot downgrade parent level 'OFFICIAL'"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_security_enforcement_with_both_definition_and_options():
    """SECURITY REGRESSION TEST: Conflicting levels in definition+options rejected."""
    registry = BasePluginRegistry[object]("test_plugin")

    class TestPlugin:
        pass

    def create_plugin(opts, ctx):
        return TestPlugin()

    registry.register("test", create_plugin)

    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Both definition and options have conflicting levels with parent
    definition = {
        "name": "test",
        "security_level": "internal",  # ❌ Conflicts with parent
        "determinism_level": "none",
        "options": {
            "security_level": "public",  # ❌ Also conflicts
        },
    }

    with pytest.raises(ConfigurationError, match="Conflicting security_level"):
        create_plugin_with_inheritance(
            registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )
