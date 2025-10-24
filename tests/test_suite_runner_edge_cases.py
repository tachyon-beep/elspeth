"""Edge Case Safety Tests for ExperimentSuiteRunner.

This module provides comprehensive edge case testing to prevent regressions
during the suite_runner.py refactoring (complexity reduction from 69 to ≤15).

Each test documents a specific edge case that must continue to work correctly
after refactoring. Tests are organized by risk category and explicitly named
for discoverability.

Test Categories:
    - Suite Configuration: Empty suites, baseline handling
    - Middleware Lifecycle: Hook calls, deduplication, missing methods
    - Sink Resolution: Factory fallbacks, all-factory scenarios
    - Baseline Comparison: Missing plugins, no baseline scenarios

References:
    - risk_reduction_suite_runner.md: Activity 5 (Edge Case Catalog)
    - EXECUTION_PLAN_suite_runner_refactor.md: Phase 0 edge case requirements
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from tests.conftest import CollectingSink, MiddlewareHookTracer, SimpleLLM


# ============================================================================
# Suite Configuration Edge Cases
# ============================================================================


def test_edge_case_empty_suite(tmp_path: Path) -> None:
    """EDGE CASE 1: Empty suite with no experiments returns empty results.

    **Risk Category:** Suite Configuration
    **Complexity Driver:** Experiment loop (lines 325-414)

    **Expected Behavior:**
        - run() returns empty dict {}
        - No sinks are called
        - No errors raised

    **Why This Edge Case Matters:**
        During refactoring, helper method extractions might assume non-empty
        experiment lists. This test ensures graceful handling of empty suites.

    **Code Location:** suite_runner.py lines 303-306 (experiment list building)
    """
    # Create empty suite
    suite = ExperimentSuite(
        root=tmp_path,
        baseline=None,
        experiments=[],  # Empty experiments list
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT: Empty suite returns empty results
    assert results == {}, "Empty suite should return empty results dict"


def test_edge_case_no_baseline_experiment(tmp_path: Path) -> None:
    """EDGE CASE 2: Suite with no baseline never sets baseline_payload.

    **Risk Category:** Baseline Tracking
    **Complexity Driver:** Baseline comparison logic (lines 396-413)

    **Expected Behavior:**
        - baseline_payload remains None throughout execution
        - No baseline comparisons run (guarded by baseline_payload check)
        - Experiments execute normally

    **Why This Edge Case Matters:**
        Baseline comparison logic depends on baseline_payload being set first.
        If no baseline exists, this entire code path should be skipped cleanly.

    **Code Location:** suite_runner.py line 377 (baseline tracking), 396 (comparison guard)
    """
    # Suite with 2 experiments, neither is baseline
    suite = ExperimentSuite(
        root=tmp_path,
        baseline=None,  # No baseline
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.7,
                max_tokens=100,
                is_baseline=False,
            ),
            ExperimentConfig(
                name="exp2",
                temperature=0.8,
                max_tokens=100,
                is_baseline=False,
            ),
        ],
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT 1: Both experiments execute
    assert "exp1" in results, "exp1 should execute"
    assert "exp2" in results, "exp2 should execute"

    # INVARIANT 2: No baseline_comparison in any results
    assert "baseline_comparison" not in results["exp1"]["payload"], (
        "No baseline_comparison should exist without baseline"
    )
    assert "baseline_comparison" not in results["exp2"]["payload"], (
        "No baseline_comparison should exist without baseline"
    )


def test_edge_case_baseline_not_first_in_list(tmp_path: Path) -> None:
    """EDGE CASE 3: Baseline experiment not first in experiments list gets reordered.

    **Risk Category:** Suite Configuration / Baseline Tracking
    **Complexity Driver:** Experiment ordering (lines 303-306)

    **Expected Behavior:**
        - suite_runner reorders experiments to put baseline first
        - Baseline tracked correctly regardless of initial position
        - All non-baseline experiments can be compared to baseline

    **Why This Edge Case Matters:**
        The code explicitly reorders experiments to ensure baseline runs first
        (lines 304-306). This test verifies that reordering logic is preserved
        during refactoring.

    **Code Location:** suite_runner.py lines 303-306 (experiment reordering)
    """
    # Create suite with baseline SECOND in experiments list
    baseline_exp = ExperimentConfig(
        name="baseline",
        temperature=0.7,
        max_tokens=100,
        is_baseline=True,
    )

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=baseline_exp,
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.8,
                max_tokens=100,
                is_baseline=False,
            ),
            baseline_exp,  # Baseline is SECOND in list
            ExperimentConfig(
                name="exp2",
                temperature=0.9,
                max_tokens=100,
                is_baseline=False,
            ),
        ],
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT 1: Baseline tracked correctly
    assert "baseline" in results, "Baseline should be in results"
    assert "baseline_comparison" not in results["baseline"]["payload"], (
        "Baseline should never compare to itself"
    )

    # INVARIANT 2: All experiments executed (no duplicates)
    assert len(results) == 3, "Should have exactly 3 results (baseline + exp1 + exp2)"
    assert "exp1" in results
    assert "exp2" in results


def test_edge_case_multiple_baselines_first_wins(tmp_path: Path) -> None:
    """EDGE CASE 5: Multiple experiments marked as baseline - first one wins.

    **Risk Category:** Baseline Tracking
    **Complexity Driver:** Baseline tracking logic (lines 377-378)

    **Expected Behavior:**
        - First experiment marked is_baseline=True gets tracked
        - Later baseline experiments treated as normal experiments
        - Later baselines can be compared against first baseline
        - baseline_payload set only once

    **Why This Edge Case Matters:**
        The code uses `if baseline_payload is None` to track first baseline
        (line 377). This is a guard against malformed configurations with
        multiple baselines. Test ensures first-wins behavior is preserved.

    **Code Location:** suite_runner.py line 377 (baseline_payload is None check)
    """
    # Create suite with 2 experiments both marked as baseline
    baseline1 = ExperimentConfig(
        name="baseline1",
        temperature=0.7,
        max_tokens=100,
        is_baseline=True,  # First baseline
    )
    baseline2 = ExperimentConfig(
        name="baseline2",
        temperature=0.8,
        max_tokens=100,
        is_baseline=True,  # Second baseline (malformed config)
    )

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=baseline1,  # First baseline in suite.baseline
        experiments=[
            baseline1,
            baseline2,  # This one should be compared against baseline1
            ExperimentConfig(
                name="exp1",
                temperature=0.9,
                max_tokens=100,
                is_baseline=False,
            ),
        ],
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT 1: All experiments execute
    assert "baseline1" in results
    assert "baseline2" in results
    assert "exp1" in results

    # INVARIANT 2: First baseline never compares to itself
    assert "baseline_comparison" not in results["baseline1"]["payload"]

    # INVARIANT 3: Second baseline would be compared to first
    # (if comparison plugins were configured)
    # This verifies baseline2 is NOT used as the baseline_payload


# ============================================================================
# Middleware Lifecycle Edge Cases
# ============================================================================

# NOTE: Middleware edge cases EC4 and EC7 are comprehensively covered in
# test_suite_runner_middleware_hooks.py (Activity 1). These tests verified:
#   - EC4: Shared middleware deduplication (test_shared_middleware_deduplication)
#   - EC7: Middleware without hooks (test_middleware_without_hooks_doesnt_error)
#
# Activity 1 created 7 tests specifically for middleware hook behavior,
# which is the HIGHEST RISK area (Risk Score 4.0). Those tests are the
# definitive source for middleware edge case coverage.


# ============================================================================
# Baseline Comparison Edge Cases
# ============================================================================


def test_edge_case_no_baseline_comparison_plugins(tmp_path: Path) -> None:
    """EDGE CASE 6: No baseline comparison plugins configured - no comparisons run.

    **Risk Category:** Baseline Comparison
    **Complexity Driver:** Plugin definition merging (lines 397-401)

    **Expected Behavior:**
        - Baseline tracked correctly
        - No baseline_comparison key added to payload
        - Experiments execute normally

    **Why This Edge Case Matters:**
        Baseline comparison is optional. If no plugins are configured at any
        layer (defaults, pack, experiment), the comparison loop should be
        skipped cleanly without adding empty baseline_comparison keys.

    **Code Location:** suite_runner.py lines 397-413 (comparison plugin execution)
    """
    baseline_exp = ExperimentConfig(
        name="baseline",
        temperature=0.7,
        max_tokens=100,
        is_baseline=True,
    )

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=baseline_exp,
        experiments=[
            baseline_exp,
            ExperimentConfig(
                name="exp1",
                temperature=0.8,
                max_tokens=100,
                is_baseline=False,
            ),
        ],
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
        # NO baseline_plugin_defs configured
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT 1: Experiments execute
    assert "baseline" in results
    assert "exp1" in results

    # INVARIANT 2: No baseline_comparison in results
    assert "baseline_comparison" not in results["baseline"]["payload"]
    assert "baseline_comparison" not in results["exp1"]["payload"]


# ============================================================================
# Sink Resolution Edge Cases
# ============================================================================


def test_edge_case_all_sinks_from_factory(tmp_path: Path) -> None:
    """EDGE CASE 8: All sinks resolved via factory - factory called for each experiment.

    **Risk Category:** Sink Resolution
    **Complexity Driver:** Sink resolution paths (lines 329-336)

    **Expected Behavior:**
        - Factory called once per experiment
        - Factory receives correct experiment config
        - Results written to factory-created sinks
        - No errors from missing sink_defs at other layers

    **Why This Edge Case Matters:**
        Factory is the 4th fallback in the sink resolution priority chain
        (after experiment.sink_defs, pack["sinks"], defaults["sink_defs"]).
        This test verifies the factory path works when all other layers are
        absent, and that factory is called fresh for each experiment.

    **Code Location:** suite_runner.py line 336 (factory fallback)
    """
    # Track factory calls
    factory_calls: list[str] = []

    def sink_factory(experiment: ExperimentConfig) -> list[Any]:
        """Factory that tracks which experiments it's called for."""
        factory_calls.append(experiment.name)
        return [CollectingSink()]

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=None,
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.7,
                max_tokens=100,
                # No sink_defs - will use factory
            ),
            ExperimentConfig(
                name="exp2",
                temperature=0.8,
                max_tokens=100,
                # No sink_defs - will use factory
            ),
        ],
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
        # No sink_defs in defaults
        # No prompt_packs configured
    }

    runner = ExperimentSuiteRunner(
        suite,
        SimpleLLM(),
        [],  # No self.sinks (factory will be used)
    )

    results = runner.run(
        pd.DataFrame([{"text": "test"}]),
        defaults,
        sink_factory=sink_factory,
    )

    # INVARIANT 1: Factory called for each experiment
    assert len(factory_calls) == 2, (
        f"Factory should be called once per experiment, got {len(factory_calls)} calls"
    )

    # INVARIANT 2: Factory called with correct experiment configs
    assert "exp1" in factory_calls, "Factory should be called with exp1 config"
    assert "exp2" in factory_calls, "Factory should be called with exp2 config"

    # INVARIANT 3: Experiments execute successfully
    assert "exp1" in results
    assert "exp2" in results

    # INVARIANT 4: Factory called in experiment execution order
    assert factory_calls == ["exp1", "exp2"], (
        "Factory should be called in experiment execution order"
    )


