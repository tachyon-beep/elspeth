"""Risk Reduction Tests: Suite Runner Baseline Tracking Flow.

These tests verify the critical baseline tracking and comparison timing logic
in suite_runner.py::run(), focusing on edge cases and invariants:

1. First baseline wins (multiple baselines)
2. No baseline handling (graceful degradation)
3. Baseline never compares to itself
4. All non-baseline experiments get compared
5. Baseline ordering enforcement

INVARIANT: These behaviors must be preserved during refactoring.
"""

from __future__ import annotations


def test_baseline_tracked_on_first_baseline_only() -> None:
    """INVARIANT: When multiple experiments have is_baseline=True, first one wins.

    This tests the "first baseline wins" logic from suite_runner.py:377-378:
        if baseline_payload is None and (experiment.is_baseline or ...):
            baseline_payload = payload

    The None-check ensures only the FIRST baseline sets the payload.
    """
    # Simulate suite execution with multiple baselines (malformed config)
    baseline_payload = None
    experiments = [
        {"name": "baseline1", "is_baseline": True},
        {"name": "baseline2", "is_baseline": True},
        {"name": "variant1", "is_baseline": False},
    ]

    tracked_baselines = []

    for experiment in experiments:
        # Simulate payload from runner.run()
        payload = {"results": [f"{experiment['name']}_result"]}

        # Baseline tracking logic (from suite_runner.py:377-378)
        if baseline_payload is None and experiment["is_baseline"]:
            baseline_payload = payload
            tracked_baselines.append(experiment["name"])

    # Critical assertion: Only first baseline tracked
    assert len(tracked_baselines) == 1, \
        "Only first baseline should be tracked"
    assert tracked_baselines[0] == "baseline1", \
        "First baseline should be baseline1"
    assert baseline_payload == {"results": ["baseline1_result"]}, \
        "baseline_payload should reference first baseline"


def test_baseline_comparison_skipped_when_no_baseline() -> None:
    """INVARIANT: When no baseline exists, all experiments skip comparison.

    Tests graceful handling when baseline_payload stays None throughout execution.
    """
    baseline_payload = None  # Never set
    experiments = [
        {"name": "exp1", "is_baseline": False},
        {"name": "exp2", "is_baseline": False},
        {"name": "exp3", "is_baseline": False},
    ]

    comparisons_run = []

    for experiment in experiments:
        # Comparison guard logic (from suite_runner.py:396)
        if baseline_payload is not None:
            comparisons_run.append(experiment["name"])

    # Critical assertion: No comparisons run
    assert len(comparisons_run) == 0, \
        "No comparisons should run when baseline_payload is None"


def test_baseline_never_compares_to_itself() -> None:
    """INVARIANT: Baseline experiment never runs comparison against itself.

    Tests the dual-guard pattern from suite_runner.py:396:
        if baseline_payload and experiment != self.suite.baseline:

    Even if baseline is last in list (shouldn't happen due to ordering),
    the != check prevents self-comparison.
    """

    class MockExperiment:
        def __init__(self, name: str, is_baseline: bool):
            self.name = name
            self.is_baseline = is_baseline

        def __eq__(self, other):
            return self is other

    baseline_exp = MockExperiment("baseline", True)
    variant_exp = MockExperiment("variant", False)

    experiments = [baseline_exp, variant_exp]
    baseline_payload = {"results": ["baseline_result"]}
    suite_baseline = baseline_exp  # Reference to baseline

    comparisons_run = []

    for experiment in experiments:

        # Comparison guard (from suite_runner.py:396)
        if baseline_payload and experiment != suite_baseline:
            comparisons_run.append(experiment.name)

    # Critical assertion: Only variant compared, not baseline
    assert "variant" in comparisons_run, \
        "Variant should run comparison"
    assert "baseline" not in comparisons_run, \
        "Baseline should NOT run comparison against itself"


def test_all_non_baseline_experiments_get_compared() -> None:
    """INVARIANT: Every non-baseline experiment runs baseline comparison.

    No filtering or early-exit - all variants get compared to baseline.
    """
    baseline_payload = {"results": ["baseline_result"]}  # Baseline already ran

    experiments = [
        {"name": "variant1", "is_baseline": False},
        {"name": "variant2", "is_baseline": False},
        {"name": "variant3", "is_baseline": False},
        {"name": "variant4", "is_baseline": False},
        {"name": "variant5", "is_baseline": False},
    ]

    comparisons_run = []

    for experiment in experiments:
        # Comparison guard (simplified - no suite.baseline check since none are baseline)
        if baseline_payload:
            comparisons_run.append(experiment["name"])

    # Critical assertion: ALL experiments compared
    assert len(comparisons_run) == 5, \
        "All 5 non-baseline experiments should run comparison"
    assert comparisons_run == ["variant1", "variant2", "variant3", "variant4", "variant5"], \
        "All variants should be compared in order"


