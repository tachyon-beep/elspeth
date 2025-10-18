"""Secure mode detection and validation.

Provides environment-based security enforcement for Elspeth configuration.

Three modes:
- STRICT: Production mode with maximum security requirements
- STANDARD: Default balanced mode with strong security (default)
- DEVELOPMENT: Permissive mode for local development and testing

Set via ELSPETH_SECURE_MODE environment variable.
"""

import logging
import os
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Default set of local filesystem sinks that must enforce path containment and
# (where applicable) output sanitization. Can be extended via the
# ELSPETH_PATH_CONTAINED_SINKS environment variable (comma-separated list).
#
# Example:
#   ELSPETH_PATH_CONTAINED_SINKS="csv,excel_workbook,local_bundle,zip_bundle,file_copy,parquet"
PATH_CONTAINED_SINK_TYPES_DEFAULT: frozenset[str] = frozenset({"csv", "excel_workbook", "local_bundle", "zip_bundle", "file_copy"})


def _parse_csv_list(value: str) -> frozenset[str]:
    return frozenset(chunk.strip().lower() for chunk in value.split(",") if chunk.strip())


def get_path_contained_sink_types(env: dict[str, str] | None = None) -> frozenset[str]:
    """Return the set of sink ``type`` identifiers requiring path containment.

    Allows extension via the ``ELSPETH_PATH_CONTAINED_SINKS`` environment
    variable, which is merged with the default set.
    """
    environ = env if env is not None else os.environ
    override = environ.get("ELSPETH_PATH_CONTAINED_SINKS")
    if not override:
        return PATH_CONTAINED_SINK_TYPES_DEFAULT
    try:
        custom = _parse_csv_list(override)
        return frozenset(PATH_CONTAINED_SINK_TYPES_DEFAULT.union(custom))
    except (ValueError, AttributeError, TypeError):
        logger.warning("Failed to parse ELSPETH_PATH_CONTAINED_SINKS; using defaults")
        return PATH_CONTAINED_SINK_TYPES_DEFAULT


class SecureMode(Enum):
    """Security enforcement modes."""

    STRICT = "strict"
    STANDARD = "standard"
    DEVELOPMENT = "development"

    @classmethod
    def from_environment(cls) -> "SecureMode":
        """Detect secure mode from ELSPETH_SECURE_MODE environment variable.

        Returns:
            SecureMode: The detected mode (defaults to STANDARD)

        Examples:
            >>> os.environ["ELSPETH_SECURE_MODE"] = "strict"
            >>> SecureMode.from_environment()
            <SecureMode.STRICT: 'strict'>
        """
        mode_str = os.environ.get("ELSPETH_SECURE_MODE", "standard").lower().strip()

        try:
            return cls(mode_str)
        except ValueError:
            logger.warning(
                f"Invalid ELSPETH_SECURE_MODE='{mode_str}', defaulting to STANDARD. Valid values: {', '.join([m.value for m in cls])}"
            )
            return cls.STANDARD


def get_secure_mode() -> SecureMode:
    """Get current secure mode from environment.

    Returns:
        SecureMode: Current mode (defaults to STANDARD)
    """
    return SecureMode.from_environment()


def is_strict_mode() -> bool:
    """Check if running in STRICT mode.

    Returns:
        bool: True if STRICT mode is active
    """
    return get_secure_mode() == SecureMode.STRICT


def is_development_mode() -> bool:
    """Check if running in DEVELOPMENT mode.

    Returns:
        bool: True if DEVELOPMENT mode is active
    """
    return get_secure_mode() == SecureMode.DEVELOPMENT


def _validate_security_level_required(config: dict[str, Any], plugin_type: str, mode: SecureMode) -> None:
    """Validate security_level is present according to mode.

    Args:
        config: Plugin configuration dictionary
        plugin_type: Type name for error messages (e.g., "Datasource", "LLM", "Sink")
        mode: Secure mode

    Raises:
        ValueError: If security_level missing in STRICT/STANDARD mode
    """
    if "security_level" not in config and mode != SecureMode.DEVELOPMENT:
        raise ValueError(f"{plugin_type} missing required 'security_level' ({mode.value.upper()} mode)")

    if "security_level" not in config and mode == SecureMode.DEVELOPMENT:
        logger.warning(f"{plugin_type} missing 'security_level' - allowed in DEVELOPMENT mode")


def validate_datasource_config(config: dict[str, Any], mode: SecureMode | None = None) -> None:
    """Validate datasource configuration according to secure mode.

    Args:
        config: Datasource configuration dictionary
        mode: Secure mode (auto-detected if None)

    Raises:
        ValueError: If configuration violates secure mode requirements

    Examples:
        >>> validate_datasource_config({"type": "local_csv", "path": "data.csv"})
        Traceback (most recent call last):
        ...
        ValueError: Datasource missing required 'security_level' (STANDARD mode)
    """
    if mode is None:
        mode = get_secure_mode()

    # Validate security_level requirement
    _validate_security_level_required(config, "Datasource", mode)

    # Check retain_local requirement
    retain_local = config.get("retain_local")

    if mode == SecureMode.STRICT:
        if retain_local is False:
            raise ValueError(
                "Datasource has retain_local=False which violates STRICT mode (audit requirement: all source data must be retained)"
            )
        if retain_local is None:
            logger.warning("Datasource missing 'retain_local' - should be explicit True in STRICT mode")

    elif mode == SecureMode.STANDARD:
        if retain_local is False:
            logger.warning("Datasource has retain_local=False - consider enabling for audit compliance")


