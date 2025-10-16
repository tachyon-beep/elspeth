"""Deprecated compatibility shim for :mod:`elspeth.core.registry.context_utils`."""

from __future__ import annotations

import importlib
import warnings

_new_module = importlib.import_module("elspeth.core.registries.context_utils")
__all__ = getattr(_new_module, "__all__", [name for name in dir(_new_module) if not name.startswith("_")])

globals().update({name: getattr(_new_module, name) for name in __all__})

warnings.warn(
    "elspeth.core.registry.context_utils is deprecated; import from elspeth.core.registries.context_utils instead",
    DeprecationWarning,
    stacklevel=2,
)
