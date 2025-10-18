"""Rate limiter protocols and implementations."""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from threading import Lock
from typing import Any, ContextManager, Deque, Iterator, SupportsFloat


def _coerce_float(value: object, *, context: str) -> float:
    """Convert a value to float, raising a descriptive error when invalid."""

    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"Invalid numeric value for {context}: {value!r}") from exc
    if isinstance(value, SupportsFloat):
        return float(value)
    raise TypeError(f"Value for {context} must be numeric, received {type(value).__name__}")


class RateLimiter:
    """Base protocol for rate limiters."""

    def acquire(self, metadata: dict[str, object | None] | None = None) -> ContextManager[None]:
        """Return a context manager that enforces the rate limit."""

        del metadata  # Unused in base implementation.
        raise NotImplementedError

    def utilization(self) -> float:  # pragma: no cover - default no usage
        """Return a utilization ratio in the range [0, 1]."""

        return 0.0

    def update_usage(
        self, response: dict[str, Any], metadata: dict[str, object | None] | None = None
    ) -> None:  # pragma: no cover - optional override
        """Record response metadata to refine future rate limiting."""

        del response, metadata  # Unused in base implementation.


class NoopRateLimiter(RateLimiter):
    """Limiter implementation that performs no throttling."""

    def acquire(self, metadata: dict[str, object | None] | None = None) -> ContextManager[None]:  # pragma: no cover - trivial
        @contextmanager
        def _cm() -> Iterator[None]:
            yield

        return _cm()

    def utilization(self) -> float:  # pragma: no cover - trivial
        return 0.0


class FixedWindowRateLimiter(RateLimiter):
    """Simple fixed window limiter enforcing N requests per interval."""

    def __init__(self, requests: int = 1, per_seconds: float = 1.0):
        if requests <= 0 or per_seconds <= 0:
            raise ValueError("requests and per_seconds must be positive")
        self.requests = requests
        self.per_seconds = per_seconds
        self._lock = Lock()
        self._window_start = 0.0
        self._count = 0
        self._usage_ratio = 0.0

    def acquire(self, metadata: dict[str, object | None] | None = None) -> ContextManager[None]:
        @contextmanager
        def _cm() -> Iterator[None]:
            while True:
                with self._lock:
                    now = time.time()
                    elapsed = now - self._window_start
                    if elapsed >= self.per_seconds:
                        self._window_start = now
                        self._count = 0
                    if self._count < self.requests:
                        self._count += 1
                        self._usage_ratio = min(1.0, self._count / self.requests)
                        break
                    sleep_for = self.per_seconds - elapsed
                time.sleep(max(sleep_for, 0.001))
            yield

        return _cm()

    def utilization(self) -> float:
        with self._lock:
            now = time.time()
            if now - self._window_start >= self.per_seconds:
                self._window_start = now
                self._count = 0
                self._usage_ratio = 0.0
            return min(1.0, self._usage_ratio)


class AdaptiveRateLimiter(RateLimiter):
    """Limiter supporting request and token ceilings per interval."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        tokens_per_minute: int | None = None,
        interval_seconds: float = 60.0,
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        self.interval = interval_seconds
        self._lock = Lock()
        self._request_times: Deque[float] = deque()
        self._token_records: Deque[tuple[float, float]] = deque()
        self._last_utilization = 0.0

    def acquire(self, metadata: dict[str, object | None] | None = None) -> ContextManager[None]:
        estimated_tokens = 0.0
        if metadata:
            value = metadata.get("estimated_tokens")
            if value is None:
                value = metadata.get("expected_tokens")
            if value is not None:
                estimated_tokens = _coerce_float(value, context="estimated tokens")

        @contextmanager
        def _cm() -> Iterator[None]:
            while True:
                with self._lock:
                    now = time.time()
                    self._trim(now)
                    request_usage = len(self._request_times) / self.requests_per_minute
                    token_usage = 0.0
                    if self.tokens_per_minute:
                        current_tokens = sum(tokens for _, tokens in self._token_records)
                        token_usage = (current_tokens + estimated_tokens) / self.tokens_per_minute
                    self._last_utilization = max(request_usage, token_usage)
                    if request_usage < 1.0 and (self.tokens_per_minute is None or token_usage < 1.0):
                        self._request_times.append(now)
                        break
                    sleep_for = self._next_available_time(now)
                time.sleep(sleep_for)
            yield

        return _cm()

    def update_usage(self, response: dict[str, Any], metadata: dict[str, object | None] | None = None) -> None:
        if self.tokens_per_minute is None:
            return
        metrics = response.get("metrics") if isinstance(response, dict) else None
        tokens = 0.0
        if isinstance(metrics, dict):
            prompt = metrics.get("prompt_tokens")
            if prompt is not None:
                tokens += _coerce_float(prompt, context="prompt_tokens")
            completion = metrics.get("completion_tokens")
            if completion is not None:
                tokens += _coerce_float(completion, context="completion_tokens")
        if tokens <= 0:
            return
        with self._lock:
            now = time.time()
            self._trim(now)
            self._token_records.append((now, tokens))

    def utilization(self) -> float:
        with self._lock:
            self._trim(time.time())
            request_usage = len(self._request_times) / self.requests_per_minute
            token_usage = 0.0
            if self.tokens_per_minute:
                current_tokens = sum(tokens for _, tokens in self._token_records)
                token_usage = current_tokens / self.tokens_per_minute
            self._last_utilization = max(request_usage, token_usage)
            return min(1.0, self._last_utilization)

    def _trim(self, now: float) -> None:
        cutoff = now - self.interval
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()
        while self._token_records and self._token_records[0][0] < cutoff:
            self._token_records.popleft()

    def _next_available_time(self, now: float) -> float:
        next_times = []
        if self._request_times:
            next_times.append(max(0.0, self._request_times[0] + self.interval - now))
        if self._token_records:
            next_times.append(max(0.0, self._token_records[0][0] + self.interval - now))
        return min(next_times) if next_times else 0.1


__all__ = [
    "RateLimiter",
    "NoopRateLimiter",
    "FixedWindowRateLimiter",
    "AdaptiveRateLimiter",
]
