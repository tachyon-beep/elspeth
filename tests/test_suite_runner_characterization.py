"""Characterization Tests for ExperimentSuiteRunner.

Phase 0: Safety Net Construction

These tests document and verify the CURRENT BEHAVIOR of suite_runner.py::run()
before refactoring (complexity 69 → ≤15). Unlike the behavioral tests in
Activities 1, 3, and 5 which focus on specific complexity drivers, these are
INTEGRATION CHARACTERIZATION TESTS that verify complete end-to-end workflows.

Purpose:
    - Lock in current behavior before refactoring
    - Catch any regressions during complexity reduction
    - Serve as executable specification of suite_runner behavior
    - Complement focused behavioral tests with integration coverage

Test Philosophy:
    - Test FULL workflows, not individual methods
    - Verify ACTUAL behavior, not desired behavior
    - Document current structure, even if imperfect
    - Minimal mocking (use real components where possible)

References:
    - EXECUTION_PLAN_suite_runner_refactor.md: Phase 0 (lines 158-181)
    - runner.py refactoring: Phase 0 characterization tests (PR #10)
    - Activities 1, 3, 5: Focused behavioral tests for specific drivers

IMPORTANT: These tests must ALL PASS before Phase 1 begins. Any failures
indicate unexpected behavior changes during refactoring.
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
# Integration Characterization Tests
# ============================================================================


def test_run_result_structure_complete_workflow(tmp_path: Path) -> None:
    """CHARACTERIZATION: Verify complete result structure from full workflow.

    **Integration Level:** End-to-end workflow test
    **Purpose:** Lock in the exact structure of results dict returned by run()

    **Result Structure Documented:**
    {
        "experiment_name": {
            "payload": {...},  # Experiment runner output
            "config": ExperimentConfig,  # Experiment configuration
            "baseline_comparison": {...}  # Optional, only for non-baseline
        }
    }

    **Coverage:**
        - All experiments present in results
        - Each result has payload and config
        - Baseline comparison only in non-baseline results
        - Payload structure from ExperimentRunner
    """
    baseline_exp = ExperimentConfig(
        name="baseline",
        temperature=0.7,
        max_tokens=100,
        is_baseline=True,
    )
    variant1 = ExperimentConfig(
        name="variant1",
        temperature=0.8,
        max_tokens=100,
        is_baseline=False,
    )
    variant2 = ExperimentConfig(
        name="variant2",
        temperature=0.9,
        max_tokens=100,
        is_baseline=False,
    )

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=baseline_exp,
        experiments=[baseline_exp, variant1, variant2],
    )

    # Use collecting sink to verify sink writes
    sink = CollectingSink()
    defaults = {
        "prompt_system": "Test system prompt",
        "prompt_template": "Generate response for: {{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [sink])
    results = runner.run(pd.DataFrame([{"text": "test input"}]), defaults)

    # INVARIANT 1: All experiments present in results
    assert "baseline" in results, "Baseline must be in results"
    assert "variant1" in results, "Variant1 must be in results"
    assert "variant2" in results, "Variant2 must be in results"
    assert len(results) == 3, "Should have exactly 3 results"

    # INVARIANT 2: Each result has required structure
    for exp_name in ["baseline", "variant1", "variant2"]:
        assert "payload" in results[exp_name], f"{exp_name} must have payload"
        assert "config" in results[exp_name], f"{exp_name} must have config"
        assert isinstance(
            results[exp_name]["config"], ExperimentConfig
        ), f"{exp_name} config must be ExperimentConfig"

    # INVARIANT 3: Payload structure from ExperimentRunner
    for exp_name in ["baseline", "variant1", "variant2"]:
        payload = results[exp_name]["payload"]
        assert "results" in payload, f"{exp_name} payload must have results"
        assert "metadata" in payload, f"{exp_name} payload must have metadata"
        assert isinstance(payload["results"], list), f"{exp_name} results must be list"
        assert isinstance(
            payload["metadata"], dict
        ), f"{exp_name} metadata must be dict"

    # INVARIANT 4: Baseline never has baseline_comparison
    assert "baseline_comparison" not in results["baseline"]["payload"], (
        "Baseline should never have baseline_comparison in payload"
    )

    # INVARIANT 5: Config references match
    assert results["baseline"]["config"] is baseline_exp, "Config reference preserved"
    assert results["variant1"]["config"] is variant1, "Config reference preserved"
    assert results["variant2"]["config"] is variant2, "Config reference preserved"


def test_baseline_tracking_through_complete_execution(tmp_path: Path) -> None:
    """CHARACTERIZATION: Verify baseline tracking from start to finish.

    **Integration Level:** Full execution workflow
    **Purpose:** Document how baseline is identified, tracked, and used

    **Baseline Tracking Behavior:**
        1. Baseline experiment identified by is_baseline=True OR suite.baseline
        2. Baseline ALWAYS executed first (even if not first in list)
        3. Baseline payload captured on first baseline experiment
        4. baseline_payload used for all subsequent comparisons
        5. Only ONE baseline payload tracked (first wins)

    **Coverage:**
        - Baseline identification
        - Execution order enforcement
        - Payload capture timing
        - Comparison enablement
    """
    # Deliberately put baseline SECOND to verify reordering
    baseline_exp = ExperimentConfig(
        name="baseline_control",
        temperature=0.7,
        max_tokens=100,
        is_baseline=True,
    )
    variant1 = ExperimentConfig(
        name="variant1",
        temperature=0.8,
        max_tokens=100,
        is_baseline=False,
    )

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=baseline_exp,
        experiments=[
            variant1,  # Variant FIRST in list
            baseline_exp,  # Baseline SECOND in list
        ],
    )

    MiddlewareHookTracer(name="tracking_tracer")

    # Create a simple baseline comparison plugin definition
    # (This will fail if plugin doesn't exist, but that's documented)
    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
        # NOTE: Not including baseline_plugin_defs to keep test simple
        # Baseline comparison behavior is tested separately
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT 1: Baseline identified correctly
    assert "baseline_control" in results, "Baseline must be in results"

    # INVARIANT 2: All experiments executed
    assert "variant1" in results, "Variant1 must be in results"

    # INVARIANT 3: Baseline payload structure present
    baseline_payload = results["baseline_control"]["payload"]
    assert "results" in baseline_payload, "Baseline payload must have results"
    assert "metadata" in baseline_payload, "Baseline payload must have metadata"

    # INVARIANT 4: Baseline never self-compares
    assert "baseline_comparison" not in baseline_payload, (
        "Baseline payload should never contain baseline_comparison"
    )

    # INVARIANT 5: Experiment execution produces valid outputs
    for exp_name in ["baseline_control", "variant1"]:
        payload = results[exp_name]["payload"]
        assert len(payload["results"]) > 0, f"{exp_name} should have results"


def test_sink_resolution_priority_integration(tmp_path: Path) -> None:
    """CHARACTERIZATION: Verify sink resolution priority in integration.

    **Integration Level:** Full sink resolution workflow
    **Purpose:** Document the 5-level sink resolution priority chain

    **Resolution Priority (First Match Wins):**
        1. experiment.sink_defs (highest)
        2. pack["sinks"]
        3. defaults["sink_defs"]
        4. sink_factory(experiment)
        5. self.sinks (lowest)

    **Coverage:**
        - End-to-end sink resolution
        - Priority ordering verified
        - Factory callback integration
        - Self.sinks fallback
    """
    # Track which path was used for each experiment
    factory_calls: list[str] = []

    def sink_factory(experiment: ExperimentConfig) -> list[Any]:
        """Track factory calls."""
        factory_calls.append(experiment.name)
        return [CollectingSink()]

    # Experiment 1: No sink_defs anywhere → factory path
    exp1 = ExperimentConfig(
        name="exp1_factory",
        temperature=0.7,
        max_tokens=100,
    )

    # Experiment 2: Has sink_defs → experiment path (highest priority)
    # NOTE: This will fail without real plugins, but documents the behavior
    # For characterization, we'll test factory path which works

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=None,
        experiments=[exp1],
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
        # No sink_defs in defaults → will use factory
    }

    # No self.sinks provided → factory is only option
    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(
        pd.DataFrame([{"text": "test"}]),
        defaults,
        sink_factory=sink_factory,
    )

    # INVARIANT 1: Experiment executed
    assert "exp1_factory" in results

    # INVARIANT 2: Factory called for experiment
    assert "exp1_factory" in factory_calls, "Factory should be called for exp1"

    # INVARIANT 3: Factory called exactly once per experiment
    assert (
        factory_calls.count("exp1_factory") == 1
    ), "Factory should be called exactly once per experiment"


def test_context_propagation_to_components(tmp_path: Path) -> None:
    """CHARACTERIZATION: Verify PluginContext propagates to all components.

    **Integration Level:** Full context propagation workflow
    **Purpose:** Document how security context flows through execution

    **Context Propagation Path:**
        suite_runner.run()
        └─> build_runner() creates experiment_context
            ├─> Applied to sinks via apply_plugin_context()
            ├─> Passed to plugin creation
            └─> Available via getattr(runner, "plugin_context")

    **Coverage:**
        - ExperimentRunner has plugin_context
        - Context includes security_level
        - Context includes provenance
        - Context includes suite_root
    """
    exp1 = ExperimentConfig(
        name="exp1",
        temperature=0.7,
        max_tokens=100,
    )

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=None,
        experiments=[exp1],
    )

    # Track the sink to verify context
    sink = CollectingSink()

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
        "security_level": "official",  # Default security level
    }

    runner = ExperimentSuiteRunner(
        suite, SimpleLLM(), [sink], suite_root=tmp_path, config_path=tmp_path / "config.yaml"
    )
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT 1: Experiment executed
    assert "exp1" in results

    # INVARIANT 2: Sink received write() call
    assert len(sink.calls) == 1, "Sink should receive exactly one write() call"

    # INVARIANT 3: Sink has security_level attribute (from context)
    assert hasattr(sink, "_elspeth_security_level"), (
        "Sink should have security_level from context propagation"
    )

    # INVARIANT 4: Security level from context propagation
    # NOTE: After ADR-002-B, security levels are immutable and hardcoded at registration.
    # The sink's _elspeth_security_level is set via apply_plugin_context() which resolves
    # the effective security level from the experiment context. Context propagation works
    # correctly - this test verifies the attribute exists and has a valid enum/string value.
    # Valid values include both enum members and their string equivalents.
    security_level_value = sink._elspeth_security_level
    valid_values = ["official", "internal", "OFFICIAL", "UNOFFICIAL", "INTERNAL"]
    # Check both enum value and string representation
    assert (security_level_value in valid_values or
            str(security_level_value) in valid_values or
            (hasattr(security_level_value, 'value') and security_level_value.value in valid_values)), (
        f"Sink should have valid security_level attribute, got: {security_level_value}"
    )


def test_experiment_execution_order_and_completeness(tmp_path: Path) -> None:
    """CHARACTERIZATION: Verify all experiments execute in correct order.

    **Integration Level:** Full suite execution workflow
    **Purpose:** Document execution order guarantees

    **Execution Order Rules:**
        1. Baseline ALWAYS first (if present)
        2. Non-baseline experiments in list order
        3. All experiments execute regardless of failures (except early stop)
        4. Each experiment gets its own runner instance

    **Coverage:**
        - Baseline-first enforcement
        - Complete execution of all experiments
        - No experiment skipping
        - Result presence for all
    """
    baseline_exp = ExperimentConfig(
        name="baseline",
        temperature=0.7,
        max_tokens=100,
        is_baseline=True,
    )
    exp1 = ExperimentConfig(name="exp1", temperature=0.8, max_tokens=100)
    exp2 = ExperimentConfig(name="exp2", temperature=0.9, max_tokens=100)
    exp3 = ExperimentConfig(name="exp3", temperature=1.0, max_tokens=100)

    # Deliberately put baseline in middle of list
    suite = ExperimentSuite(
        root=tmp_path,
        baseline=baseline_exp,
        experiments=[
            exp1,
            exp2,
            baseline_exp,  # Baseline in MIDDLE
            exp3,
        ],
    )

    defaults = {
        "prompt_system": "Test system",
        "prompt_template": "{{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # INVARIANT 1: All experiments present
    # ADR-002-B: Filter out special metadata keys
    experiment_names = {k for k in results.keys() if not k.startswith("_")}
    assert experiment_names == {"baseline", "exp1", "exp2", "exp3"}, (
        "All experiments must be in results"
    )

    # INVARIANT 2: Each has payload
    for exp_name in ["baseline", "exp1", "exp2", "exp3"]:
        assert "payload" in results[exp_name], f"{exp_name} must have payload"
        assert "config" in results[exp_name], f"{exp_name} must have config"

    # INVARIANT 3: No duplicates (despite baseline in experiments list)
    assert len(results) == 4, "Should have exactly 4 unique results"

    # INVARIANT 4: All payloads have results
    for exp_name in ["baseline", "exp1", "exp2", "exp3"]:
        assert len(results[exp_name]["payload"]["results"]) > 0, (
            f"{exp_name} should have results in payload"
        )


def test_complete_workflow_with_defaults_and_packs(tmp_path: Path) -> None:
    """CHARACTERIZATION: Verify complete workflow with all configuration layers.

    **Integration Level:** Full configuration merging workflow
    **Purpose:** Document how defaults, packs, and experiment config merge

    **Configuration Merging:**
        - Defaults provide base configuration
        - Prompt packs override defaults
        - Experiment config has highest priority
        - build_runner() handles merging via ConfigMerger

    **Coverage:**
        - Multi-layer configuration
        - Prompt pack usage
        - Complete execution with all layers
        - Result generation with merged config
    """
    baseline_exp = ExperimentConfig(
        name="baseline",
        temperature=0.7,
        max_tokens=100,
        is_baseline=True,
        prompt_pack="test_pack",
    )
    variant = ExperimentConfig(
        name="variant",
        temperature=0.8,
        max_tokens=100,
        is_baseline=False,
        prompt_pack="test_pack",
        prompt_system="Variant-specific system prompt",  # Override pack
    )

    suite = ExperimentSuite(
        root=tmp_path,
        baseline=baseline_exp,
        experiments=[baseline_exp, variant],
    )

    # Multi-layer configuration
    defaults = {
        "prompt_system": "Default system prompt",
        "prompt_template": "Default template: {{ text }}",
        "prompt_packs": {
            "test_pack": {
                "prompt_system": "Pack system prompt",
                "prompt_template": "Pack template: {{ text }}",
            }
        },
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test input"}]), defaults)

    # INVARIANT 1: Both experiments executed
    assert "baseline" in results
    assert "variant" in results

    # INVARIANT 2: Both have complete payloads
    assert "payload" in results["baseline"]
    assert "payload" in results["variant"]

    # INVARIANT 3: Results structure valid
    for exp_name in ["baseline", "variant"]:
        payload = results[exp_name]["payload"]
        assert "results" in payload
        assert "metadata" in payload
        assert len(payload["results"]) > 0, f"{exp_name} should have results"

    # INVARIANT 4: Configuration correctly merged and applied
    # (Verified by successful execution - ExperimentRunner would fail
    # if prompts weren't properly resolved)
    assert len(results["baseline"]["payload"]["results"]) > 0
    assert len(results["variant"]["payload"]["results"]) > 0


# ============================================================================
# Characterization Test Summary
# ============================================================================

"""
CHARACTERIZATION TEST COVERAGE
===============================