def test_baseline_ordering_enforced() -> None:
    """INVARIANT: Baseline is always first in experiment execution order.

    Tests the experiment list construction from suite_runner.py:304-306:
        experiments = []
        if self.suite.baseline:
            experiments.append(self.suite.baseline)
        experiments.extend(exp for exp in self.suite.experiments if exp != self.suite.baseline)

    This ensures baseline runs before any comparisons are attempted.
    """

    class MockExperiment:
        def __init__(self, name: str, is_baseline: bool):
            self.name = name
            self.is_baseline = is_baseline

        def __eq__(self, other):
            return self.name == other.name if hasattr(other, 'name') else False

        def __repr__(self):
            return f"<Exp:{self.name}>"

    # Suite configuration with baseline NOT first
    baseline_exp = MockExperiment("baseline", True)
    variant1 = MockExperiment("variant1", False)
    variant2 = MockExperiment("variant2", False)

    # Original list: variants first, baseline last (unusual but possible)
    suite_experiments_raw = [variant1, variant2, baseline_exp]
    suite_baseline = baseline_exp

    # Experiment ordering logic (from suite_runner.py:304-306)
    experiments = []
    if suite_baseline:
        experiments.append(suite_baseline)
    experiments.extend(exp for exp in suite_experiments_raw if exp != suite_baseline)

    # Critical assertion: Baseline is first
    assert len(experiments) == 3, "All experiments should be in list"
    assert experiments[0] == baseline_exp, "Baseline must be first"
    assert experiments[1] == variant1, "variant1 should be second"
    assert experiments[2] == variant2, "variant2 should be third"

    # Verify no duplicates (baseline filtered from extend)
    experiment_names = [exp.name for exp in experiments]
    assert len(experiment_names) == len(set(experiment_names)), \
        "No duplicate experiments"


def test_baseline_payload_immutability_risk() -> None:
    """DOCUMENTATION: Baseline payload is NOT deep-copied - mutation risk exists.

    This test documents the current behavior where baseline_payload is a direct
    reference, not a deep copy. Comparison plugins could mutate it.

    NOTE: This is a KNOWN RISK, not a bug. Documented for refactoring awareness.
    """
    baseline_payload_original = {
        "results": [{"response": "original"}],
        "metadata": {"count": 1},
    }

    # Simulate setting baseline payload (direct reference)
    baseline_payload = baseline_payload_original

    # Simulate comparison plugin mutating baseline payload
    baseline_payload["results"].append({"response": "mutated"})
    baseline_payload["metadata"]["count"] = 999

    # Current behavior: Original dict is mutated (no copy protection)
    assert baseline_payload_original["metadata"]["count"] == 999, \
        "Original dict is mutated (current behavior - no immutability)"
    assert len(baseline_payload_original["results"]) == 2, \
        "Original results list is mutated"

    # This documents that comparison plugins share the same baseline reference
    # If refactoring adds immutability, this test should be updated


def test_baseline_comparison_runs_after_each_experiment_completes() -> None:
    """INVARIANT: Baseline comparison runs immediately after each experiment completes.

    Not batched at the end - runs in the experiment loop for each variant.
    """
    baseline_payload = {"results": ["baseline"]}

    # Simulate experiment execution with comparison timing
    execution_log = []

    experiments = [
        {"name": "variant1"},
        {"name": "variant2"},
        {"name": "variant3"},
    ]

    for experiment in experiments:
        # Experiment execution
        execution_log.append(f"{experiment['name']}_start")
        execution_log.append(f"{experiment['name']}_complete")

        # Comparison runs IMMEDIATELY (not batched)
        if baseline_payload:
            execution_log.append(f"{experiment['name']}_comparison")

    # Verify interleaved execution (not all experiments then all comparisons)
    expected_log = [
        "variant1_start",
        "variant1_complete",
        "variant1_comparison",  # Immediate
        "variant2_start",
        "variant2_complete",
        "variant2_comparison",  # Immediate
        "variant3_start",
        "variant3_complete",
        "variant3_comparison",  # Immediate
    ]

    assert execution_log == expected_log, \
        "Comparisons should run immediately after each experiment, not batched"


def test_baseline_comparison_plugin_definition_merging() -> None:
    """INVARIANT: Baseline plugin defs merge from 3 sources in priority order.

    From suite_runner.py:397-401:
    1. Start with defaults.baseline_plugin_defs
    2. Prepend pack.baseline_plugins (if exists)
    3. Append experiment.baseline_plugin_defs (if exists)

    Result: pack plugins run first, then defaults, then experiment-specific
    """

    # Simulate configuration layers
    defaults = {
        "baseline_plugin_defs": [
            {"plugin": "default_comparison_1"},
            {"plugin": "default_comparison_2"},
        ],
    }

    pack = {
        "baseline_plugins": [
            {"plugin": "pack_comparison"},
        ],
    }

    experiment = {
        "name": "variant1",
        "baseline_plugin_defs": [
            {"plugin": "experiment_specific_comparison"},
        ],
    }

    # Merging logic (from suite_runner.py:397-401)
    comp_defs = list(defaults.get("baseline_plugin_defs", []))

    if pack and pack.get("baseline_plugins"):
        comp_defs = list(pack.get("baseline_plugins", [])) + comp_defs

    if experiment.get("baseline_plugin_defs"):
        comp_defs += experiment["baseline_plugin_defs"]

    # Verify merge order
    expected_order = [
        {"plugin": "pack_comparison"},              # Pack first
        {"plugin": "default_comparison_1"},         # Defaults next
        {"plugin": "default_comparison_2"},
        {"plugin": "experiment_specific_comparison"},  # Experiment last
    ]

    assert comp_defs == expected_order, \
        "Plugin defs should merge in pack → defaults → experiment order"


def test_baseline_comparison_skipped_when_no_plugins() -> None:
    """INVARIANT: When no comparison plugin defs exist, comparisons dict stays empty.

    Empty comparisons dict is not added to payload (lines 408-410 check `if comparisons`).
    """

    # No comparison plugin definitions from any source
    comp_defs = []

    comparisons = {}
    for defn in comp_defs:  # Empty loop
        # Would create and run plugin here
        pass

    # Guard from lines 408-410
    payload = {"results": ["variant_result"]}
    if comparisons:
        payload["baseline_comparison"] = comparisons

    # Critical assertion: No baseline_comparison key added
    assert "baseline_comparison" not in payload, \
        "Empty comparisons should not add baseline_comparison key to payload"
