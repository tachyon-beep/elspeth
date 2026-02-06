"""Type-preserving JSON serialization for checkpoint aggregation state.

This module provides serialization that preserves type fidelity for types allowed
in SchemaContract (int, str, float, bool, NoneType, datetime, object).

The problem: Standard json.dumps() cannot serialize datetime objects.
The solution: Use type tags to encode datetime as {"__datetime__": iso_string}.

This is distinct from canonical_json() which:
1. Is designed for hashing (normalized output)
2. Converts datetime to bare ISO strings (no type tags)
3. Normalizes floats in ways that could change values

Checkpoint serialization needs round-trip fidelity, not canonical form.

Per CLAUDE.md:
- NaN/Infinity are rejected (audit integrity)
- datetime must round-trip correctly (type fidelity)
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any


class CheckpointEncoder(json.JSONEncoder):
    """JSON encoder that preserves datetime with type tags.

    Encodes datetime as {"__datetime__": "2024-01-01T00:00:00+00:00"}.
    This allows deserialization to restore the original datetime type.

    NaN and Infinity are rejected per CLAUDE.md audit integrity requirements.
    """

    def default(self, obj: Any) -> Any:
        """Encode non-standard types.

        Args:
            obj: Object to encode

        Returns:
            JSON-serializable representation

        Raises:
            TypeError: If object cannot be serialized
            ValueError: If float is NaN or Infinity
        """
        if isinstance(obj, datetime):
            # Ensure timezone-aware (audit requirement)
            if obj.tzinfo is None:
                obj = obj.replace(tzinfo=UTC)
            return {"__datetime__": obj.isoformat()}

        # Let default encoder handle or raise TypeError
        return super().default(obj)


def _reject_nan_infinity(obj: Any) -> Any:
    """Recursively check for NaN/Infinity in data structure.

    Per CLAUDE.md: NaN/Infinity are strictly rejected for audit integrity.

    Args:
        obj: Data structure to validate

    Returns:
        The same object if valid

    Raises:
        ValueError: If NaN or Infinity found
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError(
                f"Cannot serialize non-finite float: {obj}. "
                "Use None for missing values, not NaN/Infinity."
            )
    elif isinstance(obj, dict):
        for v in obj.values():
            _reject_nan_infinity(v)
    elif isinstance(obj, list):
        for v in obj:
            _reject_nan_infinity(v)
    return obj


def checkpoint_dumps(obj: Any) -> str:
    """Serialize object to JSON with type preservation.

    Preserves datetime objects using type tags for round-trip fidelity.
    Rejects NaN/Infinity per CLAUDE.md audit integrity requirements.

    Args:
        obj: Data structure to serialize (typically aggregation state)

    Returns:
        JSON string with type tags for datetime

    Raises:
        ValueError: If data contains NaN or Infinity
        TypeError: If data contains non-serializable types
    """
    # Validate no NaN/Infinity before serialization
    _reject_nan_infinity(obj)

    return json.dumps(obj, cls=CheckpointEncoder, allow_nan=False)


def _restore_types(obj: Any) -> Any:
    """Recursively restore type-tagged values.

    Converts {"__datetime__": iso_string} back to datetime objects.

    Args:
        obj: Deserialized JSON data

    Returns:
        Data with restored Python types
    """
    if isinstance(obj, dict):
        # Check for type tag
        if "__datetime__" in obj and len(obj) == 1:
            return datetime.fromisoformat(obj["__datetime__"])
        # Recurse into dict values
        return {k: _restore_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_restore_types(v) for v in obj]
    return obj


def checkpoint_loads(s: str) -> Any:
    """Deserialize JSON string with type restoration.

    Restores datetime objects from type tags.

    Args:
        s: JSON string (from checkpoint_dumps)

    Returns:
        Data structure with restored Python types

    Raises:
        json.JSONDecodeError: If string is not valid JSON
    """
    data = json.loads(s)
    return _restore_types(data)
