"""Recursive deep-freeze utility for immutable dataclass fields.

Converts mutable containers to their immutable equivalents:
- ``dict`` → ``MappingProxyType``
- ``list`` → ``tuple``

Already-frozen containers (``MappingProxyType``, ``tuple``, ``frozenset``)
are returned as-is to avoid redundant wrapping on repeated calls (e.g.,
when ``__post_init__`` is invoked on an already-constructed instance).

This module is L0 (contracts layer) — no imports from core, engine, or plugins.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any


def deep_freeze(value: Any) -> Any:
    """Recursively freeze mutable containers.

    Converts ``dict`` → ``MappingProxyType`` and ``list`` → ``tuple``,
    recursing into values. Non-container types (str, int, float, bool,
    None, enum members, dataclass instances) are returned unchanged.

    This is the standard freeze function for ``__post_init__`` guards
    on frozen dataclasses throughout the contracts layer.

    Examples:
        >>> deep_freeze({"a": [1, {"b": 2}]})
        MappingProxyType({'a': (1, MappingProxyType({'b': 2}))})

        >>> deep_freeze([{"x": 1}, {"y": 2}])
        (MappingProxyType({'x': 1}), MappingProxyType({'y': 2}))

        >>> from types import MappingProxyType
        >>> already = MappingProxyType({"k": "v"})
        >>> deep_freeze(already) is already  # no-op on frozen input
        True
    """
    if isinstance(value, dict):
        return MappingProxyType({k: deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    # Already immutable containers — return as-is
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, (tuple, frozenset)):
        return value
    # Scalars and opaque objects (str, int, float, bool, None, enums, dataclasses)
    return value


def deep_thaw(value: Any) -> Any:
    """Recursively thaw frozen containers back to plain mutable types.

    Converts ``MappingProxyType`` → ``dict`` and ``tuple`` → ``list``,
    recursing into values. The inverse of ``deep_freeze``.

    Used by ``to_dict()`` methods to produce JSON-serializable output
    from deeply frozen fields.

    Examples:
        >>> deep_thaw(MappingProxyType({"a": (1, MappingProxyType({"b": 2}))}))
        {'a': [1, {'b': 2}]}
    """
    if isinstance(value, MappingProxyType):
        return {k: deep_thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [deep_thaw(item) for item in value]
    if isinstance(value, dict):
        return {k: deep_thaw(v) for k, v in value.items()}
    if isinstance(value, list):
        return [deep_thaw(item) for item in value]
    return value
