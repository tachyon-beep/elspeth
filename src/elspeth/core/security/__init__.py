"""Security utilities (signing, classification, secure mode, etc.)."""

from elspeth.core.types import DeterminismLevel, SecurityLevel

from .approved_endpoints import (
    ServiceType,
    get_approved_patterns,
    validate_azure_blob_endpoint,
    validate_azure_openai_endpoint,
    validate_endpoint,
    validate_http_api_endpoint,
)
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
from .signing import generate_signature, verify_signature

# Export enum types for backward compatibility
SECURITY_LEVELS = [level.value for level in list(SecurityLevel)]
DETERMINISM_LEVELS = [level.value for level in list(DeterminismLevel)]


def normalize_security_level(level: str | SecurityLevel | None) -> str:
    """Coerce user-supplied levels to canonical PSPF format (uppercase).

    Args:
        level: String, SecurityLevel enum, or None

    Returns:
        Canonical PSPF string (e.g., "OFFICIAL")

    Raises:
        ValueError: If the level is invalid
    """
    if isinstance(level, SecurityLevel):
        # Enum .value is typed as Any in Python stdlib, but we know it's str
        return level.value  # type: ignore[no-any-return]
    # Enum .value is typed as Any in Python stdlib, but we know it's str
    return SecurityLevel.from_string(level).value  # type: ignore[no-any-return]


def is_security_level_allowed(data_level: str | None, clearance_level: str | None) -> bool:
    """Return True when the clearance equals or exceeds the data classification."""

    normalized_data = normalize_security_level(data_level)
    normalized_clearance = normalize_security_level(clearance_level)
    data_idx = SECURITY_LEVELS.index(normalized_data)
    clearance_idx = SECURITY_LEVELS.index(normalized_clearance)
    return clearance_idx >= data_idx


def resolve_security_level(*levels: str | None) -> str:
    """Resolve multiple levels to the highest classification."""

    normalized = [normalize_security_level(level) for level in levels if level is not None]
    if not normalized:
        # List indexing returns Any because SECURITY_LEVELS is dynamically built from enum values
        return SECURITY_LEVELS[0]  # type: ignore[no-any-return]
    return max(normalized, key=SECURITY_LEVELS.index)


def coalesce_security_level(*levels: str | None) -> str:
    """Return a single normalized level ensuring all inputs agree."""

    normalized: list[str] = []
    for level in levels:
        if level is None:
            continue
        text = str(level).strip()
        if not text:
            continue
        normalized.append(normalize_security_level(text))

    if not normalized:
        raise ValueError("security_level is required")

    if len(set(normalized)) > 1:
        raise ValueError("Conflicting security_level values")

    return normalized[0]


# ============================================================================
# Determinism Level Functions
# ============================================================================


def normalize_determinism_level(level: str | DeterminismLevel | None) -> str:
    """Coerce user-supplied determinism levels to canonical lowercase format.

    Args:
        level: String, DeterminismLevel enum, or None

    Returns:
        Canonical lowercase string (e.g., "high")

    Raises:
        ValueError: If the level is invalid
    """
    if isinstance(level, DeterminismLevel):
        # Enum .value is typed as Any in Python stdlib, but we know it's str
        return level.value  # type: ignore[no-any-return]
    # Enum .value is typed as Any in Python stdlib, but we know it's str
    return DeterminismLevel.from_string(level).value  # type: ignore[no-any-return]


def resolve_determinism_level(*levels: str | None) -> str:
    """Resolve multiple levels to the LEAST deterministic (opposite of security).

    Rule: LEAST deterministic wins (none < low < high < guaranteed)
    Examples:
        resolve_determinism_level("guaranteed", "high") → "high"
        resolve_determinism_level("high", "none") → "none"
    """

    normalized = [normalize_determinism_level(level) for level in levels if level is not None]
    if not normalized:
        # List indexing returns Any because DETERMINISM_LEVELS is dynamically built from enum values
        # Default to "none"
        return DETERMINISM_LEVELS[0]  # type: ignore[no-any-return]
    return min(normalized, key=DETERMINISM_LEVELS.index)


def coalesce_determinism_level(*levels: str | None) -> str:
    """Return a single normalized determinism level ensuring all inputs agree."""

    normalized: list[str] = []
    for level in levels:
        if level is None:
            continue
        text = str(level).strip()
        if not text:
            continue
        normalized.append(normalize_determinism_level(text))

    if not normalized:
        raise ValueError("determinism_level is required")

    if len(set(normalized)) > 1:
        raise ValueError("Conflicting determinism_level values")

    return normalized[0]


__all__ = [
    "generate_signature",
    "verify_signature",
    "SecurityLevel",
    "DeterminismLevel",
    "SECURITY_LEVELS",
    "DETERMINISM_LEVELS",
    "normalize_security_level",
    "is_security_level_allowed",
    "resolve_security_level",
    "coalesce_security_level",
    "normalize_determinism_level",
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
    "get_approved_patterns",
]