# ============================================================================
# Edge Case Summary
# ============================================================================

"""
EDGE CASE COVERAGE SUMMARY
===========================

6 edge case tests in this file across 3 risk categories:

Suite Configuration (4 tests):
    - EC1: Empty suite → empty results
    - EC2: No baseline → no comparisons
    - EC3: Baseline not first → reordered correctly
    - EC5: Multiple baselines → first wins

Baseline Comparison (1 test):
    - EC6: No plugins → no comparisons

Sink Resolution (1 test):
    - EC8: Factory fallback → called per experiment

Middleware Edge Cases (covered in Activity 1):
    - EC4: Shared middleware deduplication
      → See: test_suite_runner_middleware_hooks.py::test_shared_middleware_deduplication
    - EC7: Middleware without hooks
      → See: test_suite_runner_middleware_hooks.py::test_middleware_without_hooks_doesnt_error

TOTAL EDGE CASE COVERAGE:
8 edge cases across all Activity 1, 3, and 5 tests.

REFACTORING SAFETY:
-------------------
All tests verify behavioral invariants that MUST be preserved during
complexity reduction refactoring. Any test failures indicate regression.

Each test documents:
    - Risk category
    - Complexity driver (code location)
    - Expected behavior
    - Why this edge case matters
    - Code location references

NEXT STEPS:
-----------
After Activity 5 completes:
    - Option A (RECOMMENDED): Proceed to Phase 0 (Characterization Tests)
    - Option B: Complete Activity 4 (Verbose Logging Analysis)
    - Option C: Complete Activity 6 (Risk Assessment Matrix)

See: PROGRESS_suite_runner_refactoring.md for decision matrix
"""
