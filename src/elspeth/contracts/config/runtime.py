# src/elspeth/contracts/config/runtime.py
"""Runtime configuration dataclasses.

These dataclasses implement the Runtime*Protocol interfaces and provide
factory methods to construct from Settings objects or plugin policies.

Design Principles:
1. Frozen (immutable) - runtime config should never change mid-execution
2. Slots - memory efficient, prevents attribute typos
3. Protocol compliance - implements Runtime*Protocol for structural typing
4. Factory methods - from_settings(), from_policy(), default(), no_retry()

Field Origins:
- Settings fields: Come from user YAML configuration via Pydantic models
- Internal fields: Hardcoded implementation details, documented in INTERNAL_DEFAULTS

See alignment.py for complete field mapping documentation.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from elspeth.contracts.config.defaults import INTERNAL_DEFAULTS, POLICY_DEFAULTS
from elspeth.contracts.engine import RetryPolicy

if TYPE_CHECKING:
    from elspeth.core.config import ConcurrencySettings, RateLimitSettings, RetrySettings, ServiceRateLimit


def _merge_policy_with_defaults(policy: RetryPolicy) -> dict[str, Any]:
    """Merge policy with defaults, returning dict with numeric values.

    Policy values override defaults. The result has all POLICY_DEFAULTS keys
    with values from either policy (if present) or defaults.
    """
    return {**POLICY_DEFAULTS, **cast(dict[str, Any], policy)}


@dataclass(frozen=True, slots=True)
class RuntimeRetryConfig:
    """Runtime configuration for retry behavior.

    Implements RuntimeRetryProtocol for structural typing verification.

    Field Origins:
        - max_attempts: RetrySettings.max_attempts (direct mapping)
        - base_delay: RetrySettings.initial_delay_seconds (renamed)
        - max_delay: RetrySettings.max_delay_seconds (renamed)
        - exponential_base: RetrySettings.exponential_base (direct mapping)
        - jitter: INTERNAL - hardcoded to 1.0 second (see INTERNAL_DEFAULTS["retry"]["jitter"])

    Why jitter is internal:
        Jitter adds randomness to backoff delays to prevent thundering herd
        problems when many clients retry simultaneously. The value (1.0 second)
        is a reasonable default that users shouldn't need to tune. Exposing it
        in Settings would add configuration surface without practical benefit.

    Note: max_attempts is the TOTAL number of tries, not the number of retries.
    So max_attempts=3 means: try, retry, retry (3 total).
    """

    max_attempts: int
    base_delay: float  # seconds
    max_delay: float  # seconds
    jitter: float  # seconds - INTERNAL, not from Settings
    exponential_base: float  # backoff multiplier

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    @classmethod
    def default(cls) -> "RuntimeRetryConfig":
        """Factory for default retry configuration.

        Uses POLICY_DEFAULTS values - the standard retry behavior.
        """
        return cls(
            max_attempts=int(POLICY_DEFAULTS["max_attempts"]),
            base_delay=float(POLICY_DEFAULTS["base_delay"]),
            max_delay=float(POLICY_DEFAULTS["max_delay"]),
            jitter=float(POLICY_DEFAULTS["jitter"]),
            exponential_base=float(POLICY_DEFAULTS["exponential_base"]),
        )

    @classmethod
    def no_retry(cls) -> "RuntimeRetryConfig":
        """Factory for no-retry configuration (single attempt).

        Useful for operations that should not be retried on failure.
        """
        return cls(
            max_attempts=1,
            base_delay=float(POLICY_DEFAULTS["base_delay"]),
            max_delay=float(POLICY_DEFAULTS["max_delay"]),
            jitter=float(POLICY_DEFAULTS["jitter"]),
            exponential_base=float(POLICY_DEFAULTS["exponential_base"]),
        )

    @classmethod
    def from_settings(cls, settings: "RetrySettings") -> "RuntimeRetryConfig":
        """Factory from RetrySettings config model.

        Field Mapping:
            settings.max_attempts -> max_attempts (direct)
            settings.initial_delay_seconds -> base_delay (renamed)
            settings.max_delay_seconds -> max_delay (renamed)
            settings.exponential_base -> exponential_base (direct)
            jitter <- INTERNAL_DEFAULTS["retry"]["jitter"] (hardcoded)

        Args:
            settings: Validated Pydantic settings model

        Returns:
            RuntimeRetryConfig with mapped values
        """
        return cls(
            max_attempts=settings.max_attempts,
            base_delay=settings.initial_delay_seconds,
            max_delay=settings.max_delay_seconds,
            jitter=float(INTERNAL_DEFAULTS["retry"]["jitter"]),
            exponential_base=settings.exponential_base,
        )

    @classmethod
    def from_policy(cls, policy: RetryPolicy | None) -> "RuntimeRetryConfig":
        """Factory from plugin policy dict.

        RetryPolicy is total=False (all fields optional), so plugins can specify
        partial overrides. Missing fields use POLICY_DEFAULTS.

        This is a trust boundary - plugin config (user YAML) may have invalid
        values that need clamping to safe minimums.

        Args:
            policy: Optional RetryPolicy dict from plugin configuration.
                   If None, returns no_retry() configuration.

        Returns:
            RuntimeRetryConfig with policy values (or defaults for missing fields)

        Note: We deliberately avoid .get() here. If a field exists in RuntimeRetryConfig
        but not in POLICY_DEFAULTS, the direct access below will crash. This is
        intentional - it catches the bug at development time, not production.
        """
        if policy is None:
            return cls.no_retry()

        # Merge explicit defaults with provided policy - policy values override
        full = _merge_policy_with_defaults(policy)

        # Direct access - crashes if POLICY_DEFAULTS is missing a field
        # Clamp values to safe minimums (user config may have invalid values)
        # Type narrowing: values are int|float from POLICY_DEFAULTS or policy
        max_attempts = full["max_attempts"]
        base_delay = full["base_delay"]
        max_delay_val = full["max_delay"]
        jitter = full["jitter"]
        exponential_base = full["exponential_base"]

        return cls(
            max_attempts=max(1, int(max_attempts)),
            base_delay=max(0.01, float(base_delay)),
            max_delay=max(0.1, float(max_delay_val)),
            jitter=max(0.0, float(jitter)),
            exponential_base=max(1.01, float(exponential_base)),
        )


@dataclass(frozen=True, slots=True)
class RuntimeRateLimitConfig:
    """Runtime configuration for rate limiting.

    Implements RuntimeRateLimitProtocol for structural typing verification.

    Field Origins (all from RateLimitSettings, direct mapping):
        - enabled: RateLimitSettings.enabled
        - default_requests_per_second: RateLimitSettings.default_requests_per_second
        - default_requests_per_minute: RateLimitSettings.default_requests_per_minute
        - persistence_path: RateLimitSettings.persistence_path
        - services: RateLimitSettings.services

    Protocol Coverage:
        RuntimeRateLimitProtocol requires: enabled, default_requests_per_second,
        default_requests_per_minute. The additional fields (persistence_path, services)
        are preserved for full Settings fidelity but not part of the protocol.

    Note: Unlike RetryConfig, there are no plugin-level rate limit overrides.
    Rate limiting is configured globally in Settings only.
    """

    enabled: bool
    default_requests_per_second: float | None
    default_requests_per_minute: float | None
    persistence_path: str | None
    services: dict[str, "ServiceRateLimit"]

    @classmethod
    def default(cls) -> "RuntimeRateLimitConfig":
        """Factory for default rate limit configuration.

        Returns disabled rate limiting - no constraints by default.
        This is safe because rate limiting is opt-in.
        """
        return cls(
            enabled=False,
            default_requests_per_second=None,
            default_requests_per_minute=None,
            persistence_path=None,
            services={},
        )

    @classmethod
    def from_settings(cls, settings: "RateLimitSettings") -> "RuntimeRateLimitConfig":
        """Factory from RateLimitSettings config model.

        Field Mapping (all direct, no renames):
            settings.enabled -> enabled
            settings.default_requests_per_second -> default_requests_per_second (int -> float)
            settings.default_requests_per_minute -> default_requests_per_minute (int -> float)
            settings.persistence_path -> persistence_path
            settings.services -> services

        Note: Protocol expects float for rate fields, but Settings uses int.
        We convert int to float for protocol compliance.

        Args:
            settings: Validated Pydantic settings model

        Returns:
            RuntimeRateLimitConfig with mapped values
        """
        return cls(
            enabled=settings.enabled,
            default_requests_per_second=float(settings.default_requests_per_second),
            default_requests_per_minute=(
                float(settings.default_requests_per_minute) if settings.default_requests_per_minute is not None else None
            ),
            persistence_path=settings.persistence_path,
            services=dict(settings.services),
        )


@dataclass(frozen=True, slots=True)
class RuntimeConcurrencyConfig:
    """Runtime configuration for concurrency/parallelism.

    Implements RuntimeConcurrencyProtocol for structural typing verification.

    Field Origins (all from ConcurrencySettings, direct mapping):
        - max_workers: ConcurrencySettings.max_workers

    This is the simplest runtime config - just one field controlling
    the maximum number of parallel workers for thread pool execution.

    Note: Unlike RetryConfig, there are no plugin-level concurrency overrides.
    Concurrency is configured globally in Settings only.
    """

    max_workers: int

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_workers < 1:
            raise ValueError("max_workers must be >= 1")

    @classmethod
    def default(cls) -> "RuntimeConcurrencyConfig":
        """Factory for default concurrency configuration.

        Returns config with max_workers=4 (same as ConcurrencySettings default).
        """
        return cls(max_workers=4)

    @classmethod
    def from_settings(cls, settings: "ConcurrencySettings") -> "RuntimeConcurrencyConfig":
        """Factory from ConcurrencySettings config model.

        Field Mapping (direct, no renames):
            settings.max_workers -> max_workers

        Args:
            settings: Validated Pydantic settings model

        Returns:
            RuntimeConcurrencyConfig with mapped values
        """
        return cls(max_workers=settings.max_workers)
