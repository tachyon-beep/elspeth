"""Tests for ComposerRateLimiter -- in-memory sliding window rate limiter."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi import HTTPException

from elspeth.web.middleware.rate_limit import ComposerRateLimiter


class TestRateLimiterAllow:
    """Tests that requests within the limit are allowed."""

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self) -> None:
        limiter = ComposerRateLimiter(limit=5)
        for _ in range(5):
            await limiter.check("user_1")

    @pytest.mark.asyncio
    async def test_first_request_always_allowed(self) -> None:
        limiter = ComposerRateLimiter(limit=1)
        await limiter.check("user_1")  # Should not raise


class TestRateLimiterDeny:
    """Tests that requests exceeding the limit are denied."""

    @pytest.mark.asyncio
    async def test_denies_request_exceeding_limit(self) -> None:
        limiter = ComposerRateLimiter(limit=2)
        await limiter.check("user_1")
        await limiter.check("user_1")
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check("user_1")
        assert exc_info.value.status_code == 429
        assert exc_info.value.headers is not None
        assert "Retry-After" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_429_response_body_shape(self) -> None:
        limiter = ComposerRateLimiter(limit=1)
        await limiter.check("user_1")
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check("user_1")
        detail: dict[str, Any] = exc_info.value.detail  # type: ignore[assignment]
        assert detail["error_type"] == "rate_limited"
        assert "retry_after" in detail
        assert isinstance(detail["retry_after"], int)


class TestRateLimiterWindowReset:
    """Tests that the sliding window resets correctly."""

    @pytest.mark.asyncio
    async def test_window_resets_after_60_seconds(self) -> None:
        limiter = ComposerRateLimiter(limit=1)
        # Manually inject an old timestamp to simulate window expiry
        limiter._buckets["user_1"] = [time.monotonic() - 61.0]
        # Should pass -- the old request is outside the window
        await limiter.check("user_1")


class TestRateLimiterConcurrentUsers:
    """Tests that per-user limits are independent."""

    @pytest.mark.asyncio
    async def test_independent_per_user_limits(self) -> None:
        limiter = ComposerRateLimiter(limit=1)
        await limiter.check("user_1")
        # user_2 should still be allowed -- separate bucket
        await limiter.check("user_2")

    @pytest.mark.asyncio
    async def test_user1_exhausted_user2_unaffected(self) -> None:
        limiter = ComposerRateLimiter(limit=1)
        await limiter.check("user_1")
        with pytest.raises(HTTPException):
            await limiter.check("user_1")
        # user_2 is not affected
        await limiter.check("user_2")


class TestRateLimiterPerUserLocks:
    """Tests that per-user locks prevent interleaving."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_user_serialized(self) -> None:
        """Concurrent requests from the same user are serialized by the
        per-user lock, preventing race conditions in the
        prune-check-append sequence."""
        limiter = ComposerRateLimiter(limit=3)
        # Fire 3 concurrent requests from same user
        results = await asyncio.gather(
            *[limiter.check("user_1") for _ in range(3)],
            return_exceptions=True,
        )
        # All 3 should succeed (within limit)
        assert all(r is None for r in results)

        # Now fire 2 more -- should both fail
        results = await asyncio.gather(
            *[limiter.check("user_1") for _ in range(2)],
            return_exceptions=True,
        )
        assert all(isinstance(r, HTTPException) for r in results)
