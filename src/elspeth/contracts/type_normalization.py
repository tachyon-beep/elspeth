"""Type normalization for schema contracts.

Converts numpy/pandas types to Python primitives for consistent
contract storage and validation.

Per CLAUDE.md: Uses isinstance() checks (not string matching on __name__).
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

# NOTE: numpy and pandas are imported LAZILY inside normalize_type_for_contract()
# to avoid breaking the contracts leaf module boundary. Importing them at module
# level pulls in 400+ modules just for type normalization.
# FIX: P2-2026-01-30-6fp (regression from type_normalization.py addition)

# Types that can be serialized in checkpoint and restored in from_checkpoint()
# Must match type_map in SchemaContract.from_checkpoint()
ALLOWED_CONTRACT_TYPES: frozenset[type] = frozenset(
    {
        int,
        str,
        float,
        bool,
        type(None),
        datetime,
    }
)


def normalize_type_for_contract(value: Any) -> type:
    """Convert value's type to Python primitive for contract storage.

    Args:
        value: Any Python value

    Returns:
        Python primitive type or original type for unknowns

    Raises:
        ValueError: If value is NaN or Infinity (invalid for audit trail)

    Note:
        numpy and pandas are imported lazily inside this function to avoid
        pulling in heavy dependencies when the contracts package is imported.
    """
    # Lazy imports to maintain contracts as a leaf module
    import numpy as np
    import pandas as pd

    if value is None:
        return type(None)

    # pd.NaT = "Not a Time" (missing datetime), treat like None
    if value is pd.NaT:
        return type(None)

    # CRITICAL: Reject NaN/Infinity (Tier 1 audit integrity)
    # Must check before numpy type normalization to catch np.float64(nan) etc.
    if isinstance(value, (float, np.floating)) and (math.isnan(value) or math.isinf(value)):
        raise ValueError(f"Cannot infer type from non-finite float: {value}. NaN/Infinity are invalid in audit trail.")

    # Normalize numpy/pandas types to primitives
    if isinstance(value, np.integer):
        return int
    if isinstance(value, np.floating):
        return float
    if isinstance(value, np.bool_):
        return bool
    if isinstance(value, pd.Timestamp):
        return datetime
    if isinstance(value, np.datetime64):
        return datetime
    if isinstance(value, (np.str_, np.bytes_)):
        return str

    # Reject unsupported types immediately (fail-fast for checkpoint compatibility)
    # Per CLAUDE.md: Silent failures corrupt audit trail - crash early with clear error
    final_type = type(value)
    if final_type not in ALLOWED_CONTRACT_TYPES:
        raise TypeError(
            f"Unsupported type '{final_type.__name__}' for schema contract. "
            f"Allowed types: {', '.join(sorted(t.__name__ for t in ALLOWED_CONTRACT_TYPES))}. "
            f"Use 'any' type declaration for fields with complex/dynamic types."
        )
    return final_type
