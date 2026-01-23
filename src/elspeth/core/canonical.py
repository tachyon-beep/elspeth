# src/elspeth/core/canonical.py
"""
Canonical JSON serialization for deterministic hashing.

Two-phase approach:
1. Normalize: Convert pandas/numpy types to JSON-safe primitives (our code)
2. Serialize: Produce deterministic JSON per RFC 8785/JCS (rfc8785 package)

IMPORTANT: NaN and Infinity are strictly REJECTED, not silently converted.
This is defense-in-depth for audit integrity.

NOTE: For non-canonical data that cannot be serialized (malformed external
data at Tier-3 trust boundary), use repr_hash() as a fallback. This is NOT
deterministic across Python versions but is appropriate for quarantined data
where the content is already flagged as problematic.
"""

import base64
import hashlib
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import rfc8785

# Version string stored with every run for hash verification
CANONICAL_VERSION = "sha256-rfc8785-v1"


def _normalize_value(obj: Any) -> Any:
    """Convert a single value to JSON-safe primitive.

    Handles pandas and numpy types that appear in real pipeline data.

    NaN Policy: STRICT REJECTION
    - NaN and Infinity are invalid input states, not "missing"
    - Use None/pd.NA/NaT for intentional missing values
    - This prevents silent data corruption in audit records

    Args:
        obj: Any Python value

    Returns:
        JSON-serializable primitive

    Raises:
        ValueError: If value contains NaN or Infinity
    """
    # Check for NaN/Infinity FIRST (before type coercion)
    if isinstance(obj, float | np.floating):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError(f"Cannot canonicalize non-finite float: {obj}. Use None for missing values, not NaN.")
        if isinstance(obj, np.floating):
            return float(obj)
        return obj

    # Primitives pass through unchanged
    if obj is None or isinstance(obj, str | int | bool):
        return obj

    # NumPy scalar types
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [_normalize_value(x) for x in obj.tolist()]

    # Pandas types
    if isinstance(obj, pd.Timestamp):
        # Naive timestamps assumed UTC (explicit policy)
        if obj.tz is None:
            return obj.tz_localize("UTC").isoformat()
        return obj.tz_convert("UTC").isoformat()

    # Intentional missing values (NOT NaN - that's rejected above)
    if obj is pd.NA or (isinstance(obj, type(pd.NaT)) and obj is pd.NaT):
        return None

    # Standard library types
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=UTC)
        return obj.astimezone(UTC).isoformat()

    if isinstance(obj, bytes):
        return {"__bytes__": base64.b64encode(obj).decode("ascii")}

    if isinstance(obj, Decimal):
        return str(obj)

    return obj


def _normalize_for_canonical(data: Any) -> Any:
    """Recursively normalize a data structure for canonical JSON.

    Converts pandas/numpy types to JSON-safe primitives.

    Args:
        data: Any data structure (dict, list, primitive)

    Returns:
        Normalized data structure with only JSON-safe types

    Raises:
        ValueError: If data contains NaN, Infinity, or other non-serializable values
    """
    if isinstance(data, dict):
        return {k: _normalize_for_canonical(v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [_normalize_for_canonical(v) for v in data]
    return _normalize_value(data)


def canonical_json(obj: Any) -> str:
    """Produce canonical JSON for hashing.

    Two-phase approach:
    1. Normalize pandas/numpy types to JSON-safe primitives (our code)
    2. Serialize per RFC 8785/JCS standard (rfc8785 package)

    Args:
        obj: Data structure to serialize

    Returns:
        Canonical JSON string (no whitespace, sorted keys)

    Raises:
        ValueError: If data contains NaN, Infinity, or other non-finite values
        TypeError: If data contains types that cannot be serialized
    """
    normalized = _normalize_for_canonical(obj)
    result: bytes = rfc8785.dumps(normalized)
    return result.decode("utf-8")


def stable_hash(obj: Any, version: str = CANONICAL_VERSION) -> str:
    """Compute stable hash of object.

    Args:
        obj: Data structure to hash
        version: Hash algorithm version (stored with runs for verification)

    Returns:
        SHA-256 hex digest of canonical JSON
    """
    canonical = canonical_json(obj)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def repr_hash(obj: Any) -> str:
    """Generate SHA-256 hash of repr() for non-canonical data.

    Used as fallback when canonical_json fails (NaN, Infinity, or other
    non-serializable types). This provides deterministic hashing within
    the same Python version, but is NOT guaranteed to be stable across
    different Python versions due to repr() implementation differences.

    This is appropriate for Tier-3 (external data) trust boundary where
    data is already malformed and being quarantined.

    Args:
        obj: Any Python object

    Returns:
        SHA-256 hex digest of repr(obj)

    Example:
        >>> repr_hash(42)
        '73475cb40a568e8da8a045ced110137e159f890ac4da883b6b17dc651b3a8049'
        >>> repr_hash({"value": float("nan")})  # Non-canonical data
        '49ce040dd7d56208...'
    """
    return hashlib.sha256(repr(obj).encode("utf-8")).hexdigest()
