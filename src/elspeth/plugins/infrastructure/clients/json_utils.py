"""Shared strict JSON parsing with NaN/Infinity rejection.

Extracted from AuditedHTTPClient to be reusable by any client that handles
external JSON responses at the Tier 3 boundary. Both AuditedHTTPClient and
DataverseClient callers import from this module.

Python's stdlib json module accepts non-finite float values (NaN, Infinity)
by default, but these cannot be canonicalized via RFC 8785 for audit hashing.
Detecting them at the HTTP boundary produces clean, Tier-3-attributed errors
rather than cryptic canonicalization crashes downstream.
"""

from __future__ import annotations

import json
import math
from json import JSONDecodeError
from typing import Any


def contains_non_finite(obj: Any) -> bool:
    """Recursively check if object contains NaN or Infinity float values.

    This is a Tier 3 boundary check: external JSON may contain non-finite values
    (Python's json module accepts them), but canonicalization rejects them. We
    detect these at the HTTP boundary to record as parse failure rather than
    crashing during audit recording.

    Args:
        obj: Any JSON-parsed value (dict, list, or primitive)

    Returns:
        True if any float value is NaN or Infinity
    """
    if isinstance(obj, float):
        return math.isnan(obj) or math.isinf(obj)
    if isinstance(obj, dict):
        return any(contains_non_finite(v) for v in obj.values())
    if isinstance(obj, list):
        return any(contains_non_finite(v) for v in obj)
    return False


def parse_json_strict(text: str) -> tuple[Any, str | None]:
    """Parse JSON with strict rejection of NaN/Infinity.

    Python's stdlib json module accepts non-finite values by default, but
    these cannot be canonicalized. This function parses and validates in
    one step at the Tier 3 boundary.

    Args:
        text: JSON string to parse

    Returns:
        Tuple of (parsed_value, error_message)
        - On success: (parsed_dict_or_list, None)
        - On failure: (None, error_message)
    """
    try:
        parsed = json.loads(text)
    except JSONDecodeError as e:
        return None, str(e)

    # Check for non-finite values that canonicalization would reject
    if contains_non_finite(parsed):
        return None, "JSON contains non-finite values (NaN or Infinity)"

    return parsed, None
