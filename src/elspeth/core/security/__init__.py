"""Security utilities (signing, classification, secure mode, etc.)."""

from elspeth.core.base.types import DeterminismLevel, SecurityLevel

from .approved_endpoints import (
    ServiceType,
    get_approved_patterns,
    validate_azure_blob_endpoint,
    validate_azure_openai_endpoint,
    validate_azure_search_endpoint,
    validate_endpoint,
    validate_http_api_endpoint,
)
from .classified_data import ClassifiedDataFrame
from .secure_mode import (
    SecureMode,
    get_mode_description,
    get_secure_mode,
    is_development_mode,
    is_strict_mode,
    validate_datasource_config,
    validate_llm_config,
    validate_middleware_config,
    validate_sink_config,
)
from .signing import generate_signature, public_key_fingerprint, verify_signature

# No legacy string lists; enums are the source of truth


def _normalize_security_text(value: str) -> str:
    """Normalize free-form security text for comparison.

    Removes punctuation and whitespace, lowercases, and collapses variants so
    inputs like "OFFICIAL: SENSITIVE", "official_sensitive", and
    "official-sensitive" normalize identically.
    """
    # Keep only alphanumeric characters for a robust match across punctuation
    return "".join(ch for ch in value if ch.isalnum()).lower()


def _ensure_security_level(level: SecurityLevel | str | None) -> SecurityLevel:
    """Convert input into a SecurityLevel enum (None/blank -> UNOFFICIAL).

    This function is the single normalization point for security levels.
    It accepts SecurityLevel values directly and supports common string inputs,
    including canonical PSPF labels (e.g., "OFFICIAL: SENSITIVE") and legacy
    aliases (e.g., "public" -> UNOFFICIAL, "internal" -> OFFICIAL).
    """
    if isinstance(level, SecurityLevel):
        return level
    if level is None:
        return SecurityLevel.UNOFFICIAL

    text = str(level).strip()
    if not text:
        return SecurityLevel.UNOFFICIAL

    # First try exact, case-insensitive match to enum values
    for enum_value in SecurityLevel:
        if text.casefold() == enum_value.value.casefold():
            return enum_value

    # Fallback to normalized comparison and legacy aliases
    normalized = _normalize_security_text(text)

    # Canonical normalized keys for enum values
    canonical_map = {_normalize_security_text(e.value): e for e in SecurityLevel}

    # Legacy/alias mappings (normalized)
    alias_map = {
        "public": SecurityLevel.UNOFFICIAL,
        "unofficial": SecurityLevel.UNOFFICIAL,
        "internal": SecurityLevel.OFFICIAL,
        "official": SecurityLevel.OFFICIAL,
        "sensitive": SecurityLevel.OFFICIAL_SENSITIVE,
        "officialsensitive": SecurityLevel.OFFICIAL_SENSITIVE,
        "confidential": SecurityLevel.PROTECTED,
        "protected": SecurityLevel.PROTECTED,
        "secret": SecurityLevel.SECRET,
    }

    if normalized in canonical_map:
        return canonical_map[normalized]
    if normalized in alias_map:
        return alias_map[normalized]

    valid_levels = ", ".join(level.value for level in SecurityLevel)
    raise ValueError(f"Unknown security level '{level}'. Must be one of: {valid_levels}")


def _ensure_determinism_level(level: DeterminismLevel | str | None) -> DeterminismLevel:
    """Convert input into a DeterminismLevel enum (None/blank -> NONE)."""
    if isinstance(level, DeterminismLevel):
        return level
    if level is None:
        return DeterminismLevel.NONE
    text = str(level).strip()
    if not text:
        return DeterminismLevel.NONE
    try:
        # DeterminismLevel values are lower-case; accept case-insensitively
        return DeterminismLevel(text.lower())
    except ValueError as exc:
        valid_levels = ", ".join(lv.value for lv in DeterminismLevel)
        raise ValueError(f"Unknown determinism level '{level}'. Must be one of: {valid_levels}") from exc


