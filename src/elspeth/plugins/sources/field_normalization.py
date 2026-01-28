"""Field name normalization for external data sources.

This module normalizes messy external headers (e.g., "CaSE Study1 !!!! xx!")
to valid Python identifiers (e.g., "case_study1_xx") at the source boundary.

Per ELSPETH's Three-Tier Trust Model, this is Tier 3 (external data) handling:
- Sources ARE allowed to normalize/coerce external data
- Transforms expect normalized names (no coercion downstream)

Algorithm Stability:
    The normalization algorithm is versioned and frozen per major version.
    NORMALIZATION_ALGORITHM_VERSION is stored in the audit trail to enable
    debugging cross-run field name drift when algorithm evolves.
"""

from __future__ import annotations

import keyword
import re
import unicodedata

# Algorithm version for audit trail - frozen per major version
# Increment when algorithm changes affect output
NORMALIZATION_ALGORITHM_VERSION = "1.0.0"


def get_normalization_version() -> str:
    """Return current algorithm version for audit trail storage."""
    return NORMALIZATION_ALGORITHM_VERSION


# Pre-compiled regex patterns (module level for efficiency)
_NON_IDENTIFIER_CHARS = re.compile(r"[^\w]+")
_CONSECUTIVE_UNDERSCORES = re.compile(r"_+")


def normalize_field_name(raw: str) -> str:
    """Normalize messy header to valid Python identifier.

    Rules applied in order:
    1. Unicode NFC normalization (canonical composition)
    2. Strip leading/trailing whitespace
    3. Lowercase
    4. Replace non-identifier chars with underscore
    5. Collapse consecutive underscores
    6. Strip leading/trailing underscores
    7. Prefix with underscore if starts with digit
    8. Append underscore if result is Python keyword
    9. Raise error if result is empty

    Args:
        raw: Original messy header name

    Returns:
        Valid Python identifier

    Raises:
        ValueError: If header normalizes to empty string
    """
    # Step 1: Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", raw)

    # Step 2: Strip whitespace
    normalized = normalized.strip()

    # Step 3: Lowercase
    normalized = normalized.lower()

    # Step 4: Replace non-identifier chars with underscore
    normalized = _NON_IDENTIFIER_CHARS.sub("_", normalized)

    # Step 5: Collapse consecutive underscores
    normalized = _CONSECUTIVE_UNDERSCORES.sub("_", normalized)

    # Step 6: Strip leading/trailing underscores
    normalized = normalized.strip("_")

    # Step 7: Prefix if starts with digit
    if normalized and normalized[0].isdigit():
        normalized = f"_{normalized}"

    # Step 8: Handle Python keywords
    if keyword.iskeyword(normalized):
        normalized = f"{normalized}_"

    # Step 9: Validate non-empty result
    if not normalized:
        raise ValueError(f"Header '{raw}' normalizes to empty string")

    # Defense-in-depth: verify result is valid identifier
    if not normalized.isidentifier():
        raise ValueError(
            f"Header '{raw}' normalized to '{normalized}' which is not a valid identifier. This is a bug in the normalization algorithm."
        )

    return normalized
