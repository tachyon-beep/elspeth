"""L0 helpers for source/sink boundary role detection.

These helpers let L2 engine code distinguish source and sink plugin instances
without importing the L3 plugin base classes. They intentionally avoid
``isinstance()`` and instead walk the plugin class MRO plus the instance
namespace so inherited class-level declarations remain visible.

Plugin discovery and registration remain nominal via ``BaseSource`` /
``BaseSink`` in ``plugins.infrastructure.base``. This module exists only for
runtime boundary contracts that need a lower-layer role check.
"""

from __future__ import annotations

from typing import cast


def _declared_frozenset_from_instance_or_mro(
    plugin: object,
    *,
    attr_name: str,
) -> frozenset[str] | None:
    instance_namespace = vars(plugin)
    if attr_name in instance_namespace:
        value = instance_namespace[attr_name]
        if type(value) is not frozenset:
            raise TypeError(f"{type(plugin).__name__}.{attr_name} must be frozenset, got {type(value).__name__!r}.")
        return cast(frozenset[str], value)

    for owner in type(plugin).__mro__:
        namespace = vars(owner)
        if attr_name not in namespace:
            continue
        value = namespace[attr_name]
        if type(value) is not frozenset:
            raise TypeError(f"{owner.__name__}.{attr_name} must be frozenset, got {type(value).__name__!r}.")
        return cast(frozenset[str], value)
    return None


def _class_mro_defines_method(plugin: object, method_name: str) -> bool:
    return any(method_name in vars(owner) for owner in type(plugin).__mro__)


def source_declared_guaranteed_fields(plugin: object) -> frozenset[str] | None:
    """Return source guarantees for real source-role plugins, else ``None``."""

    if not _class_mro_defines_method(plugin, "load"):
        return None
    return _declared_frozenset_from_instance_or_mro(
        plugin,
        attr_name="declared_guaranteed_fields",
    )


def sink_declared_required_fields(plugin: object) -> frozenset[str] | None:
    """Return sink requirements for real sink-role plugins, else ``None``."""

    if not _class_mro_defines_method(plugin, "write"):
        return None
    if not _class_mro_defines_method(plugin, "flush"):
        return None
    return _declared_frozenset_from_instance_or_mro(
        plugin,
        attr_name="declared_required_fields",
    )
