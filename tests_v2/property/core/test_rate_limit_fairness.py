# tests_v2/property/core/test_rate_limit_fairness.py
"""Property-based tests for rate limiter fairness (no starvation).

These tests verify that ELSPETH's rate limiter does not starve any
particular requestor when multiple threads compete for tokens:

Fairness Properties:
- All competing threads eventually acquire at least one token
- No single thread monopolizes the limiter
- Distribution of successful acquires is roughly uniform across threads

Starvation Detection Properties:
- With sufficient capacity and time, no thread is permanently blocked
- Weighted acquires don't permanently starve lightweight requests

These properties are important for ELSPETH pipelines that make concurrent
external calls (e.g., LLM transforms with pooled threads) - every thread
must eventually make progress.
"""

from __future__ import annotations

import threading
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.core.rate_limit import RateLimiter

pytestmark = pytest.mark.slow

# =============================================================================
# Strategies for fairness testing
# =============================================================================

# Valid limiter names
fairness_names = st.text(
    min_size=1,
    max_size=10,
    alphabet="abcdefghijklmnopqrstuvwxyz",
)

# Number of competing threads
thread_counts = st.integers(min_value=2, max_value=6)

# Window size in ms (short for testing but long enough for fairness)
TEST_WINDOW_MS = 500
THREAD_POLL_SLEEP_SECONDS = 0.005


# =============================================================================
# Fairness Property Tests
# =============================================================================


class TestRateLimiterFairnessProperties:
    """Property tests for rate limiter fairness under contention."""

    @given(name=fairness_names, num_threads=thread_counts)
    @settings(max_examples=10, deadline=None)
    def test_no_thread_starved(self, name: str, num_threads: int) -> None:
        """Property: All competing threads acquire at least one token.

        With a rate limit high enough to serve all threads over a
        reasonable time window, no thread should be permanently starved.
        """
        # Rate high enough that each thread should get multiple
        # tokens across several windows
        rate = num_threads * 10
        acquires_per_thread: dict[int, int] = {}
        lock = threading.Lock()
        stop_event = threading.Event()

        def worker(thread_id: int, limiter: RateLimiter) -> None:
            count = 0
            while not stop_event.is_set():
                if limiter.try_acquire():
                    count += 1
                # Yield to other threads regardless of success/failure
                time.sleep(THREAD_POLL_SLEEP_SECONDS)
            with lock:
                acquires_per_thread[thread_id] = count

        with RateLimiter(name=name, requests_per_minute=rate, window_ms=TEST_WINDOW_MS) as limiter:
            threads = []
            for i in range(num_threads):
                t = threading.Thread(target=worker, args=(i, limiter))
                threads.append(t)

            for t in threads:
                t.start()

            # Let threads compete for 4 windows
            time.sleep(TEST_WINDOW_MS * 4 / 1000.0 + 0.2)
            stop_event.set()

            for t in threads:
                t.join(timeout=2.0)

        # Every thread should have acquired at least once
        for thread_id in range(num_threads):
            assert thread_id in acquires_per_thread, f"Thread {thread_id} never recorded any acquires"
            assert acquires_per_thread[thread_id] > 0, f"Thread {thread_id} was starved (0 acquires)"

    @given(name=fairness_names)
    @settings(max_examples=8, deadline=None)
    def test_no_thread_monopolizes(self, name: str) -> None:
        """Property: No single thread takes more than its fair share.

        With 3 threads and sufficient capacity, no single thread
        should take more than 80% of all tokens.
        """
        num_threads = 3
        rate = num_threads * 10  # Generous capacity
        acquires_per_thread: dict[int, int] = {}
        lock = threading.Lock()
        stop_event = threading.Event()

        def worker(thread_id: int, limiter: RateLimiter) -> None:
            count = 0
            while not stop_event.is_set():
                if limiter.try_acquire():
                    count += 1
                time.sleep(THREAD_POLL_SLEEP_SECONDS)  # Small delay to prevent spin
            with lock:
                acquires_per_thread[thread_id] = count

        with RateLimiter(name=name, requests_per_minute=rate, window_ms=TEST_WINDOW_MS) as limiter:
            threads = []
            for i in range(num_threads):
                t = threading.Thread(target=worker, args=(i, limiter))
                threads.append(t)

            for t in threads:
                t.start()

            # Let threads compete
            time.sleep(TEST_WINDOW_MS * 3 / 1000.0 + 0.2)
            stop_event.set()

            for t in threads:
                t.join(timeout=2.0)

        total = sum(acquires_per_thread.values())
        if total > 0:
            for thread_id, count in acquires_per_thread.items():
                share = count / total
                assert share < 0.80, (
                    f"Thread {thread_id} monopolized {share:.0%} of tokens ({count}/{total})"
                )

    @given(name=fairness_names)
    @settings(max_examples=8, deadline=None)
    def test_weighted_acquires_dont_starve_lightweight(self, name: str) -> None:
        """Property: Heavy-weight acquires don't permanently starve light ones.

        A thread requesting weight=1 should still make progress even when
        another thread requests weight=3.
        """
        rate = 10
        light_acquires = 0
        heavy_acquires = 0
        lock = threading.Lock()
        stop_event = threading.Event()

        def light_worker(limiter: RateLimiter) -> None:
            nonlocal light_acquires
            count = 0
            while not stop_event.is_set():
                if limiter.try_acquire(weight=1):
                    count += 1
                time.sleep(THREAD_POLL_SLEEP_SECONDS)
            with lock:
                light_acquires = count

        def heavy_worker(limiter: RateLimiter) -> None:
            nonlocal heavy_acquires
            count = 0
            while not stop_event.is_set():
                if limiter.try_acquire(weight=3):
                    count += 1
                time.sleep(THREAD_POLL_SLEEP_SECONDS)
            with lock:
                heavy_acquires = count

        with RateLimiter(name=name, requests_per_minute=rate, window_ms=TEST_WINDOW_MS) as limiter:
            t_light = threading.Thread(target=light_worker, args=(limiter,))
            t_heavy = threading.Thread(target=heavy_worker, args=(limiter,))

            t_light.start()
            t_heavy.start()

            # Let them compete for several windows
            time.sleep(TEST_WINDOW_MS * 4 / 1000.0 + 0.2)
            stop_event.set()

            t_light.join(timeout=2.0)
            t_heavy.join(timeout=2.0)

        # Light thread should have acquired at least once
        assert light_acquires > 0, "Light-weight thread was starved by heavy-weight thread"
