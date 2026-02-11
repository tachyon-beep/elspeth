# tests/property/testing/chaosengine/test_injection_engine_properties.py
"""Property-based tests for InjectionEngine.

Tests probabilistic invariants:
- Error rate convergence (priority and weighted modes)
- Burst timing periodicity
- Deterministic replay with seeded RNG
- Selection mode distribution fairness
"""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.testing.chaosengine.injection_engine import InjectionEngine
from elspeth.testing.chaosengine.types import BurstConfig, ErrorSpec

# =============================================================================
# Error Rate Convergence
# =============================================================================


class TestErrorRateConvergence:
    """Property: Observed error rates converge to configured percentages."""

    @given(
        rate=st.floats(min_value=5.0, max_value=95.0, allow_nan=False, allow_infinity=False),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=50)
    def test_priority_single_spec_converges(self, rate: float, seed: int) -> None:
        """Single spec in priority mode converges to its weight."""
        engine = InjectionEngine(selection_mode="priority", rng=random.Random(seed))
        specs = [ErrorSpec("test", rate)]
        n = 2000
        fired = sum(1 for _ in range(n) if engine.select(specs) is not None)
        observed = (fired / n) * 100
        assert abs(observed - rate) < 5.0, f"Expected ~{rate:.1f}%, observed {observed:.1f}% (seed={seed})"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_zero_weight_never_fires(self, seed: int) -> None:
        """0% weight never produces a selection."""
        engine = InjectionEngine(rng=random.Random(seed))
        specs = [ErrorSpec("zero", 0.0)]
        for _ in range(500):
            assert engine.select(specs) is None

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_100_weight_always_fires(self, seed: int) -> None:
        """100% weight always fires in priority mode."""
        engine = InjectionEngine(selection_mode="priority", rng=random.Random(seed))
        specs = [ErrorSpec("always", 100.0)]
        for _ in range(200):
            result = engine.select(specs)
            assert result is not None


# =============================================================================
# Weighted Mode Distribution
# =============================================================================


class TestWeightedDistribution:
    """Property: Weighted mode distributes proportionally."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_equal_weights_produce_both(self, seed: int) -> None:
        """Equal-weight specs both appear over many trials."""
        engine = InjectionEngine(selection_mode="weighted", rng=random.Random(seed))
        specs = [ErrorSpec("a", 40.0), ErrorSpec("b", 40.0)]
        seen: set[str] = set()
        for _ in range(500):
            result = engine.select(specs)
            if result is not None:
                seen.add(result.tag)
        assert "a" in seen and "b" in seen

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_weighted_100_never_returns_none(self, seed: int) -> None:
        """Total weight of 100% never returns None."""
        engine = InjectionEngine(selection_mode="weighted", rng=random.Random(seed))
        specs = [ErrorSpec("a", 50.0), ErrorSpec("b", 50.0)]
        for _ in range(200):
            assert engine.select(specs) is not None


# =============================================================================
# Burst Timing Periodicity
# =============================================================================


class TestBurstPeriodicity:
    """Property: Burst windows repeat at correct intervals."""

    @given(
        interval=st.integers(min_value=10, max_value=120),
        duration=st.integers(min_value=1, max_value=9),
    )
    @settings(max_examples=50)
    def test_burst_periodic_in_out(self, interval: int, duration: int) -> None:
        """Burst is active within duration, inactive after."""
        effective_duration = min(duration, interval - 1)
        engine = InjectionEngine(
            burst_config=BurstConfig(
                enabled=True,
                interval_sec=interval,
                duration_sec=effective_duration,
            ),
        )
        # In burst at start of interval
        assert engine._check_burst(0.5)
        # Out of burst after duration
        assert not engine._check_burst(effective_duration + 0.5)
        # In burst at next interval
        assert engine._check_burst(float(interval) + 0.5)
        # Out of burst after next duration
        assert not engine._check_burst(float(interval) + effective_duration + 0.5)


# =============================================================================
# Deterministic Replay
# =============================================================================


class TestDeterministicReplay:
    """Property: Same seed produces identical selection sequences."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_same_seed_same_sequence(self, seed: int) -> None:
        """Two engines with same seed produce identical selections."""
        specs = [
            ErrorSpec("a", 30.0),
            ErrorSpec("b", 20.0),
            ErrorSpec("c", 10.0),
        ]
        engine1 = InjectionEngine(rng=random.Random(seed))
        engine2 = InjectionEngine(rng=random.Random(seed))
        for i in range(200):
            r1 = engine1.select(specs)
            r2 = engine2.select(specs)
            t1 = r1.tag if r1 is not None else None
            t2 = r2.tag if r2 is not None else None
            assert t1 == t2, f"Diverged at step {i}: {t1} != {t2} (seed={seed})"
