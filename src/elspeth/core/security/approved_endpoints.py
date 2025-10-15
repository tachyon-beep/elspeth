"""Approved endpoint validation for external service integrations.

This module implements endpoint allowlisting for external services to prevent
data exfiltration to unauthorized endpoints. All external API endpoints must
match approved patterns before use.

ATO Requirement: MF-4 External Service Approval & Endpoint Lockdown

Usage:
    from elspeth.core.security.approved_endpoints import validate_endpoint

    # Validate Azure OpenAI endpoint
    validate_endpoint(
        endpoint="https://my-resource.openai.azure.com",
        service_type="azure_openai",
        security_level="OFFICIAL"
    )

    # Validate HTTP API endpoint
    validate_endpoint(
        endpoint="https://api.openai.com/v1",
        service_type="http_api",
        security_level="public"
    )

Environment Variables:
    ELSPETH_APPROVED_ENDPOINTS: Comma-separated additional approved patterns
    ELSPETH_SECURE_MODE: Security mode (strict, standard, development)

Security Modes:
    STRICT: Endpoint validation strictly enforced, errors raised
    STANDARD: Endpoint validation enforced, errors raised
    DEVELOPMENT: Endpoint validation logged as warnings only
"""

from __future__ import annotations

import logging
import os
import re
from typing import Literal
from urllib.parse import urlparse

from elspeth.core.security.secure_mode import SecureMode, get_secure_mode

logger = logging.getLogger(__name__)

# Service type literal for type safety
ServiceType = Literal[
    "azure_openai",
    "http_api",
    "azure_blob",
]

# Default approved endpoint patterns by service type
# Patterns are regular expressions (re), not glob-style wildcards.
# Full regex matching is used for validation.
APPROVED_PATTERNS: dict[ServiceType, list[str]] = {
    "azure_openai": [
        # Azure OpenAI public cloud
        r"https://[^/]+\.openai\.azure\.com(/.*)?",
        # Azure OpenAI Government cloud
        r"https://[^/]+\.openai\.azure\.us(/.*)?",
        # Azure OpenAI China cloud
        r"https://[^/]+\.openai\.azure\.cn(/.*)?",
    ],
    "http_api": [
        # OpenAI public API
        r"https://api\.openai\.com(/.*)?",
        # Localhost for testing (any port)
        r"http://localhost(:[0-9]+)?(/.*)?",
        r"http://127\.0\.0\.1(:[0-9]+)?(/.*)?",
        r"http://\[::1\](:[0-9]+)?(/.*)?",  # IPv6 localhost
        # HTTPS localhost for testing
        r"https://localhost(:[0-9]+)?(/.*)?",
        r"https://127\.0\.0\.1(:[0-9]+)?(/.*)?",
        r"https://\[::1\](:[0-9]+)?(/.*)?",
    ],
    "azure_blob": [
        # Azure Blob Storage public cloud
        r"https://[^/]+\.blob\.core\.windows\.net(/.*)?",
        # Azure Blob Storage Government cloud
        r"https://[^/]+\.blob\.core\.usgovcloudapi\.net(/.*)?",
        # Azure Blob Storage China cloud
        r"https://[^/]+\.blob\.core\.chinacloudapi\.cn(/.*)?",
    ],
}

# Security level restrictions by service type
# Maps service type -> list of allowed security levels (canonical uppercase forms)
# If not specified, all security levels are allowed
SECURITY_LEVEL_RESTRICTIONS: dict[ServiceType, dict[str, list[str]]] = {
    "http_api": {
        # OpenAI public API should only be used for public/internal data
        # Note: Uses canonical uppercase forms (UNOFFICIAL, OFFICIAL)
        # Aliases: "public" -> "UNOFFICIAL", "internal" -> "OFFICIAL"
        r"https://api\.openai\.com(/.*)?": ["UNOFFICIAL", "OFFICIAL"],
        # Localhost is allowed for any security level (data never leaves host)
        # All other patterns: no restrictions
    }
}


def _get_environment_patterns() -> list[str]:
    """Get additional approved patterns from environment variable.

    Returns:
        List of regex patterns from ELSPETH_APPROVED_ENDPOINTS env var.
    """
    env_patterns = os.environ.get("ELSPETH_APPROVED_ENDPOINTS", "").strip()
    if not env_patterns:
        return []

    patterns = []
    for pattern_str in env_patterns.split(","):
        pattern_str = pattern_str.strip()
        if pattern_str:
            # Patterns are treated as raw regex (no glob-to-regex conversion)
            # Users should provide regex patterns in ELSPETH_APPROVED_ENDPOINTS
            patterns.append(pattern_str)

    if patterns:
        logger.info(f"Loaded {len(patterns)} additional approved endpoint patterns from " "ELSPETH_APPROVED_ENDPOINTS environment variable")

    return patterns


def _matches_pattern(endpoint: str, pattern: str) -> bool:
    """Check if endpoint matches a regex pattern.

    Args:
        endpoint: The endpoint URL to check
        pattern: Regex pattern to match against

    Returns:
        True if endpoint matches pattern
    """
    try:
        return bool(re.fullmatch(pattern, endpoint))
    except re.error as exc:
        logger.warning(f"Invalid endpoint pattern '{pattern}': {exc}")
        return False


def _is_localhost(endpoint: str) -> bool:
    """Check if endpoint is a localhost/loopback address.

    Args:
        endpoint: The endpoint URL to check

    Returns:
        True if endpoint is localhost or loopback address
    """
    try:
        parsed = urlparse(endpoint)
        hostname = parsed.hostname
        if not hostname:
            return False

        # Check common localhost patterns
        localhost_patterns = [
            "localhost",
            "127.0.0.1",
            "::1",
            "[::1]",
        ]

        return hostname.lower() in localhost_patterns
    except Exception:
        return False


