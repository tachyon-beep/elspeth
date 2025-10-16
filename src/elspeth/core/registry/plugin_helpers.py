"""Deprecated compatibility shim for :mod:`elspeth.core.registry.plugin_helpers`."""

from __future__ import annotations

import importlib
import warnings

_new_module = importlib.import_module("elspeth.core.registries.plugin_helpers")
__all__ = getattr(_new_module, "__all__", [name for name in dir(_new_module) if not name.startswith("_")])

globals().update({name: getattr(_new_module, name) for name in __all__})

warnings.warn(
    "elspeth.core.registry.plugin_helpers is deprecated; import from elspeth.core.registries.plugin_helpers instead",
    DeprecationWarning,
    stacklevel=2,
)
