# src/elspeth/contracts/config/__init__.py
"""Configuration contracts subpackage.

This subpackage contains:
- Settings classes (re-exported from core/config.py)
- Runtime protocols (protocols.py)
- Default registries (defaults.py)
- Field alignment documentation (alignment.py)

Import pattern:
    # Settings classes (most common)
    from elspeth.contracts.config import RetrySettings, CheckpointSettings

    # Runtime protocols (for type hints accepting runtime config)
    from elspeth.contracts.config import RuntimeRetryProtocol

    # Defaults (for runtime config construction)
    from elspeth.contracts.config import POLICY_DEFAULTS, INTERNAL_DEFAULTS

    # Alignment (for tooling/tests)
    from elspeth.contracts.config import FIELD_MAPPINGS, EXEMPT_SETTINGS
"""

# =============================================================================
# Settings classes (re-exports from core/config.py)
# =============================================================================
# These are the original Pydantic models for user configuration.
# Re-exported here for import consistency: `from elspeth.contracts import ...`

# =============================================================================
# Field alignment documentation
# =============================================================================
# Machine-readable mapping of Settings -> Runtime field names
from elspeth.contracts.config.alignment import (
    EXEMPT_SETTINGS,
    FIELD_MAPPINGS,
    SETTINGS_TO_RUNTIME,
    get_runtime_field_name,
    get_settings_field_name,
    is_exempt_settings,
)

# =============================================================================
# Default registries
# =============================================================================
# INTERNAL_DEFAULTS: Hardcoded values not exposed in Settings
# POLICY_DEFAULTS: Defaults for plugin RetryPolicy dicts
from elspeth.contracts.config.defaults import (
    INTERNAL_DEFAULTS,
    POLICY_DEFAULTS,
    get_internal_default,
    get_policy_default,
)

# =============================================================================
# Runtime protocols
# =============================================================================
# Protocols that define what engine components expect from runtime config.
from elspeth.contracts.config.protocols import (
    RuntimeCheckpointProtocol,
    RuntimeConcurrencyProtocol,
    RuntimeRateLimitProtocol,
    RuntimeRetryProtocol,
)

# =============================================================================
# Runtime configuration dataclasses
# =============================================================================
# Concrete implementations of Runtime*Protocol interfaces.
from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig, RuntimeRateLimitConfig, RuntimeRetryConfig
from elspeth.core.config import (
    AggregationSettings,
    CheckpointSettings,
    CoalesceSettings,
    ConcurrencySettings,
    DatabaseSettings,
    ElspethSettings,
    GateSettings,
    LandscapeExportSettings,
    LandscapeSettings,
    PayloadStoreSettings,
    RateLimitSettings,
    RetrySettings,
    ServiceRateLimit,
    SinkSettings,
    SourceSettings,
    TransformSettings,
    TriggerConfig,
)

__all__ = [
    "EXEMPT_SETTINGS",
    "FIELD_MAPPINGS",
    "INTERNAL_DEFAULTS",
    "POLICY_DEFAULTS",
    "SETTINGS_TO_RUNTIME",
    "AggregationSettings",
    "CheckpointSettings",
    "CoalesceSettings",
    "ConcurrencySettings",
    "DatabaseSettings",
    "ElspethSettings",
    "GateSettings",
    "LandscapeExportSettings",
    "LandscapeSettings",
    "PayloadStoreSettings",
    "RateLimitSettings",
    "RetrySettings",
    "RuntimeCheckpointProtocol",
    "RuntimeConcurrencyConfig",
    "RuntimeConcurrencyProtocol",
    "RuntimeRateLimitConfig",
    "RuntimeRateLimitProtocol",
    "RuntimeRetryConfig",
    "RuntimeRetryProtocol",
    "ServiceRateLimit",
    "SinkSettings",
    "SourceSettings",
    "TransformSettings",
    "TriggerConfig",
    "get_internal_default",
    "get_policy_default",
    "get_runtime_field_name",
    "get_settings_field_name",
    "is_exempt_settings",
]
