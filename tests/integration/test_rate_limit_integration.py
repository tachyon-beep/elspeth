"""Integration tests for rate limit registry wiring.

These tests verify that RateLimitRegistry is properly wired through
the CLI -> Orchestrator -> PluginContext pipeline.
"""

import time
from typing import Any

from elspeth.contracts import TransformResult
from elspeth.contracts.config.runtime import RuntimeRateLimitConfig
from elspeth.core.config import RateLimitSettings
from elspeth.core.landscape import LandscapeDB
from elspeth.core.rate_limit import RateLimitRegistry
from elspeth.engine import Orchestrator
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.context import PluginContext


class RateLimitAwareTransform(BaseTransform):
    """Test transform that uses rate limiting from context."""

    name = "rate_limit_test"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._service_name = config.get("service_name", "test_service")
        self._call_times: list[float] = []

    def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
        """Process row, using rate limiter if available."""
        if ctx.rate_limit_registry is not None:
            limiter = ctx.rate_limit_registry.get_limiter(self._service_name)
            limiter.acquire()

        # Record the time of this call
        self._call_times.append(time.perf_counter())

        return TransformResult.success({"processed": True, **row}, success_reason={"action": "processed"})

    @property
    def call_times(self) -> list[float]:
        """Get the recorded call times."""
        return self._call_times


class TestRateLimitRegistryInOrchestrator:
    """Test that RateLimitRegistry is properly passed to Orchestrator."""

    def test_orchestrator_accepts_rate_limit_registry(self) -> None:
        """Orchestrator constructor accepts rate_limit_registry parameter."""
        db = LandscapeDB.in_memory()
        settings = RateLimitSettings(enabled=True, default_requests_per_minute=60)
        config = RuntimeRateLimitConfig.from_settings(settings)
        registry = RateLimitRegistry(config)

        try:
            # Should not raise
            orchestrator = Orchestrator(db, rate_limit_registry=registry)
            assert orchestrator._rate_limit_registry is registry
        finally:
            registry.close()
            db.close()

    def test_orchestrator_accepts_none_registry(self) -> None:
        """Orchestrator works without rate limit registry."""
        db = LandscapeDB.in_memory()

        try:
            orchestrator = Orchestrator(db, rate_limit_registry=None)
            assert orchestrator._rate_limit_registry is None
        finally:
            db.close()


class TestRateLimitRegistryInContext:
    """Test that RateLimitRegistry is available in PluginContext."""

    def test_context_has_rate_limit_registry_field(self) -> None:
        """PluginContext has rate_limit_registry field."""
        settings = RateLimitSettings(enabled=True, default_requests_per_minute=60)
        config = RuntimeRateLimitConfig.from_settings(settings)
        registry = RateLimitRegistry(config)

        try:
            ctx = PluginContext(
                run_id="test-run",
                config={},
                rate_limit_registry=registry,
            )
            assert ctx.rate_limit_registry is registry
        finally:
            registry.close()

    def test_context_without_registry(self) -> None:
        """PluginContext works without rate limit registry."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            rate_limit_registry=None,
        )
        assert ctx.rate_limit_registry is None


class TestRateLimitThrottling:
    """Test that rate limiting actually throttles requests."""

    def test_rate_limiter_throttles_excess_requests(self) -> None:
        """Verify rate limiter blocks when bucket is full.

        The bucket can hold requests_per_minute tokens. With 10 req/min:
        - First 10 calls go through immediately (filling the bucket)
        - 11th call must wait for a token to leak (the bucket to drain)
        """
        settings = RateLimitSettings(
            enabled=True,
            default_requests_per_minute=10,  # 10 per minute
        )
        config = RuntimeRateLimitConfig.from_settings(settings)
        registry = RateLimitRegistry(config)

        try:
            transform = RateLimitAwareTransform({"service_name": "throttle_test"})
            ctx = PluginContext(
                run_id="test-run",
                config={},
                rate_limit_registry=registry,
            )

            # Make 11 calls - first 10 should be instant (bucket holds 10)
            # The 11th should block waiting for a leak
            for i in range(11):
                transform.process({"id": i}, ctx)

            call_times = transform.call_times
            assert len(call_times) == 11

            # First 10 calls should be nearly instant
            first_10_delta = call_times[9] - call_times[0]
            assert first_10_delta < 0.1, f"First 10 calls took {first_10_delta * 1000:.0f}ms (expected instant)"

            # 11th call should have waited for a token leak
            # With 10 req/min, we need to wait for tokens to leak
            wait_for_11th = call_times[10] - call_times[9]
            assert wait_for_11th >= 0.05, f"11th call should have waited, only waited {wait_for_11th * 1000:.0f}ms"
        finally:
            registry.close()

    def test_disabled_rate_limit_no_throttle(self) -> None:
        """Verify disabled rate limiting doesn't throttle."""
        settings = RateLimitSettings(
            enabled=False,
            default_requests_per_minute=1,  # Would be slow if enabled
        )
        config = RuntimeRateLimitConfig.from_settings(settings)
        registry = RateLimitRegistry(config)

        try:
            transform = RateLimitAwareTransform({"service_name": "no_throttle_test"})
            ctx = PluginContext(
                run_id="test-run",
                config={},
                rate_limit_registry=registry,
            )

            # Make 5 calls rapidly
            for i in range(5):
                transform.process({"id": i}, ctx)

            call_times = transform.call_times
            assert len(call_times) == 5

            # Total time should be very short (no rate limiting)
            total_time = call_times[-1] - call_times[0]
            assert total_time < 0.1, f"Expected fast calls, took {total_time * 1000:.0f}ms"
        finally:
            registry.close()


class TestRateLimitServiceConfig:
    """Test per-service rate limit configuration."""

    def test_per_service_rate_limits(self) -> None:
        """Different services can have different rate limits."""
        from elspeth.core.config import ServiceRateLimit

        settings = RateLimitSettings(
            enabled=True,
            default_requests_per_minute=60,
            services={
                "slow_service": ServiceRateLimit(requests_per_minute=10),
                "fast_service": ServiceRateLimit(requests_per_minute=600),
            },
        )
        config = RuntimeRateLimitConfig.from_settings(settings)
        registry = RateLimitRegistry(config)

        try:
            # Get limiters for different services
            slow_limiter = registry.get_limiter("slow_service")
            fast_limiter = registry.get_limiter("fast_service")
            default_limiter = registry.get_limiter("unknown_service")

            # All should be real limiters (enabled=True)
            from elspeth.core.rate_limit import NoOpLimiter

            assert not isinstance(slow_limiter, NoOpLimiter)
            assert not isinstance(fast_limiter, NoOpLimiter)
            assert not isinstance(default_limiter, NoOpLimiter)
        finally:
            registry.close()