def validate_endpoint(
    endpoint: str,
    service_type: ServiceType,
    security_level: str | None = None,
    mode: SecureMode | None = None,
) -> None:
    """Validate that an endpoint is approved for use.

    Args:
        endpoint: The endpoint URL to validate
        service_type: Type of service (azure_openai, http_api, azure_blob)
        security_level: Data classification level (optional, required for some services)
        mode: Security mode (defaults to current environment mode)

    Raises:
        ValueError: If endpoint is not approved (in STRICT or STANDARD mode)

    Notes:
        - In DEVELOPMENT mode, validation failures are logged as warnings
        - In STRICT/STANDARD mode, validation failures raise ValueError
        - Localhost endpoints are always allowed (for testing)
        - Additional patterns can be added via ELSPETH_APPROVED_ENDPOINTS env var
    """
    if mode is None:
        mode = get_secure_mode()

    # Normalize endpoint (strip trailing slashes for comparison)
    endpoint_normalized = endpoint.rstrip("/")

    # Always allow localhost for testing
    if _is_localhost(endpoint_normalized):
        logger.debug(f"Endpoint '{endpoint}' is localhost - allowed for testing")
        return

    # Get approved patterns for this service type
    approved_patterns = APPROVED_PATTERNS.get(service_type, [])

    # Add environment-specific patterns
    env_patterns = _get_environment_patterns()
    all_patterns = approved_patterns + env_patterns

    # Check if endpoint matches any approved pattern
    matched = False
    matched_pattern = None
    for pattern in all_patterns:
        if _matches_pattern(endpoint_normalized, pattern):
            matched = True
            matched_pattern = pattern
            break

    if not matched:
        error_msg = f"Endpoint '{endpoint}' is not approved for service type '{service_type}'. " f"Approved patterns: {approved_patterns}"

        if mode == SecureMode.DEVELOPMENT:
            logger.warning(f"{error_msg} (DEVELOPMENT mode - allowing anyway)")
            return
        else:
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Check security level restrictions (if applicable)
    if security_level and service_type in SECURITY_LEVEL_RESTRICTIONS:
        restrictions = SECURITY_LEVEL_RESTRICTIONS[service_type]

        # Normalize security level to canonical form (handles aliases like "internal" -> "OFFICIAL")
        # Import here to avoid circular dependency
        from elspeth.core.security import normalize_security_level

        security_level_normalized = normalize_security_level(security_level)

        # Check if this specific pattern has security level restrictions
        for pattern, allowed_levels in restrictions.items():
            if _matches_pattern(endpoint_normalized, pattern):
                if security_level_normalized not in allowed_levels:
                    error_msg = (
                        f"Endpoint '{endpoint}' (matched pattern '{pattern}') is not approved "
                        f"for security level '{security_level_normalized}'. "
                        f"Allowed security levels: {allowed_levels}"
                    )

                    if mode == SecureMode.DEVELOPMENT:
                        logger.warning(f"{error_msg} (DEVELOPMENT mode - allowing anyway)")
                        return
                    else:
                        logger.error(error_msg)
                        raise ValueError(error_msg)

    logger.debug(f"Endpoint '{endpoint}' validated successfully for service '{service_type}' " f"(matched pattern: {matched_pattern})")


def get_approved_patterns(service_type: ServiceType) -> list[str]:
    """Get list of approved endpoint patterns for a service type.

    Args:
        service_type: Type of service

    Returns:
        List of regex patterns approved for this service type
    """
    base_patterns = APPROVED_PATTERNS.get(service_type, [])
    env_patterns = _get_environment_patterns()
    return base_patterns + env_patterns


def validate_azure_openai_endpoint(endpoint: str, security_level: str | None = None, mode: SecureMode | None = None) -> None:
    """Validate an Azure OpenAI endpoint.

    Convenience wrapper for validate_endpoint with service_type="azure_openai".

    Args:
        endpoint: Azure OpenAI endpoint URL
        security_level: Data classification level
        mode: Security mode (defaults to current environment mode)

    Raises:
        ValueError: If endpoint is not approved
    """
    validate_endpoint(
        endpoint=endpoint,
        service_type="azure_openai",
        security_level=security_level,
        mode=mode,
    )


def validate_http_api_endpoint(endpoint: str, security_level: str | None = None, mode: SecureMode | None = None) -> None:
    """Validate an HTTP API endpoint.

    Convenience wrapper for validate_endpoint with service_type="http_api".

    Args:
        endpoint: HTTP API endpoint URL
        security_level: Data classification level
        mode: Security mode (defaults to current environment mode)

    Raises:
        ValueError: If endpoint is not approved
    """
    validate_endpoint(
        endpoint=endpoint,
        service_type="http_api",
        security_level=security_level,
        mode=mode,
    )


def validate_azure_blob_endpoint(endpoint: str, security_level: str | None = None, mode: SecureMode | None = None) -> None:
    """Validate an Azure Blob Storage endpoint.

    Convenience wrapper for validate_endpoint with service_type="azure_blob".

    Args:
        endpoint: Azure Blob Storage account URL
        security_level: Data classification level
        mode: Security mode (defaults to current environment mode)

    Raises:
        ValueError: If endpoint is not approved
    """
    validate_endpoint(
        endpoint=endpoint,
        service_type="azure_blob",
        security_level=security_level,
        mode=mode,
    )


__all__ = [
    "ServiceType",
    "validate_endpoint",
    "validate_azure_openai_endpoint",
    "validate_http_api_endpoint",
    "validate_azure_blob_endpoint",
    "get_approved_patterns",
]
