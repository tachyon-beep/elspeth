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


def check_normalization_collisions(raw_headers: list[str], normalized_headers: list[str]) -> None:
    """Check for collisions after normalization.

    Args:
        raw_headers: Original header names
        normalized_headers: Normalized header names (same order)

    Raises:
        ValueError: If multiple raw headers normalize to same value,
                   with ALL colliding headers and their positions listed
    """
    seen: dict[str, list[tuple[int, str]]] = {}

    for i, (raw, norm) in enumerate(zip(raw_headers, normalized_headers, strict=True)):
        seen.setdefault(norm, []).append((i, raw))

    collisions = {norm: sources for norm, sources in seen.items() if len(sources) > 1}

    if collisions:
        details = []
        for norm, sources in sorted(collisions.items()):
            source_desc = ", ".join(f"column {i} ('{raw}')" for i, raw in sources)
            details.append(f"  '{norm}' <- {source_desc}")

        raise ValueError("Field name collision after normalization:\n" + "\n".join(details))


def check_mapping_collisions(
    pre_mapping: list[str],
    post_mapping: list[str],
    field_mapping: dict[str, str],
) -> None:
    """Check for collisions created by field_mapping.

    Args:
        pre_mapping: Headers before mapping applied
        post_mapping: Headers after mapping applied
        field_mapping: The mapping that was applied

    Raises:
        ValueError: If mapping causes multiple fields to have same final name
    """
    if len(post_mapping) != len(set(post_mapping)):
        # Build mapping from target to all sources (both mapped and passthrough)
        target_to_sources: dict[str, list[str]] = {}
        for source, target in zip(pre_mapping, post_mapping, strict=True):
            target_to_sources.setdefault(target, []).append(source)

        collisions = {t: s for t, s in target_to_sources.items() if len(s) > 1}

        if collisions:
            details = [f"  '{target}' <- {', '.join(repr(s) for s in sources)}" for target, sources in sorted(collisions.items())]
            raise ValueError("field_mapping creates collision:\n" + "\n".join(details))
