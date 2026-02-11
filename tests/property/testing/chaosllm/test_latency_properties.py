# tests/property/testing/chaosllm/test_latency_properties.py
"""Property-based tests for ChaosLLM LatencySimulator.

Tests the invariants of latency simulation:
- Simulated delay is always non-negative (clamped to 0)
- Delay is within expected bounds (base ± jitter) / 1000
- Deterministic with seeded RNG
- slow_response delay within [min, max] range
"""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.testing.chaosengine.latency import LatencySimulator
from elspeth.testing.chaosengine.types import LatencyConfig

# =============================================================================
# Non-Negativity
# =============================================================================


class TestNonNegativity:
    """Simulated latency must never be negative."""

    @given(
        base_ms=st.integers(min_value=0, max_value=500),
        jitter_ms=st.integers(min_value=0, max_value=500),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=200)
    def test_simulate_always_non_negative(self, base_ms: int, jitter_ms: int, seed: int) -> None:
        """Property: simulate() >= 0 for all base/jitter combinations.

        Even when jitter > base (e.g., base=10, jitter=100), the result
        is clamped to 0 via max(0, base + jitter).
        """
        config = LatencyConfig(base_ms=base_ms, jitter_ms=jitter_ms)
        rng = random.Random(seed)
        sim = LatencySimulator(config, rng=rng)

        for _ in range(50):
            delay = sim.simulate()
            assert delay >= 0.0, f"Negative delay: {delay} (base={base_ms}, jitter={jitter_ms})"


# =============================================================================
# Bounds
# =============================================================================


class TestBounds:
    """Simulated delay must be within expected bounds."""

    @given(
        base_ms=st.integers(min_value=10, max_value=500),
        jitter_ms=st.integers(min_value=0, max_value=200),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=200)
    def test_simulate_within_bounds(self, base_ms: int, jitter_ms: int, seed: int) -> None:
        """Property: delay is in [max(0, base-jitter), base+jitter] / 1000."""
        config = LatencyConfig(base_ms=base_ms, jitter_ms=jitter_ms)
        rng = random.Random(seed)
        sim = LatencySimulator(config, rng=rng)

        lower = max(0.0, (base_ms - jitter_ms)) / 1000.0
        upper = (base_ms + jitter_ms) / 1000.0

        for _ in range(50):
            delay = sim.simulate()
            assert lower - 1e-9 <= delay <= upper + 1e-9, f"Delay {delay:.6f}s outside bounds [{lower:.6f}, {upper:.6f}]"

    @given(
        min_sec=st.integers(min_value=1, max_value=10),
        max_sec=st.integers(min_value=10, max_value=60),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=100)
    def test_slow_response_within_range(self, min_sec: int, max_sec: int, seed: int) -> None:
        """Property: slow_response delay is in [min_sec, max_sec]."""
        config = LatencyConfig()
        rng = random.Random(seed)
        sim = LatencySimulator(config, rng=rng)

        for _ in range(50):
            delay = sim.simulate_slow_response(min_sec, max_sec)
            assert min_sec <= delay <= max_sec, f"Slow response delay {delay:.3f} outside [{min_sec}, {max_sec}]"


# =============================================================================
# Determinism
# =============================================================================


class TestDeterminism:
    """Same seed must produce identical delay sequence."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_same_seed_same_delays(self, seed: int) -> None:
        """Property: Same seed → identical simulate() sequence."""
        config = LatencyConfig(base_ms=100, jitter_ms=50)

        rng1 = random.Random(seed)
        sim1 = LatencySimulator(config, rng=rng1)

        rng2 = random.Random(seed)
        sim2 = LatencySimulator(config, rng=rng2)

        for i in range(100):
            d1 = sim1.simulate()
            d2 = sim2.simulate()
            assert d1 == d2, f"Diverged at iteration {i}: {d1} != {d2}"


# =============================================================================
# Statistical Properties
# =============================================================================


class TestStatisticalProperties:
    """Statistical properties of the latency distribution."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_mean_converges_to_base(self, seed: int) -> None:
        """Property: Mean delay converges to base_ms/1000 over many samples.

        Since jitter is uniform(-j, +j), the expected value is base_ms/1000.
        """
        base_ms = 100
        jitter_ms = 30
        config = LatencyConfig(base_ms=base_ms, jitter_ms=jitter_ms)
        rng = random.Random(seed)
        sim = LatencySimulator(config, rng=rng)

        n = 5000
        total = sum(sim.simulate() for _ in range(n))
        mean = total / n
        expected = base_ms / 1000.0

        # Allow ±10% tolerance
        assert abs(mean - expected) < expected * 0.10, f"Mean {mean:.6f} too far from expected {expected:.6f}"

    def test_zero_base_zero_jitter_returns_zero(self) -> None:
        """Edge case: base=0, jitter=0 always returns 0."""
        config = LatencyConfig(base_ms=0, jitter_ms=0)
        sim = LatencySimulator(config)

        for _ in range(100):
            assert sim.simulate() == 0.0
