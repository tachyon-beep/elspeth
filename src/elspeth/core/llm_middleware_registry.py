"""Deprecated compatibility shim for :mod:`elspeth.core.llm_middleware_registry`."""

from __future__ import annotations

import importlib
import warnings

_new_module = importlib.import_module("elspeth.core.registries.middleware")
__all__ = getattr(_new_module, "__all__", [name for name in dir(_new_module) if not name.startswith("_")])

globals().update({name: getattr(_new_module, name) for name in __all__})

warnings.warn(
    "elspeth.core.llm_middleware_registry is deprecated; import from elspeth.core.registries.middleware instead",
    DeprecationWarning,
    stacklevel=2,
)
