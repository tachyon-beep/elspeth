"""Recursive deep-freeze utility for immutable dataclass fields.

Converts mutable containers to their immutable equivalents:
- ``dict`` → ``MappingProxyType``
- ``list`` → ``tuple``

Already-frozen containers (``MappingProxyType``, ``tuple``, ``frozenset``)
are recursed into to freeze any mutable contents. When all children are
already frozen, the original object is returned (identity-preserving
idempotency for repeated ``__post_init__`` calls).

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
    # Already-immutable containers — recurse into contents, but return
    # the original object when nothing changed (idempotency optimisation).
    if isinstance(value, MappingProxyType):
        frozen_map = {k: deep_freeze(v) for k, v in value.items()}
        if all(frozen_map[k] is value[k] for k in frozen_map):
            return value
        return MappingProxyType(frozen_map)
    if isinstance(value, tuple):
        frozen_tup = tuple(deep_freeze(item) for item in value)
        if all(a is b for a, b in zip(frozen_tup, value, strict=True)):
            return value
        return frozen_tup
    if isinstance(value, frozenset):
        # frozenset elements are unordered; recurse but can only detect
        # change by identity of the rebuilt set.
        frozen_fs = frozenset(deep_freeze(item) for item in value)
        if frozen_fs == value:
            return value
        return frozen_fs
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
