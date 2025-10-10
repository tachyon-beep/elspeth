import threading
import time

import pytest

from elspeth.core.controls.rate_limit import FixedWindowRateLimiter, NoopRateLimiter, AdaptiveRateLimiter
from elspeth.core.controls.cost_tracker import FixedPriceCostTracker


def test_fixed_window_rate_limiter(monkeypatch):
    limiter = FixedWindowRateLimiter(requests=2, per_seconds=1.0)
    times = [0.0, 0.0, 0.0, 1.0]

    def fake_time():
        return times.pop(0)

    sleep_calls = []

    def fake_sleep(duration):
        sleep_calls.append(duration)
        times[0] += duration

    monkeypatch.setattr("elspeth.core.controls.rate_limit.time.time", fake_time)
    monkeypatch.setattr("elspeth.core.controls.rate_limit.time.sleep", fake_sleep)

    with limiter.acquire():
        pass
    with limiter.acquire():
        pass
    with limiter.acquire():
        pass

    assert sleep_calls  # should have slept before third request


def test_fixed_price_cost_tracker_dict_usage():
    tracker = FixedPriceCostTracker(prompt_token_price=0.01, completion_token_price=0.02)
    response = {
        "raw": {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
            }
        }
    }
    metrics = tracker.record(response)
    assert metrics["cost"] == pytest.approx(10 * 0.01 + 5 * 0.02)
    summary = tracker.summary()
    assert summary["prompt_tokens"] == 10
    assert summary["completion_tokens"] == 5


def test_adaptive_rate_limiter(monkeypatch):
    limiter = AdaptiveRateLimiter(requests_per_minute=2, tokens_per_minute=100, interval_seconds=0.2)
    with limiter.acquire({"estimated_tokens": 10}):
        pass
    with limiter.acquire({"estimated_tokens": 10}):
        pass
    start = time.perf_counter()
    with limiter.acquire({"estimated_tokens": 10}):
        pass
    elapsed = time.perf_counter() - start
    assert elapsed >= 0.05
    limiter.update_usage({"metrics": {"prompt_tokens": 30, "completion_tokens": 20}}, {})
    assert limiter.utilization() > 0


def test_adaptive_rate_limiter_thread_safety():
    limiter = AdaptiveRateLimiter(requests_per_minute=100, tokens_per_minute=1000, interval_seconds=1.0)

    def worker():
        for _ in range(5):
            with limiter.acquire({"estimated_tokens": 1}):
                pass
            limiter.update_usage({"metrics": {"prompt_tokens": 1, "completion_tokens": 1}}, {})

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    util = limiter.utilization()
    assert 0.0 <= util <= 1.0