def validate_llm_config(config: dict[str, Any], mode: SecureMode | None = None) -> None:
    """Validate LLM configuration according to secure mode.

    Args:
        config: LLM configuration dictionary
        mode: Secure mode (auto-detected if None)

    Raises:
        ValueError: If configuration violates secure mode requirements
    """
    if mode is None:
        mode = get_secure_mode()

    # Validate security_level requirement
    _validate_security_level_required(config, "LLM", mode)

    # Check for mock LLM usage
    llm_type = config.get("type", "")

    if mode == SecureMode.STRICT and llm_type in ["mock", "static_test"]:
        raise ValueError(f"LLM type '{llm_type}' is not allowed in STRICT mode (production requires real LLM clients)")

    if mode == SecureMode.STANDARD and llm_type in ["mock", "static_test"]:
        logger.warning(f"Using mock LLM type '{llm_type}' - consider real LLM for production")


def validate_sink_config(config: dict[str, Any], mode: SecureMode | None = None) -> None:
    """Validate sink configuration according to secure mode.

    Args:
        config: Sink configuration dictionary
        mode: Secure mode (auto-detected if None)

    Raises:
        ValueError: If configuration violates secure mode requirements
    """
    if mode is None:
        mode = get_secure_mode()

    # Validate security_level requirement
    _validate_security_level_required(config, "Sink", mode)

    # Enforce path containment and sanitization requirements for local sinks
    sink_type = (config.get("type", "") or "").strip().lower()
    if sink_type in get_path_contained_sink_types():
        sanitize_formulas = config.get("sanitize_formulas", True)

        if mode == SecureMode.STRICT and sanitize_formulas is False:
            raise ValueError(
                f"Sink type '{sink_type}' has sanitize_formulas=False which violates STRICT mode (formula injection protection required)"
            )

        if mode == SecureMode.STANDARD and sanitize_formulas is False:
            logger.warning(f"Sink type '{sink_type}' has sanitize_formulas=False - consider enabling for security")

        # Enforce explicit base-path containment for local filesystem sinks in STRICT
        allowed_base = config.get("allowed_base_path")
        if mode == SecureMode.STRICT and not allowed_base:
            raise ValueError(f"Sink type '{sink_type}' requires explicit 'allowed_base_path' in STRICT mode (path containment enforcement)")


def validate_middleware_config(middleware: list[dict[str, Any]], mode: SecureMode | None = None) -> None:
    """Validate middleware configuration according to secure mode.

    Args:
        middleware: List of middleware configurations
        mode: Secure mode (auto-detected if None)

    Raises:
        ValueError: If configuration violates secure mode requirements
    """
    if mode is None:
        mode = get_secure_mode()

    if mode == SecureMode.STRICT:
        # STRICT mode requires audit logging middleware
        has_audit = any(mw.get("type") == "audit_logger" for mw in middleware)

        if not has_audit:
            logger.warning("No 'audit_logger' middleware found - strongly recommended in STRICT mode for compliance and audit requirements")


def get_mode_description(mode: SecureMode | None = None) -> str:
    """Get human-readable description of secure mode requirements.

    Args:
        mode: Secure mode (auto-detected if None)

    Returns:
        str: Description of mode requirements
    """
    if mode is None:
        mode = get_secure_mode()

    descriptions = {
        SecureMode.STRICT: """STRICT mode (production):
- security_level REQUIRED for all datasources, LLMs, and sinks
- retain_local REQUIRED (True) for datasources
- Mock LLMs NOT ALLOWED
- Formula sanitization REQUIRED (enabled)
- Audit logging middleware RECOMMENDED""",
        SecureMode.STANDARD: """STANDARD mode (default):
- security_level REQUIRED for all datasources, LLMs, and sinks
- retain_local RECOMMENDED (warns if False)
- Mock LLMs ALLOWED (warns)
- Formula sanitization ENABLED by default (warns if disabled)""",
        SecureMode.DEVELOPMENT: """DEVELOPMENT mode (permissive):
- security_level OPTIONAL (defaults applied)
- retain_local OPTIONAL
- Mock LLMs ALLOWED
- Formula sanitization CAN BE DISABLED (for testing only)""",
    }

    return descriptions[mode]


__all__ = [
    "SecureMode",
    "get_secure_mode",
    "is_strict_mode",
    "is_development_mode",
    "validate_datasource_config",
    "validate_llm_config",
    "validate_sink_config",
    "validate_middleware_config",
    "get_mode_description",
]
