"""Primitive-only canonical hashing for the contracts layer.

Provides canonical JSON serialization (RFC 8785/JCS) and stable hashing
for data that contains only JSON-safe primitives (str, int, float, bool,
None, dict, list).

This module exists to break the circular dependency between contracts/
and core/canonical.py. Contracts callers only hash primitive dicts, so
they don't need the pandas/numpy normalization in core/canonical.py.

For data containing pandas/numpy types or PipelineRow, use
elspeth.core.canonical instead — it adds a normalization phase before
delegating to rfc8785.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import rfc8785

# Version string stored with every run for hash verification.
# Single source of truth — core/canonical.py imports this constant.
CANONICAL_VERSION = "sha256-rfc8785-v1"


def _reject_non_finite(obj: Any) -> None:
    """Reject NaN and Infinity anywhere in a primitive data structure.

    Raises ValueError with a clear message instead of letting rfc8785 raise
    a cryptic FloatDomainError. Matches the rejection pattern in
    core/canonical.py's _normalize_for_canonical().
    """
    if isinstance(obj, float):
        if math.isnan(obj):
            raise ValueError(f"Cannot canonicalize NaN. Use None for missing values, not NaN. Got: {obj!r}")
        if math.isinf(obj):
            raise ValueError(f"Cannot canonicalize Infinity. Use None for missing values, not Infinity. Got: {obj!r}")
    elif isinstance(obj, dict):
        for v in obj.values():
            _reject_non_finite(v)
    elif isinstance(obj, list):
        for item in obj:
            _reject_non_finite(item)


def canonical_json(obj: Any) -> str:
    """Produce canonical JSON per RFC 8785/JCS for primitive data.

    For data containing pandas/numpy types or PipelineRow, use
    ``elspeth.core.canonical.canonical_json()`` instead.

    Args:
        obj: JSON-safe data structure (no pandas/numpy types)

    Returns:
        Canonical JSON string (deterministic key order, no whitespace)

    Raises:
        ValueError: If data contains NaN or Infinity
        TypeError: If data contains non-serializable types
    """
    _reject_non_finite(obj)
    result: bytes = rfc8785.dumps(obj)
    return result.decode("utf-8")


def stable_hash(obj: Any) -> str:
    """Compute SHA-256 hash of canonical JSON for primitive data.

    For data containing pandas/numpy types or PipelineRow, use
    ``elspeth.core.canonical.stable_hash()`` instead.

    Args:
        obj: JSON-safe data structure (no pandas/numpy types)

    Returns:
        SHA-256 hex digest of canonical JSON
    """
    canonical = canonical_json(obj)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def repr_hash(obj: Any) -> str:
    """Generate SHA-256 hash of repr() for non-canonical data.

    Used as fallback when canonical_json fails (NaN, Infinity, or other
    non-serializable types). Deterministic within the same Python version
    but NOT stable across versions due to repr() implementation differences.

    Appropriate for Tier-3 (external data) trust boundary where data is
    already malformed and being quarantined.

    Args:
        obj: Any Python object

    Returns:
        SHA-256 hex digest of repr(obj)
    """
    return hashlib.sha256(repr(obj).encode("utf-8")).hexdigest()
