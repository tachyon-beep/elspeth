# tests/performance/stress/test_rate_limiter.py
"""Rate limiter stress tests under concurrent load.

Tests the RateLimiter from elspeth.core.rate_limit under realistic
concurrent access patterns to verify:
- Thread safety under parallel acquisition
- Recovery after request bursts
- Fair scheduling (no thread starvation)

These tests do NOT require ChaosLLM; they exercise the rate limiter directly.
"""

from __future__ import annotations

import threading
import time
from collections import Counter

import pytest

from elspeth.core.rate_limit import RateLimiter

pytestmark = pytest.mark.stress


@pytest.mark.stress
class TestRateLimiterStress:
    """Rate limiter under concurrent load."""

    def test_rate_limiter_concurrent_acquire(self) -> None:
        """Multiple threads acquiring rate limiter concurrently.

        Spawns 10 threads each trying to acquire 20 tokens from a limiter
        with 200 requests/minute (enough to serve all within the window).

        Verifies:
        - All 200 acquires succeed without exception
        - No deadlocks (test completes within timeout)
        - Thread safety (no duplicate grants or crashes)
        """
        rpm = 600  # High enough to accommodate all requests within test duration
        total_threads = 10
        acquires_per_thread = 20

        # Use a short window to make the test faster
        with RateLimiter("concurrent_test", requests_per_minute=rpm, window_ms=5000) as limiter:
            results: list[bool] = []
            errors: list[Exception] = []
            lock = threading.Lock()

            def worker() -> None:
                for _ in range(acquires_per_thread):
                    try:
                        limiter.acquire(timeout=30.0)
                        with lock:
                            results.append(True)
                    except Exception as e:
                        with lock:
                            errors.append(e)

            threads = [threading.Thread(target=worker, name=f"worker-{i}") for i in range(total_threads)]

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60.0)

            # All acquires should succeed
            assert len(errors) == 0, f"Unexpected errors: {errors}"
            assert len(results) == total_threads * acquires_per_thread, (
                f"Expected {total_threads * acquires_per_thread} acquires, got {len(results)}"
            )

    def test_rate_limiter_burst_recovery(self) -> None:
        """Rate limiter recovers after burst of requests.

        Sends a burst of requests that exceeds the rate limit, then waits
        for the window to reset and verifies the limiter accepts new requests.

        Verifies:
        - Burst correctly saturates the limiter
        - After window reset, new requests are accepted
        - try_acquire returns False when saturated
        """
        # Use a very short window (1 second) for fast test
        rpm = 10
        window_ms = 1000  # 1 second window

        with RateLimiter("burst_test", requests_per_minute=rpm, window_ms=window_ms) as limiter:
            # Phase 1: Burst - exhaust the limiter
            acquired_count = 0
            for _ in range(rpm + 5):
                if limiter.try_acquire():
                    acquired_count += 1

            # Should have acquired exactly `rpm` tokens
            assert acquired_count == rpm, f"Expected {rpm} successful acquires, got {acquired_count}"

            # Phase 2: Verify saturation - try_acquire should fail
            assert not limiter.try_acquire(), "Limiter should be saturated"

            # Phase 3: Wait for window to reset
            time.sleep(window_ms / 1000.0 + 0.2)  # Wait for window + buffer

            # Phase 4: Verify recovery - should be able to acquire again
            assert limiter.try_acquire(), "Limiter should accept requests after window reset"

    def test_rate_limiter_fairness_under_load(self) -> None:
        """No thread is starved under sustained load.

        Each thread acquires a fixed number of tokens using the blocking
        acquire() method, and we verify that all threads complete.

        Verifies:
        - Every thread successfully acquires its share
        - No thread is starved or deadlocked
        - All threads complete within timeout
        """
        num_threads = 5
        acquires_per_thread = 10
        # Use a high RPM with short window so all threads can acquire quickly
        rpm = 500
        window_ms = 2000  # 2 second window

        with RateLimiter("fairness_test", requests_per_minute=rpm, window_ms=window_ms) as limiter:
            thread_counts: Counter[int] = Counter()
            lock = threading.Lock()
            errors: list[Exception] = []

            def worker(thread_id: int) -> None:
                for _ in range(acquires_per_thread):
                    try:
                        limiter.acquire(timeout=30.0)
                        with lock:
                            thread_counts[thread_id] += 1
                    except Exception as e:
                        with lock:
                            errors.append(e)

            threads = [threading.Thread(target=worker, args=(i,), name=f"fair-worker-{i}") for i in range(num_threads)]

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60.0)

            # No errors
            assert len(errors) == 0, f"Unexpected errors: {errors}"

            # Every thread should have gotten all its acquires
            for tid in range(num_threads):
                assert thread_counts[tid] == acquires_per_thread, (
                    f"Thread {tid} got {thread_counts[tid]} acquires, expected {acquires_per_thread} (counts: {dict(thread_counts)})"
                )

            # Verify total
            total = sum(thread_counts.values())
            expected_total = num_threads * acquires_per_thread
            assert total == expected_total, f"Total: {total}, expected {expected_total}"
