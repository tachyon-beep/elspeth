"""In-memory sliding window rate limiter for composer messages.

Per-user rate limiting via FastAPI Depends(). Not thread-safe across
multiple uvicorn workers -- each worker has its own counter. Multi-worker
deployments need Redis or equivalent shared store for accurate
cross-process rate limiting.

Layer: L3 (application).
"""

from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException, Request


class ComposerRateLimiter:
    """In-memory sliding window rate limiter for composer messages.

    Tracks message timestamps per user_id. On each request, prunes
    timestamps older than 60 seconds, then checks count against limit.
    Returns 429 if exceeded.

    Uses per-user asyncio.Lock instances to avoid contention between
    unrelated users. asyncio.Lock guards coroutine suspension points
    (e.g., between the prune-check-append sequence where another
    coroutine could interleave), not thread safety. A top-level
    _locks_lock (held for microseconds -- dict lookup only) serializes
    creation/fetch of per-user locks.

    Rate limiting is per-process. Deployments with multiple uvicorn
    workers have an effective rate limit of N * limit across the
    cluster. Multi-worker deployments require Redis or an equivalent
    shared store for accurate cross-process rate limiting.
    """

    _WINDOW_SECONDS: float = 60.0

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._buckets: dict[str, list[float]] = {}
        self._user_locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

    async def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """Get or create a lock for the given user."""
        async with self._locks_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            return self._user_locks[user_id]

    async def check(self, user_id: str) -> None:
        """Check rate limit for the given user.

        Raises HTTPException(429) with Retry-After header if the
        per-user rate limit is exceeded.
        """
        lock = await self._get_user_lock(user_id)
        async with lock:
            now = time.monotonic()
            cutoff = now - self._WINDOW_SECONDS

            # Get or create bucket
            if user_id not in self._buckets:
                self._buckets[user_id] = []

            bucket = self._buckets[user_id]

            # Prune timestamps outside the window
            bucket[:] = [ts for ts in bucket if ts > cutoff]

            # Check limit
            if len(bucket) >= self._limit:
                # Earliest timestamp determines retry delay
                earliest = bucket[0]
                retry_after = int(earliest - cutoff) + 1
                if retry_after < 1:
                    retry_after = 1
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error_type": "rate_limited",
                        "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            # Record this request
            bucket.append(now)


async def get_rate_limiter(request: Request) -> ComposerRateLimiter:
    """FastAPI dependency that extracts the rate limiter from app state."""
    limiter: ComposerRateLimiter = request.app.state.rate_limiter
    return limiter
