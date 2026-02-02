"""Type normalization for schema contracts.

Converts numpy/pandas types to Python primitives for consistent
contract storage and validation.

Per CLAUDE.md: Uses isinstance() checks (not string matching on __name__).
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


def normalize_type_for_contract(value: Any) -> type:
    """Convert value's type to Python primitive for contract storage.

    Args:
        value: Any Python value

    Returns:
        Python primitive type or original type for unknowns

    Raises:
        ValueError: If value is NaN or Infinity (invalid for audit trail)
    """
    if value is None:
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

    return type(value)
