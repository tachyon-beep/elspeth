# src/elspeth/contracts/config/protocols.py
"""Runtime protocols for Settings -> Runtime enforcement.

These protocols define what engine components EXPECT from runtime config.
By having runtime config classes implement these protocols, we get:
1. Compile-time verification that Settings fields reach runtime
2. Clear documentation of what each component needs

Protocol Pattern:
    - Protocol defines minimal interface a component needs
    - Runtime config dataclass implements the protocol
    - Component accepts the protocol, not the concrete class
    - mypy verifies structural compatibility

Example:
    class RuntimeRetryConfig:
        max_attempts: int
        base_delay: float
        ...

    def __init__(self, config: RuntimeRetryProtocol):
        # mypy verifies RuntimeRetryConfig satisfies this
        self._config = config

Note on jitter:
    jitter is INTERNAL to RetryConfig (hardcoded to 1.0, not in Settings).
    It's deliberately excluded from RuntimeRetryProtocol - the protocol only
    defines what Settings MUST provide, not internal implementation details.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class RuntimeRetryProtocol(Protocol):
    """What RetryManager expects from retry configuration.

    These fields come from RetrySettings (possibly with name mapping):
    - max_attempts: RetrySettings.max_attempts (direct)
    - base_delay: RetrySettings.initial_delay_seconds (renamed)
    - max_delay: RetrySettings.max_delay_seconds (renamed)
    - exponential_base: RetrySettings.exponential_base (direct)

    Note: jitter is internal-only (hardcoded in RetryConfig, not in Settings).
    """

    @property
    def max_attempts(self) -> int:
        """Maximum number of attempts (includes initial try)."""
        ...

    @property
    def base_delay(self) -> float:
        """Initial backoff delay in seconds."""
        ...

    @property
    def max_delay(self) -> float:
        """Maximum backoff delay in seconds."""
        ...

    @property
    def exponential_base(self) -> float:
        """Exponential backoff multiplier (e.g., 2.0 for doubling)."""
        ...


@runtime_checkable
class RuntimeRateLimitProtocol(Protocol):
    """What RateLimitRegistry expects from rate limit configuration.

    These fields come from RateLimitSettings:
    - enabled: Whether rate limiting is active
    - default_requests_per_second: Fallback rate for unconfigured services
    - default_requests_per_minute: Optional per-minute limit

    Note: services and persistence_path are handled separately
    (services is a nested dict, persistence_path is optional infrastructure).
    """

    @property
    def enabled(self) -> bool:
        """Whether rate limiting is active."""
        ...

    @property
    def default_requests_per_second(self) -> float:
        """Default requests per second for unconfigured services."""
        ...

    @property
    def default_requests_per_minute(self) -> float | None:
        """Optional default requests per minute limit."""
        ...


@runtime_checkable
class RuntimeConcurrencyProtocol(Protocol):
    """What ThreadPoolExecutor/Orchestrator expects from concurrency config.

    Simple - just needs max_workers from ConcurrencySettings.
    """

    @property
    def max_workers(self) -> int:
        """Maximum number of parallel workers."""
        ...


@runtime_checkable
class RuntimeCheckpointProtocol(Protocol):
    """What checkpoint system expects from checkpoint configuration.

    Maps CheckpointSettings fields:
    - enabled: CheckpointSettings.enabled (direct)
    - frequency: CheckpointSettings.frequency mapped to int
    - aggregation_boundaries: CheckpointSettings.aggregation_boundaries (direct)

    Note: checkpoint_interval is conditional on frequency="every_n" and
    handled during construction, not as a protocol field.
    """

    @property
    def enabled(self) -> bool:
        """Whether checkpointing is active."""
        ...

    @property
    def frequency(self) -> int:
        """Checkpoint every N rows (1 = every row, 0 = aggregation only)."""
        ...

    @property
    def aggregation_boundaries(self) -> bool:
        """Whether to checkpoint at aggregation flush boundaries."""
        ...