# Public helpers for normalization from free-form input
def ensure_security_level(level: SecurityLevel | str | None) -> SecurityLevel:  # noqa: D401
    """Return SecurityLevel from free-form input (single normalization point)."""
    return _ensure_security_level(level)


def ensure_determinism_level(level: DeterminismLevel | str | None) -> DeterminismLevel:  # noqa: D401
    """Return DeterminismLevel from free-form input (single normalization point)."""
    return _ensure_determinism_level(level)


def is_security_level_allowed(data_level: SecurityLevel | str | None, clearance_level: SecurityLevel | str | None) -> bool:
    """Return True when the clearance equals or exceeds the data classification."""

    data = _ensure_security_level(data_level)
    clearance = _ensure_security_level(clearance_level)
    return bool(clearance >= data)


def resolve_security_level(*levels: SecurityLevel | str | None) -> SecurityLevel:
    """Resolve multiple levels to the highest classification (most restrictive)."""

    filtered: list[SecurityLevel] = []
    for level in levels:
        if level is None:
            continue
        if isinstance(level, SecurityLevel):
            filtered.append(level)
            continue
        text = str(level).strip()
        if not text:
            continue
        filtered.append(_ensure_security_level(text))
    if not filtered:
        return SecurityLevel.UNOFFICIAL
    return max(filtered)


def coalesce_security_level(*levels: SecurityLevel | str | None) -> SecurityLevel:
    """Return a single level ensuring all inputs agree (after normalization)."""

    normalized: list[SecurityLevel] = []
    for level in levels:
        if level is None:
            continue
        if isinstance(level, SecurityLevel):
            normalized.append(level)
            continue
        text = str(level).strip()
        if not text:
            continue
        normalized.append(_ensure_security_level(text))

    if not normalized:
        raise ValueError("security_level is required")

    if len(set(normalized)) > 1:
        raise ValueError("Conflicting security_level values")

    return normalized[0]


# ============================================================================
# Determinism Level Functions
# ============================================================================


def resolve_determinism_level(*levels: DeterminismLevel | str | None) -> DeterminismLevel:
    """Resolve to the LEAST deterministic (none < low < high < guaranteed)."""

    filtered: list[DeterminismLevel] = []
    for level in levels:
        if level is None:
            continue
        if isinstance(level, DeterminismLevel):
            filtered.append(level)
            continue
        text = str(level).strip()
        if not text:
            continue
        filtered.append(_ensure_determinism_level(text))
    if not filtered:
        return DeterminismLevel.NONE
    return min(filtered)


def coalesce_determinism_level(*levels: DeterminismLevel | str | None) -> DeterminismLevel:
    """Return a single determinism level ensuring all inputs agree."""

    normalized: list[DeterminismLevel] = []
    for level in levels:
        if level is None:
            continue
        if isinstance(level, DeterminismLevel):
            normalized.append(level)
            continue
        text = str(level).strip()
        if not text:
            continue
        normalized.append(_ensure_determinism_level(text))

    if not normalized:
        raise ValueError("determinism_level is required")

    if len(set(normalized)) > 1:
        raise ValueError("Conflicting determinism_level values")

    return normalized[0]


__all__ = [
    "generate_signature",
    "verify_signature",
    "public_key_fingerprint",
    "SecurityLevel",
    "DeterminismLevel",
    "ClassifiedDataFrame",
    "ensure_security_level",
    "ensure_determinism_level",
    "is_security_level_allowed",
    "resolve_security_level",
    "coalesce_security_level",
    "resolve_determinism_level",
    "coalesce_determinism_level",
    # Secure mode validation
    "SecureMode",
    "get_secure_mode",
    "is_strict_mode",
    "is_development_mode",
    "validate_datasource_config",
    "validate_llm_config",
    "validate_sink_config",
    "validate_middleware_config",
    "get_mode_description",
    # Endpoint validation
    "ServiceType",
    "validate_endpoint",
    "validate_azure_openai_endpoint",
    "validate_http_api_endpoint",
    "validate_azure_blob_endpoint",
    "validate_azure_search_endpoint",
    "get_approved_patterns",
]