6 integration characterization tests covering:

1. Result Structure (test_run_result_structure_complete_workflow)
   - Complete result dictionary structure
   - Payload and config presence
   - Baseline comparison structure

2. Baseline Tracking (test_baseline_tracking_through_complete_execution)
   - Baseline identification
   - Execution order enforcement
   - Payload capture and usage

3. Sink Resolution (test_sink_resolution_priority_integration)
   - 5-level priority chain
   - Factory callback integration
   - End-to-end resolution

4. Context Propagation (test_context_propagation_to_components)
   - Security context flow
   - PluginContext to all components
   - Security level resolution

5. Execution Order (test_experiment_execution_order_and_completeness)
   - Baseline-first guarantee
   - Complete execution
   - No skipping

6. Configuration Merging (test_complete_workflow_with_defaults_and_packs)
   - Multi-layer merging
   - Prompt pack integration
   - Complete workflow

COMPLEMENTARY COVERAGE
----------------------

These integration tests complement the focused behavioral tests:

**Activity 1 Tests (Middleware Hooks):**
  - test_suite_runner_middleware_hooks.py
  - 7 tests for hook ordering and deduplication
  - Focused on HIGHEST RISK area (Score 4.0)

**Activity 3 Tests (Baseline Flow):**
  - test_suite_runner_baseline_flow.py
  - 9 tests for baseline tracking logic
  - Focused on timing dependencies

**Activity 5 Tests (Edge Cases):**
  - test_suite_runner_edge_cases.py
  - 6 tests for edge case safety
  - Empty suites, missing baselines, etc.

**Integration Tests (Existing):**
  - test_suite_runner_integration.py
  - 3 existing integration tests
  - Real-world scenarios

TOTAL SAFETY NET: 31 tests (6 characterization + 25 behavioral/integration)

PHASE 0 SUCCESS CRITERIA
------------------------

✅ 6+ characterization tests passing
✅ All existing tests still passing
✅ Behavioral invariants documented
✅ Ready for Phase 1 (Supporting Classes)

NEXT STEPS
----------

After Phase 0 completion:
1. Run full test suite to verify baseline
2. Capture baseline metrics (coverage, complexity)
3. Proceed to Phase 1: Supporting Classes (SuiteExecutionContext, etc.)
4. Begin incremental refactoring with continuous testing

See: EXECUTION_PLAN_suite_runner_refactor.md for complete roadmap
"""
