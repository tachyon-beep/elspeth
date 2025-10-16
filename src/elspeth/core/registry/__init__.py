"""Deprecated compatibility shim for :mod:`elspeth.core.registry`.

This package now re-exports symbols from :mod:`elspeth.core.registries` and
will be removed in a future major release.
"""

from __future__ import annotations

import warnings

from elspeth.core.registries import *  # noqa: F401,F403

warnings.warn(
    "elspeth.core.registry is deprecated; import from elspeth.core.registries instead",
    DeprecationWarning,
    stacklevel=2,
)
