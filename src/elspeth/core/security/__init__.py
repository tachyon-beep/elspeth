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


def _ensure_security_level(level: SecurityLevel | str | None) -> SecurityLevel:
    """Convert input into a SecurityLevel enum (None/blank -> UNOFFICIAL)."""
    if isinstance(level, SecurityLevel):
        return level
    return SecurityLevel.from_string(level)


def _ensure_determinism_level(level: DeterminismLevel | str | None) -> DeterminismLevel:
    """Convert input into a DeterminismLevel enum (None/blank -> NONE)."""
    if isinstance(level, DeterminismLevel):
        return level
    return DeterminismLevel.from_string(level)


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
