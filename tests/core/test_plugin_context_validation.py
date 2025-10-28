from __future__ import annotations

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import DeterminismLevel, SecurityLevel, SecurityLevel


def test_plugin_context_non_empty_fields():
    # plugin_name cannot be empty
    with pytest.raises(ValueError):
        PluginContext(plugin_name="", plugin_kind="x", security_level="OFFICIAL")

    # plugin_kind cannot be empty
    with pytest.raises(ValueError):
        PluginContext(plugin_name="name", plugin_kind="  ", security_level="OFFICIAL")

    # security_level accepts aliases/blank via enum parser (defaults to UNOFFICIAL)
    ctx = PluginContext(plugin_name="name", plugin_kind="kind", security_level="   ")
    assert ctx.security_level == SecurityLevel.UNOFFICIAL


def test_plugin_context_determinism_level_validation_and_default():
    # Default determinism_level is "none" when omitted
    ctx = PluginContext(plugin_name="p", plugin_kind="k", security_level="OFFICIAL")
    assert ctx.determinism_level == DeterminismLevel.NONE

    # Valid values normalize to lowercase
    ctx2 = PluginContext(plugin_name="p2", plugin_kind="k2", security_level="OFFICIAL", determinism_level="HIGH")
    assert ctx2.determinism_level == DeterminismLevel.HIGH

    # Invalid determinism value raises
    with pytest.raises(ValueError):
        PluginContext(plugin_name="p3", plugin_kind="k3", security_level="OFFICIAL", determinism_level="sometimes")


def test_plugin_context_derive_inherits_and_overrides():
    parent = PluginContext(
        plugin_name="suite",
        plugin_kind="suite",
        security_level="PROTECTED",
        determinism_level="low",
    )

    # Inherit when not provided
    child = parent.derive(plugin_name="experiment", plugin_kind="experiment")
    assert child.security_level == SecurityLevel.PROTECTED
    assert child.determinism_level == DeterminismLevel.LOW
    assert child.parent == parent

    # Override when provided
    grandchild = child.derive(plugin_name="row_plugin", plugin_kind="row_plugin", security_level="SECRET", determinism_level="guaranteed")
    assert grandchild.security_level == SecurityLevel.SECRET
    assert grandchild.determinism_level == DeterminismLevel.GUARANTEED
    assert grandchild.parent == child
