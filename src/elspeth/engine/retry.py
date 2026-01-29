# src/elspeth/engine/retry.py
"""RetryManager: Retry logic with tenacity integration.

Provides configurable retry behavior for transform execution:
- Exponential backoff with jitter
- Configurable max attempts
- Retryable error filtering
- Attempt tracking for Landscape

Integration Point (Phase 5):
    The RowProcessor should use RetryManager.execute_with_retry() around
    transform execution. Each retry attempt must be auditable with the key
    (run_id, row_id, transform_seq, attempt). The on_retry callback should
    call recorder.record_retry_attempt() to audit each attempt, ensuring
    complete traceability of transient failures and recovery.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast

if TYPE_CHECKING:
    from elspeth.core.config import RetrySettings

from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from elspeth.contracts import RetryPolicy

T = TypeVar("T")

# Explicit defaults for RetryPolicy fields - MUST match RetryConfig defaults.
# If you add a field to RetryConfig, add it here too or from_policy() will crash.
# This is intentional - crashing on missing fields prevents silent bugs.
POLICY_DEFAULTS: dict[str, int | float] = {
    "max_attempts": 3,
    "base_delay": 1.0,
    "max_delay": 60.0,
    "jitter": 1.0,
    "exponential_base": 2.0,
}


def _merge_policy_with_defaults(policy: RetryPolicy) -> dict[str, Any]:
    """Merge policy with defaults, returning dict with numeric values.

    Policy values override defaults. The result has all POLICY_DEFAULTS keys
    with values from either policy (if present) or defaults.
    """
    return {**POLICY_DEFAULTS, **cast(dict[str, Any], policy)}


class MaxRetriesExceeded(Exception):
    """Raised when max retry attempts are exceeded."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Max retries ({attempts}) exceeded: {last_error}")


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    max_attempts is the TOTAL number of tries, not the number of retries.
    So max_attempts=3 means: try, retry, retry (3 total).
    """

    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    jitter: float = 1.0  # seconds
    exponential_base: float = 2.0  # backoff multiplier

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    @classmethod
    def no_retry(cls) -> "RetryConfig":
        """Factory for no-retry configuration (single attempt)."""
        return cls(max_attempts=1)

    @classmethod
    def from_policy(cls, policy: RetryPolicy | None) -> "RetryConfig":
        """Factory from plugin policy dict.

        RetryPolicy is total=False (all fields optional), so plugins can specify
        partial overrides. Missing fields use POLICY_DEFAULTS.

        This is a trust boundary - plugin config (user YAML) may have invalid
        values that need clamping to safe minimums.

        Note: We deliberately avoid .get() here. If a field exists in RetryConfig
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

    @classmethod
    def from_settings(cls, settings: "RetrySettings") -> "RetryConfig":
        """Factory from RetrySettings config model.

        Args:
            settings: Validated Pydantic settings model

        Returns:
            RetryConfig with mapped values
        """
        return cls(
            max_attempts=settings.max_attempts,
            base_delay=settings.initial_delay_seconds,
            max_delay=settings.max_delay_seconds,
            jitter=1.0,  # Fixed jitter, not exposed in settings
            exponential_base=settings.exponential_base,
        )


class RetryManager:
    """Manages retry logic for transform execution.

    Uses tenacity for exponential backoff with jitter.
    Integrates with Landscape for attempt tracking.

    Example:
        manager = RetryManager(RetryConfig(max_attempts=3))

        result = manager.execute_with_retry(
            operation=lambda: transform.process(row, ctx),
            is_retryable=lambda e: e.retryable,
            on_retry=lambda attempt, error: recorder.record_attempt(attempt, error),
        )
    """

    def __init__(self, config: RetryConfig) -> None:
        """Initialize with config.

        Args:
            config: Retry configuration
        """
        self._config = config

    def execute_with_retry(
        self,
        operation: Callable[[], T],
        *,
        is_retryable: Callable[[BaseException], bool],
        on_retry: Callable[[int, BaseException], None] | None = None,
    ) -> T:
        """Execute operation with retry logic.

        Args:
            operation: Operation to execute
            is_retryable: Function to check if error is retryable
            on_retry: Optional callback on retry (attempt, error)

        Returns:
            Result of operation

        Raises:
            MaxRetriesExceeded: If max attempts exceeded
            Exception: If non-retryable error occurs
        """
        attempt = 0
        last_error: BaseException | None = None

        try:
            for attempt_state in Retrying(
                stop=stop_after_attempt(self._config.max_attempts),
                wait=wait_exponential_jitter(
                    initial=self._config.base_delay,
                    max=self._config.max_delay,
                    exp_base=self._config.exponential_base,
                    jitter=self._config.jitter,
                ),
                retry=retry_if_exception(is_retryable),
                reraise=False,  # We catch RetryError and convert to MaxRetriesExceeded
            ):
                with attempt_state:
                    attempt = attempt_state.retry_state.attempt_number
                    try:
                        return operation()
                    except Exception as e:
                        last_error = e
                        # Only call on_retry for retryable errors that will be retried
                        if is_retryable(e) and on_retry:
                            on_retry(attempt, e)
                        raise

        except RetryError as e:
            # Retries exhausted - wrap in MaxRetriesExceeded
            # last_error is always set because RetryError means at least one attempt failed
            final_error = last_error or e.last_attempt.exception()
            assert final_error is not None, "RetryError without exception is impossible"
            raise MaxRetriesExceeded(attempt, final_error) from e

        # Should not reach here - Retrying always returns or raises
        raise RuntimeError("Unexpected state in retry loop")  # pragma: no cover
