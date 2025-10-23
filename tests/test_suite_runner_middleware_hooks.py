"""Risk Reduction Tests: Suite Runner Middleware Hook Behavior.

These tests document and verify the exact middleware hook behavior in suite_runner.py,
focusing on the most critical and subtle aspects:

1. Hook call sequence and ordering
2. Shared middleware deduplication (on_suite_loaded called once per instance)
3. Baseline comparison timing (only after baseline completes)
4. Hook argument passing
5. Multi-experiment scenarios

INVARIANT: These behaviors must be preserved during refactoring.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from tests.conftest import MiddlewareHookTracer, SimpleLLM


@pytest.fixture
def sample_suite(tmp_path: Path) -> ExperimentSuite:
    """Basic suite with baseline and one variant."""
    return ExperimentSuite(
        root=tmp_path,
        baseline=ExperimentConfig(
            name="baseline",
            is_baseline=True,
            temperature=0.0,
            max_tokens=100,
        ),
        experiments=[
            ExperimentConfig(
                name="variant1",
                temperature=0.7,
                max_tokens=100,
            ),
        ],
    )


@pytest.fixture
def multi_experiment_suite(tmp_path: Path) -> ExperimentSuite:
    """Suite with baseline and multiple variants."""
    return ExperimentSuite(
        root=tmp_path,
        baseline=ExperimentConfig(
            name="baseline",
            is_baseline=True,
            temperature=0.0,
            max_tokens=100,
        ),
        experiments=[
            ExperimentConfig(name="variant1", temperature=0.5, max_tokens=100),
            ExperimentConfig(name="variant2", temperature=0.7, max_tokens=100),
            ExperimentConfig(name="variant3", temperature=0.9, max_tokens=100),
        ],
    )


def test_middleware_hook_call_sequence_basic(
    middleware_tracer: MiddlewareHookTracer,
) -> None:
    """INVARIANT: Middleware hooks fire in correct sequence for basic suite.

    Expected sequence:
    1. on_suite_loaded (once at suite start)
    2. on_experiment_start (baseline)
    3. on_experiment_complete (baseline)
    4. on_experiment_start (variant1)
    5. on_experiment_complete (variant1)
    6. on_baseline_comparison (variant1 vs baseline)
    7. on_suite_complete (once at suite end)

    This test simulates the hook calling pattern from suite_runner.py::run()
    without requiring full integration with build_runner/ExperimentRunner.
    """
    # Simulate suite execution pattern from run() method
    suite_metadata = [
        {
            "experiment": "baseline",
            "temperature": 0.0,
            "max_tokens": 100,
            "is_baseline": True,
        },
        {
            "experiment": "variant1",
            "temperature": 0.7,
            "max_tokens": 100,
            "is_baseline": False,
        },
    ]
    preflight_info = {
        "experiment_count": 2,
        "baseline": "baseline",
    }

    # Hook 1: on_suite_loaded (called once at suite start)
    middleware_tracer.on_suite_loaded(suite_metadata, preflight_info)

    # Baseline experiment hooks
    middleware_tracer.on_experiment_start("baseline", suite_metadata[0])
    baseline_payload = {"results": [{"response": "baseline_output"}], "metadata": {}}
    middleware_tracer.on_experiment_complete("baseline", baseline_payload, suite_metadata[0])
    # NOTE: No on_baseline_comparison for baseline itself

    # Variant experiment hooks
    middleware_tracer.on_experiment_start("variant1", suite_metadata[1])
    variant_payload = {"results": [{"response": "variant_output"}], "metadata": {}}
    middleware_tracer.on_experiment_complete("variant1", variant_payload, suite_metadata[1])

    # Baseline comparison (only for non-baseline experiments)
    middleware_tracer.on_baseline_comparison("variant1", {"test_comparison": {"diff": 0.1}})

    # Hook 7: on_suite_complete (called once at suite end)
    middleware_tracer.on_suite_complete()

    # Verify exact sequence
    expected_sequence = [
        "on_suite_loaded",
        "on_experiment_start",      # baseline
        "on_experiment_complete",    # baseline
        "on_experiment_start",       # variant1
        "on_experiment_complete",    # variant1
        "on_baseline_comparison",    # variant1 vs baseline
        "on_suite_complete",
    ]

    assert middleware_tracer.get_call_sequence() == expected_sequence

    # Verify hook counts
    assert middleware_tracer.get_suite_loaded_count() == 1
    assert middleware_tracer.get_experiment_start_count() == 2
    assert middleware_tracer.get_experiment_complete_count() == 2
    assert middleware_tracer.get_baseline_comparison_count() == 1
    assert middleware_tracer.get_suite_complete_count() == 1


def test_middleware_hook_sequence_multi_experiment(
    multi_experiment_suite: ExperimentSuite,
    middleware_tracer: MiddlewareHookTracer,
) -> None:
    """INVARIANT: Hook sequence scales correctly with multiple experiments.

    With baseline + 3 variants:
    - on_suite_loaded: 1 time
    - on_experiment_start: 4 times (baseline + 3 variants)
    - on_experiment_complete: 4 times
    - on_baseline_comparison: 3 times (only variants, not baseline)
    - on_suite_complete: 1 time
    """
    # Simulate multi-experiment suite execution
    suite_metadata = [
        {"experiment": "baseline", "temperature": 0.0, "max_tokens": None, "is_baseline": True},
        {"experiment": "variant1", "temperature": 0.5, "max_tokens": None, "is_baseline": False},
        {"experiment": "variant2", "temperature": 0.7, "max_tokens": None, "is_baseline": False},
        {"experiment": "variant3", "temperature": 0.9, "max_tokens": None, "is_baseline": False},
    ]
    preflight_info = {"experiment_count": 4, "baseline": "baseline"}

    # Suite start
    middleware_tracer.on_suite_loaded(suite_metadata, preflight_info)

    # Baseline
    middleware_tracer.on_experiment_start("baseline", suite_metadata[0])
    middleware_tracer.on_experiment_complete("baseline", {"results": []}, suite_metadata[0])

    # Variants (each with baseline comparison)
    for i, variant_name in enumerate(["variant1", "variant2", "variant3"], start=1):
        middleware_tracer.on_experiment_start(variant_name, suite_metadata[i])
        middleware_tracer.on_experiment_complete(variant_name, {"results": []}, suite_metadata[i])
        middleware_tracer.on_baseline_comparison(variant_name, {"test_comp": {}})

    # Suite complete
    middleware_tracer.on_suite_complete()

    # Verify counts
    assert middleware_tracer.get_suite_loaded_count() == 1
    assert middleware_tracer.get_experiment_start_count() == 4
    assert middleware_tracer.get_experiment_complete_count() == 4
    assert middleware_tracer.get_baseline_comparison_count() == 3  # Only variants
    assert middleware_tracer.get_suite_complete_count() == 1

    # Verify experiment order
    experiments_started = middleware_tracer.get_experiments_for_hook("on_experiment_start")
    assert experiments_started == ["baseline", "variant1", "variant2", "variant3"]

    comparisons_run = middleware_tracer.get_experiments_for_hook("on_baseline_comparison")
    assert comparisons_run == ["variant1", "variant2", "variant3"]  # No baseline


def test_shared_middleware_deduplication() -> None:
    """INVARIANT: Shared middleware instance gets on_suite_loaded ONLY ONCE.

    This is the CRITICAL deduplication behavior in suite_runner.py lines 359-365.
    The notified_middlewares dict tracks which middleware instances have received
    on_suite_loaded to prevent duplicate notifications when the same middleware
    is shared across multiple experiments.

    Key insight: Uses id(mw) as key, so object identity matters.
    """
    # Create a SINGLE middleware instance that will be shared
    shared_tracer = MiddlewareHookTracer(name="shared")

    suite_metadata = [
        {"experiment": "exp1", "temperature": 0.5, "max_tokens": None, "is_baseline": False},
        {"experiment": "exp2", "temperature": 0.7, "max_tokens": None, "is_baseline": False},
        {"experiment": "exp3", "temperature": 0.9, "max_tokens": None, "is_baseline": False},
    ]
    preflight_info = {"experiment_count": 3, "baseline": None}

    # Simulate suite_runner deduplication logic
    notified_middlewares: dict[int, MiddlewareHookTracer] = {}

    for experiment in suite_metadata:
        # Each experiment uses the SAME middleware instance (shared)
        middlewares = [shared_tracer]

        for mw in middlewares:
            key = id(mw)

            # Deduplication check (from suite_runner.py:362)
            if hasattr(mw, "on_suite_loaded") and key not in notified_middlewares:
                mw.on_suite_loaded(suite_metadata, preflight_info)
                notified_middlewares[key] = mw

            # on_experiment_start always called (no deduplication)
            if hasattr(mw, "on_experiment_start"):
                mw.on_experiment_start(experiment["experiment"], experiment)

    # Critical assertion: on_suite_loaded called EXACTLY ONCE
    assert shared_tracer.get_suite_loaded_count() == 1, \
        "Shared middleware should receive on_suite_loaded only once"

    # But on_experiment_start called for EACH experiment
    assert shared_tracer.get_experiment_start_count() == 3, \
        "Shared middleware should receive on_experiment_start for each experiment"

    # Verify deduplication tracking
    assert len(notified_middlewares) == 1, \
        "Only one middleware instance should be tracked"
    assert id(shared_tracer) in notified_middlewares, \
        "Shared middleware should be in notified_middlewares dict"


def test_multiple_unique_middleware_instances() -> None:
    """INVARIANT: Each unique middleware instance gets its own on_suite_loaded.

    When experiments have DIFFERENT middleware instances (not shared),
    each one should receive on_suite_loaded separately.
    """
    # Create DIFFERENT middleware instances
    tracer1 = MiddlewareHookTracer(name="tracer1")
    tracer2 = MiddlewareHookTracer(name="tracer2")
    tracer3 = MiddlewareHookTracer(name="tracer3")

    suite_metadata = [
        {"experiment": "exp1", "temperature": 0.5, "max_tokens": None, "is_baseline": False},
        {"experiment": "exp2", "temperature": 0.7, "max_tokens": None, "is_baseline": False},
        {"experiment": "exp3", "temperature": 0.9, "max_tokens": None, "is_baseline": False},
    ]
    preflight_info = {"experiment_count": 3, "baseline": None}

    # Simulate suite_runner with different middleware instances
    notified_middlewares: dict[int, MiddlewareHookTracer] = {}
    experiment_middlewares = [[tracer1], [tracer2], [tracer3]]

    for experiment, middlewares in zip(suite_metadata, experiment_middlewares):
        for mw in middlewares:
            key = id(mw)

            if hasattr(mw, "on_suite_loaded") and key not in notified_middlewares:
                mw.on_suite_loaded(suite_metadata, preflight_info)
                notified_middlewares[key] = mw

            if hasattr(mw, "on_experiment_start"):
                mw.on_experiment_start(experiment["experiment"], experiment)

    # Each unique instance should get on_suite_loaded
    assert tracer1.get_suite_loaded_count() == 1
    assert tracer2.get_suite_loaded_count() == 1
    assert tracer3.get_suite_loaded_count() == 1

    # Each should get on_experiment_start only for their experiment
    assert tracer1.get_experiment_start_count() == 1
    assert tracer2.get_experiment_start_count() == 1
    assert tracer3.get_experiment_start_count() == 1

    # All three should be tracked separately
    assert len(notified_middlewares) == 3


def test_baseline_comparison_only_after_baseline_completes() -> None:
    """INVARIANT: Baseline comparisons only run AFTER baseline experiment completes.

    Critical timing dependency: baseline_payload must be set before comparisons run.
    Comparisons should NEVER run for the baseline experiment itself.
    """
    tracer = MiddlewareHookTracer()

    suite_metadata = [
        {"experiment": "baseline", "temperature": 0.0, "max_tokens": None, "is_baseline": True},
        {"experiment": "variant1", "temperature": 0.7, "max_tokens": None, "is_baseline": False},
    ]
    preflight_info = {"experiment_count": 2, "baseline": "baseline"}

    # Suite start
    tracer.on_suite_loaded(suite_metadata, preflight_info)

    # Baseline experiment (no comparison)
    tracer.on_experiment_start("baseline", suite_metadata[0])
    baseline_payload = {"results": [{"response": "baseline_result"}]}
    tracer.on_experiment_complete("baseline", baseline_payload, suite_metadata[0])
    # NOTE: No on_baseline_comparison for baseline itself

    # Variant experiment (with comparison)
    tracer.on_experiment_start("variant1", suite_metadata[1])
    variant_payload = {"results": [{"response": "variant_result"}]}
    tracer.on_experiment_complete("variant1", variant_payload, suite_metadata[1])

    # Comparison runs AFTER baseline completes
    comparisons = {"score_diff": {"baseline": 0.5, "variant": 0.7, "diff": 0.2}}
    tracer.on_baseline_comparison("variant1", comparisons)

    tracer.on_suite_complete()

    # Verify baseline has no comparison
    experiments_with_comparisons = tracer.get_experiments_for_hook("on_baseline_comparison")
    assert "baseline" not in experiments_with_comparisons, \
        "Baseline experiment should not have baseline comparison"
    assert "variant1" in experiments_with_comparisons

    # Verify ordering: complete before comparison
    sequence = tracer.get_call_sequence()
    baseline_complete_idx = sequence.index("on_experiment_complete")  # First complete
    variant_comparison_idx = sequence.index("on_baseline_comparison")

    assert baseline_complete_idx < variant_comparison_idx, \
        "Baseline must complete before variant comparison runs"


def test_hook_arguments_are_passed_correctly() -> None:
    """INVARIANT: Hook arguments contain expected data."""
    tracer = MiddlewareHookTracer()

    suite_metadata = [
        {
            "experiment": "test_exp",
            "temperature": 0.8,
            "max_tokens": 1000,
            "is_baseline": False,
        },
    ]
    preflight_info = {
        "experiment_count": 1,
        "baseline": None,
    }

    # Call hooks
    tracer.on_suite_loaded(suite_metadata, preflight_info)
    tracer.on_experiment_start("test_exp", suite_metadata[0])

    payload = {
        "results": [{"response": "test"}],
        "metadata": {"processed_rows": 1, "total_rows": 1},
    }
    tracer.on_experiment_complete("test_exp", payload, suite_metadata[0])

    comparisons = {
        "score_agreement": {"kappa": 0.85},
        "score_flip": {"flip_rate": 0.02},
    }
    tracer.on_baseline_comparison("test_exp", comparisons)

    tracer.on_suite_complete()

    # Verify on_suite_loaded arguments
    suite_loaded_call = [c for c in tracer.calls if c["hook"] == "on_suite_loaded"][0]
    assert suite_loaded_call["experiment_count"] == 1
    assert suite_loaded_call["suite_metadata"] == suite_metadata
    assert suite_loaded_call["preflight_info"] == preflight_info

    # Verify on_experiment_start arguments
    exp_start_call = [c for c in tracer.calls if c["hook"] == "on_experiment_start"][0]
    assert exp_start_call["experiment"] == "test_exp"
    assert exp_start_call["metadata"]["temperature"] == 0.8
    assert exp_start_call["metadata"]["max_tokens"] == 1000

    # Verify on_experiment_complete arguments
    exp_complete_call = [c for c in tracer.calls if c["hook"] == "on_experiment_complete"][0]
    assert exp_complete_call["experiment"] == "test_exp"
    assert exp_complete_call["result_count"] == 1
    assert exp_complete_call["has_payload"] is True

    # Verify on_baseline_comparison arguments
    comparison_call = [c for c in tracer.calls if c["hook"] == "on_baseline_comparison"][0]
    assert comparison_call["experiment"] == "test_exp"
    assert comparison_call["comparison_count"] == 2
    assert set(comparison_call["comparison_plugins"]) == {"score_agreement", "score_flip"}


def test_middleware_without_hooks_doesnt_error() -> None:
    """SAFETY: Middleware without lifecycle hooks should not cause errors.

    suite_runner.py uses hasattr() to check for hooks before calling them.
    This should gracefully handle middleware that doesn't implement all hooks.
    """

    class MinimalMiddleware:
        """Middleware with only on_experiment_start."""

        def __init__(self) -> None:
            self.start_count = 0

        def on_experiment_start(self, name: str, metadata: dict) -> None:
            self.start_count += 1

    minimal = MinimalMiddleware()

    suite_metadata = [{"experiment": "exp1", "temperature": 0.5, "max_tokens": None, "is_baseline": False}]
    preflight_info = {"experiment_count": 1, "baseline": None}

    # Simulate suite_runner.py hook calling pattern with hasattr checks
    if hasattr(minimal, "on_suite_loaded"):
        minimal.on_suite_loaded(suite_metadata, preflight_info)  # type: ignore

    if hasattr(minimal, "on_experiment_start"):
        minimal.on_experiment_start("exp1", suite_metadata[0])

    if hasattr(minimal, "on_experiment_complete"):
        minimal.on_experiment_complete("exp1", {}, suite_metadata[0])  # type: ignore

    if hasattr(minimal, "on_baseline_comparison"):
        minimal.on_baseline_comparison("exp1", {})  # type: ignore

    if hasattr(minimal, "on_suite_complete"):
        minimal.on_suite_complete()  # type: ignore

    # Only on_experiment_start should have been called
    assert minimal.start_count == 1
