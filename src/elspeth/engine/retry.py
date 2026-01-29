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

Configuration:
    RetryManager accepts RuntimeRetryProtocol, allowing structural typing.
    Use RuntimeRetryConfig from contracts/config for concrete instances:
    - RuntimeRetryConfig.from_settings(settings.retry) - from YAML config
    - RuntimeRetryConfig.from_policy(policy) - from plugin policies
    - RuntimeRetryConfig.default() - standard retry behavior
    - RuntimeRetryConfig.no_retry() - single attempt, no retries
"""

from collections.abc import Callable
from typing import TypeVar

from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from elspeth.contracts.config import RuntimeRetryProtocol

T = TypeVar("T")


class MaxRetriesExceeded(Exception):
    """Raised when max retry attempts are exceeded."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Max retries ({attempts}) exceeded: {last_error}")


class RetryManager:
    """Manages retry logic for transform execution.

    Uses tenacity for exponential backoff with jitter.
    Integrates with Landscape for attempt tracking.

    Example:
        from elspeth.contracts.config import RuntimeRetryConfig

        manager = RetryManager(RuntimeRetryConfig(max_attempts=3, base_delay=1.0, max_delay=60.0, jitter=1.0, exponential_base=2.0))

        result = manager.execute_with_retry(
            operation=lambda: transform.process(row, ctx),
            is_retryable=lambda e: e.retryable,
            on_retry=lambda attempt, error: recorder.record_attempt(attempt, error),
        )
    """

    def __init__(self, config: RuntimeRetryProtocol) -> None:
        """Initialize with config implementing RuntimeRetryProtocol.

        Args:
            config: Retry configuration (must implement RuntimeRetryProtocol)
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
