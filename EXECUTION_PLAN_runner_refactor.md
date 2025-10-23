# EXECUTION PLAN: ExperimentRunner.run() Refactoring

**Target:** `src/elspeth/core/experiments/runner.py:75-245`
**Goal:** Reduce complexity from 73 to < 15
**Branch:** `refactor/runner-run-method` (to be created)
**Estimated Total Time:** 17.5 hours (~2.5 days)
**Start Date:** TBD
**Status:** 🔴 NOT STARTED

---

## Executive Summary

This plan combines risk mitigation and refactoring activities into a single executable workflow. Each phase has clear deliverables, verification steps, and rollback triggers.

**Key Metrics:**
- Current: 171 lines, complexity 73, 14 responsibilities
- Target: ~35 lines, complexity ~8, 12 focused methods
- Test Coverage: 89% → maintain or improve
- All 18 existing tests must continue passing

---

## ⚠️ Important Discovery Note

**Checkpoint Format Discovery:**
During Phase 0 characterization testing, we discovered that the checkpoint file format is **plain text** (one row ID per line with newline terminator: `"row1\nrow2\nrow3\n"`), **not JSONL** as this plan originally assumed. This was documented in characterization tests and confirmed in the codebase.

See `REFACTORING_COMPLETE_summary.md:51` for details on this discovery.

This does not affect the refactoring approach but clarifies the actual implementation being refactored.

---

## Pre-Flight Checklist

**Before starting Phase 0:**

- [ ] Read this entire plan
- [ ] Ensure clean working directory (`git status`)
- [ ] Verify on correct branch (`refactor/sonar-code-quality`)
- [ ] All existing tests passing
- [ ] Coffee/tea prepared ☕

**Environment Check:**
```bash
# Verify environment
git status
git branch --show-current
python -m pytest tests/test_experiments.py tests/test_experiment_runner_integration.py -v
mypy src/elspeth/core/experiments/runner.py
```

**Expected Results:**
- ✅ Clean git status (or only documentation changes)
- ✅ On branch: `refactor/sonar-code-quality`
- ✅ 18/18 tests passing
- ✅ MyPy: no errors

---

## Phase 0: Safety Net Construction (3.5 hours)

**Objective:** Create comprehensive test coverage before refactoring

**Risk Level:** 🟢 LOW
**Estimated Time:** 3.5 hours

### Step 0.1: Create Characterization Test File (30 min)

**Task:** Create new test file with infrastructure

- [ ] Create `tests/test_runner_characterization.py`
- [ ] Add imports and fixtures
- [ ] Run empty file test (`pytest tests/test_runner_characterization.py -v`)

**Code:**
```python
"""Characterization tests documenting ExperimentRunner.run() behavior.

These tests capture the exact current behavior to detect any changes during refactoring.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from elspeth.core.base.protocols import Artifact, LLMRequest, ResultSink
from elspeth.core.experiments.runner import ExperimentRunner


class SimpleLLM:
    """Deterministic LLM for characterization tests."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        row_id = metadata.get("row_id", "unknown")
        return {
            "content": f"response_{row_id}",
            "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        }


class CollectingSink(ResultSink):
    """Sink that records all calls for assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        self._elspeth_security_level = "official"

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        self.calls.append((results, metadata))


@pytest.fixture
def simple_runner() -> ExperimentRunner:
    """Basic runner for characterization tests."""
    return ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[CollectingSink()],
        prompt_system="You are a test assistant.",
        prompt_template="Process: {{ field }}",
    )
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py -v
# Should pass with 0 tests collected
```

**Commit:**
```bash
git add tests/test_runner_characterization.py
git commit -m "Test: Add characterization test infrastructure for runner.run()"
```

---

### Step 0.2: Add Core Behavior Characterization Tests (90 min)

**Task:** Document critical invariants with tests

- [ ] Test: Result structure
- [ ] Test: Result order preservation
- [ ] Test: Checkpoint idempotency
- [ ] Test: Early stop termination
- [ ] Test: Aggregator receives all results
- [ ] Test: Failure isolation
- [ ] Run tests
- [ ] Commit

**Code to add to `tests/test_runner_characterization.py`:**

```python
def test_run_result_structure(simple_runner: ExperimentRunner) -> None:
    """INVARIANT: run() returns dict with required top-level keys."""
    df = pd.DataFrame([{"field": "value1"}])
    result = simple_runner.run(df)

    # Top-level keys
    assert isinstance(result, dict)
    assert "results" in result
    assert "failures" in result
    assert "metadata" in result

    # Metadata structure
    metadata = result["metadata"]
    assert "rows" in metadata
    assert "row_count" in metadata
    assert "security_level" in metadata
    assert "determinism_level" in metadata

    # Results structure
    assert isinstance(result["results"], list)
    assert isinstance(result["failures"], list)


def test_run_preserves_dataframe_order(simple_runner: ExperimentRunner) -> None:
    """INVARIANT: Results maintain DataFrame row order (even with concurrency)."""
    df = pd.DataFrame([
        {"field": "A", "id": "row1"},
        {"field": "B", "id": "row2"},
        {"field": "C", "id": "row3"},
        {"field": "D", "id": "row4"},
        {"field": "E", "id": "row5"},
    ])

    result = simple_runner.run(df)

    # Extract field values in result order
    result_fields = [r["context"]["field"] for r in result["results"]]
    expected_fields = ["A", "B", "C", "D", "E"]

    assert result_fields == expected_fields, "Result order must match DataFrame order"


def test_run_checkpoint_idempotency(tmp_path: Path) -> None:
    """INVARIANT: Re-running with checkpoint skips already processed rows."""
    checkpoint_file = tmp_path / "test_checkpoint.jsonl"

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        checkpoint_config={
            "path": str(checkpoint_file),
            "field": "id",
        },
    )

    df = pd.DataFrame([
        {"id": "A", "data": "first"},
        {"id": "B", "data": "second"},
    ])

    # First run: process both rows
    result1 = runner.run(df)
    assert len(result1["results"]) == 2
    assert checkpoint_file.exists()

    # Verify checkpoint contents
    with checkpoint_file.open("r") as f:
        checkpoint_ids = {json.loads(line)["id"] for line in f}
    assert checkpoint_ids == {"A", "B"}

    # Second run: both rows already checkpointed
    result2 = runner.run(df)
    assert len(result2["results"]) == 0, "All rows should be skipped"

    # Third run: add new row
    df_extended = pd.DataFrame([
        {"id": "A", "data": "first"},
        {"id": "B", "data": "second"},
        {"id": "C", "data": "third"},
    ])
    result3 = runner.run(df_extended)
    assert len(result3["results"]) == 1, "Only new row C should be processed"
    assert result3["results"][0]["context"]["id"] == "C"


def test_run_early_stop_terminates_processing() -> None:
    """INVARIANT: Early stop prevents further row processing."""
    class StopAfterTwo:
        name = "stop_after_two"

        def __init__(self) -> None:
            self.count = 0

        def reset(self) -> None:
            self.count = 0

        def check(self, record: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
            self.count += 1
            if self.count >= 2:
                return {
                    "reason": "stopped_after_two",
                    "row_index": metadata.get("row_index") if metadata else None,
                }
            return None

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        early_stop_plugins=[StopAfterTwo()],
    )

    df = pd.DataFrame([{"id": f"row{i}"} for i in range(10)])
    result = runner.run(df)

    # Should process exactly 2 rows before stopping
    assert len(result["results"]) == 2
    assert "early_stop" in result["metadata"]
    assert result["metadata"]["early_stop"]["reason"] == "stopped_after_two"


def test_run_aggregator_receives_complete_results() -> None:
    """INVARIANT: Aggregators receive all processed results."""
    class CountingAggregator:
        name = "counter"

        def __init__(self) -> None:
            self.received_count: int | None = None
            self.received_results: list[dict[str, Any]] | None = None

        def finalize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
            self.received_count = len(results)
            self.received_results = list(results)  # Copy for inspection
            return {"count": self.received_count, "row_ids": [r["context"]["id"] for r in results]}

    agg = CountingAggregator()
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        aggregator_plugins=[agg],
    )

    df = pd.DataFrame([{"id": f"row{i}"} for i in range(5)])
    result = runner.run(df)

    # Verify aggregator received all results
    assert agg.received_count == 5
    assert len(agg.received_results) == 5

    # Verify aggregator output in payload
    assert "aggregates" in result
    assert "counter" in result["aggregates"]
    assert result["aggregates"]["counter"]["count"] == 5


def test_run_single_failure_doesnt_block_others() -> None:
    """INVARIANT: One row failure doesn't prevent processing other rows."""
    class SelectiveLLM:
        """LLM that fails on specific rows."""

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            metadata = metadata or {}
            row_id = metadata.get("row_id", "unknown")

            if row_id == "fail_row":
                raise RuntimeError("Simulated permanent failure")

            return {
                "content": f"success_{row_id}",
                "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
            }

    runner = ExperimentRunner(
        llm_client=SelectiveLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        retry_config={"max_attempts": 1},  # Don't retry to keep test fast
    )

    df = pd.DataFrame([
        {"id": "ok1"},
        {"id": "fail_row"},
        {"id": "ok2"},
        {"id": "ok3"},
    ])

    result = runner.run(df)

    # Should have 3 successes and 1 failure
    assert len(result["results"]) == 3, "3 rows should succeed"
    assert len(result["failures"]) == 1, "1 row should fail"

    # Verify successful row IDs
    success_ids = {r["context"]["id"] for r in result["results"]}
    assert success_ids == {"ok1", "ok2", "ok3"}

    # Verify failure
    assert result["failures"][0]["context"]["id"] == "fail_row"
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py -v
# Should show 6/6 tests passing
```

**Commit:**
```bash
git add tests/test_runner_characterization.py
git commit -m "Test: Add 6 characterization tests for runner.run() invariants

Document critical behavioral invariants:
- Result structure and required keys
- Result order preservation
- Checkpoint idempotency (skip processed rows)
- Early stop termination
- Aggregator receives all results
- Failure isolation (one failure doesn't block others)

All tests passing. These serve as regression detection during refactoring."
```

---

### Step 0.3: Add Safety Gap Tests (60 min)

**Task:** Cover identified test gaps

- [ ] Create `tests/test_runner_safety.py`
- [ ] Test: Empty DataFrame
- [ ] Test: Concurrent execution
- [ ] Test: Aggregator exception handling
- [ ] Run tests
- [ ] Commit

**Code:**
```python
"""Safety tests for edge cases and error conditions in ExperimentRunner."""

from __future__ import annotations

import threading
from typing import Any

import pandas as pd
import pytest

from elspeth.core.experiments.runner import ExperimentRunner


class SimpleLLM:
    """Deterministic LLM for safety tests."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"content": "test", "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}}


def test_run_with_empty_dataframe() -> None:
    """Edge case: Empty DataFrame should return empty results without error."""
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ field }}",
    )

    df = pd.DataFrame()  # Empty DataFrame

    result = runner.run(df)

    # Should complete successfully
    assert result["results"] == []
    assert result["failures"] == []
    assert result["metadata"]["rows"] == 0
    assert result["metadata"]["row_count"] == 0


def test_run_with_concurrent_execution() -> None:
    """Safety: Concurrent execution maintains result order and count."""
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        concurrency_config={"max_workers": 3},
    )

    # Enough rows to trigger parallel execution
    df = pd.DataFrame([{"id": f"row{i}"} for i in range(20)])

    result = runner.run(df)

    # All rows processed
    assert len(result["results"]) == 20

    # Results maintain order
    result_ids = [r["context"]["id"] for r in result["results"]]
    expected_ids = [f"row{i}" for i in range(20)]
    assert result_ids == expected_ids


def test_run_with_failing_aggregator() -> None:
    """Safety: Aggregator exception should be handled gracefully or propagate clearly."""
    class BrokenAggregator:
        name = "broken"

        def finalize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
            raise RuntimeError("Aggregator intentionally broken for testing")

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        aggregator_plugins=[BrokenAggregator()],
    )

    df = pd.DataFrame([{"id": "test"}])

    # Current behavior: exception should propagate
    # (This documents current behavior; adjust based on actual implementation)
    with pytest.raises(RuntimeError, match="Aggregator intentionally broken"):
        runner.run(df)
```

**Verification:**
```bash
pytest tests/test_runner_safety.py -v
# Should show 3/3 tests passing (or document actual behavior)
```

**Commit:**
```bash
git add tests/test_runner_safety.py
git commit -m "Test: Add safety tests for edge cases

Cover previously untested scenarios:
- Empty DataFrame handling
- Concurrent execution maintains order
- Aggregator exception handling

These tests close coverage gaps identified in risk assessment."
```

---

### Step 0.4: Capture Baseline Snapshots (30 min)

**Task:** Record current state for comparison

- [ ] Run full test suite and save output
- [ ] Generate coverage report
- [ ] Verify MyPy passes
- [ ] Save baseline files
- [ ] Commit baseline documentation

**Commands:**
```bash
# 1. Full test output
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py \
       -v --tb=short > baseline_tests.txt 2>&1

# 2. Coverage report
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py \
       --cov=src/elspeth/core/experiments/runner \
       --cov-report=html:baseline_coverage \
       --cov-report=term > baseline_coverage.txt 2>&1

# 3. MyPy check
mypy src/elspeth/core/experiments/runner.py > baseline_mypy.txt 2>&1

# 4. Line count
wc -l src/elspeth/core/experiments/runner.py > baseline_lines.txt
```

**Create baseline summary:**
```bash
cat > baseline_summary.md << 'EOF'
# Baseline Snapshot - Before Refactoring

**Date:** $(date)
**Commit:** $(git rev-parse HEAD)
**Branch:** $(git branch --show-current)

## Test Results
Total tests: $(grep -c "PASSED" baseline_tests.txt || echo "See baseline_tests.txt")

## Coverage
See: baseline_coverage/index.html
Text summary: baseline_coverage.txt

## Type Checking
MyPy result: baseline_mypy.txt

## Code Metrics
- Lines: $(cat baseline_lines.txt)
- Complexity: 73 (SonarQube)

## Files
- baseline_tests.txt
- baseline_coverage/ (HTML report)
- baseline_coverage.txt
- baseline_mypy.txt
- baseline_lines.txt
EOF
```

**Verification:**
```bash
cat baseline_summary.md
ls baseline_*
```

**Commit:**
```bash
git add baseline_*.txt baseline_summary.md baseline_coverage/
git commit -m "Docs: Capture baseline state before refactoring

Snapshot includes:
- Test results (27 tests: 18 original + 6 characterization + 3 safety)
- Coverage report (HTML + text)
- MyPy type checking output
- Line count

This baseline allows comparison after refactoring to verify:
- All tests still pass
- Coverage maintained or improved
- No type errors introduced
- Complexity reduced"
```

---

### Phase 0 Completion Checklist

- [ ] All characterization tests pass (6 tests)
- [ ] All safety tests pass (3 tests)
- [ ] Baseline files captured
- [ ] Total tests now: 27 (18 + 6 + 3)
- [ ] All commits pushed to branch

**Verification Command:**
```bash
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py \
       -v | tail -20
```

**Expected Output:**
```
===== 27 passed in X.XXs =====
```

---

## Phase 1: Supporting Classes (2 hours)

**Objective:** Create new dataclasses and helper classes without modifying existing code

**Risk Level:** 🟢 LOW (new code only)
**Estimated Time:** 2 hours

### Step 1.1: Create CheckpointManager Class (45 min)

**Task:** Encapsulate checkpoint logic in dedicated class

- [ ] Add `CheckpointManager` class to runner.py
- [ ] Add unit tests
- [ ] Run tests
- [ ] Commit

**Code to add to `src/elspeth/core/experiments/runner.py`:**

```python
# Add after imports, before ExperimentRunner class

@dataclass
class CheckpointManager:
    """Manages checkpoint loading, tracking, and persistence.

    Provides atomic checkpoint operations with exactly-once semantics for
    row processing tracking.
    """

    path: Path
    field: str
    _processed_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Load existing checkpoint file on initialization."""
        if self.path.exists():
            self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        """Load processed row IDs from checkpoint file."""
        import json

        try:
            with self.path.open("r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self._processed_ids.add(data["id"])
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load checkpoint from {self.path}: {e}")

    def is_processed(self, row_id: str) -> bool:
        """Check if a row has already been processed."""
        return row_id in self._processed_ids

    def mark_processed(self, row_id: str) -> None:
        """Mark a row as processed and persist to checkpoint file."""
        if row_id not in self._processed_ids:
            self._processed_ids.add(row_id)
            self._append_checkpoint(row_id)

    def _append_checkpoint(self, row_id: str) -> None:
        """Append a single checkpoint entry to file."""
        import json

        try:
            with self.path.open("a") as f:
                f.write(json.dumps({"id": row_id}) + "\n")
        except OSError as e:
            logger.error(f"Failed to write checkpoint to {self.path}: {e}")
```

**Unit test to add to `tests/test_runner_characterization.py`:**

```python
def test_checkpoint_manager_tracks_ids(tmp_path: Path) -> None:
    """Unit test: CheckpointManager tracks processed IDs correctly."""
    from elspeth.core.experiments.runner import CheckpointManager

    checkpoint_file = tmp_path / "test.jsonl"
    mgr = CheckpointManager(path=checkpoint_file, field="id")

    # Initially empty
    assert not mgr.is_processed("row1")

    # Mark as processed
    mgr.mark_processed("row1")
    assert mgr.is_processed("row1")

    # Verify persistence
    assert checkpoint_file.exists()
    with checkpoint_file.open("r") as f:
        content = f.read()
        assert '"id": "row1"' in content

    # Load from file
    mgr2 = CheckpointManager(path=checkpoint_file, field="id")
    assert mgr2.is_processed("row1")
    assert not mgr2.is_processed("row2")
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py::test_checkpoint_manager_tracks_ids -v
# Should pass
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py tests/test_runner_characterization.py
git commit -m "Refactor: Add CheckpointManager class (step 1/12)

Encapsulate checkpoint logic in dedicated class:
- Automatic loading from file on init
- is_processed() query method
- mark_processed() with atomic append
- Error handling for file I/O

No changes to existing code yet - just adding new class.
Test coverage: Unit test added."
```

---

### Step 1.2: Create Supporting Dataclasses (45 min)

**Task:** Add dataclasses for structured data flow

- [ ] Add `ExperimentContext` dataclass
- [ ] Add `RowBatch` dataclass
- [ ] Add `ProcessingResult` dataclass
- [ ] Add `ResultHandlers` dataclass
- [ ] Add `ExecutionMetadata` dataclass
- [ ] Run basic validation tests
- [ ] Commit

**Code to add to `src/elspeth/core/experiments/runner.py`:**

```python
# Add after CheckpointManager

@dataclass
class ExperimentContext:
    """Compiled experiment configuration ready for execution."""

    engine: PromptEngine
    system_template: PromptTemplate
    user_template: PromptTemplate
    criteria_templates: dict[str, PromptTemplate]
    checkpoint_manager: CheckpointManager | None
    row_plugins: list[RowExperimentPlugin]


@dataclass
class RowBatch:
    """Collection of rows prepared for processing."""

    rows: list[tuple[int, pd.Series, dict[str, Any], str | None]]

    @property
    def count(self) -> int:
        """Number of rows in batch."""
        return len(self.rows)


@dataclass
class ProcessingResult:
    """Results from row processing execution."""

    records: list[dict[str, Any]]
    failures: list[dict[str, Any]]


@dataclass
class ResultHandlers:
    """Callback handlers for row processing results."""

    on_success: Callable[[int, dict[str, Any], str | None], None]
    on_failure: Callable[[dict[str, Any]], None]


@dataclass
class ExecutionMetadata:
    """Metadata about experiment execution."""

    rows: int
    row_count: int
    retry_summary: dict[str, int] | None = None
    cost_summary: dict[str, Any] | None = None
    failures: list[dict[str, Any]] | None = None
    aggregates: dict[str, Any] | None = None
    security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None
    early_stop: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        from dataclasses import asdict

        return {k: v for k, v in asdict(self).items() if v is not None}
```

**Quick validation test:**
```python
# Add to tests/test_runner_characterization.py

def test_dataclasses_instantiate() -> None:
    """Smoke test: New dataclasses can be instantiated."""
    from elspeth.core.experiments.runner import (
        ExperimentContext,
        RowBatch,
        ProcessingResult,
        ResultHandlers,
        ExecutionMetadata,
    )
    from elspeth.core.prompts import PromptEngine

    # ExperimentContext
    ctx = ExperimentContext(
        engine=PromptEngine(),
        system_template=PromptEngine().compile("test", name="test"),
        user_template=PromptEngine().compile("test", name="test"),
        criteria_templates={},
        checkpoint_manager=None,
        row_plugins=[],
    )
    assert ctx.engine is not None

    # RowBatch
    batch = RowBatch(rows=[])
    assert batch.count == 0

    # ProcessingResult
    result = ProcessingResult(records=[], failures=[])
    assert result.records == []

    # ResultHandlers
    handlers = ResultHandlers(
        on_success=lambda i, r, rid: None,
        on_failure=lambda f: None,
    )
    assert callable(handlers.on_success)

    # ExecutionMetadata
    meta = ExecutionMetadata(rows=0, row_count=0)
    meta_dict = meta.to_dict()
    assert "rows" in meta_dict
    assert "retry_summary" not in meta_dict  # None values omitted
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py::test_dataclasses_instantiate -v
mypy src/elspeth/core/experiments/runner.py
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py tests/test_runner_characterization.py
git commit -m "Refactor: Add supporting dataclasses (step 2/12)

Add typed dataclasses for structured data flow:
- ExperimentContext: Compiled configuration
- RowBatch: Prepared rows with count property
- ProcessingResult: Execution results
- ResultHandlers: Callback functions
- ExecutionMetadata: Metadata with to_dict()

No changes to existing code - just new infrastructure.
Test coverage: Smoke test for instantiation."
```

---

### Step 1.3: Verify Phase 1 Completion (30 min)

**Task:** Ensure all new code integrates correctly

- [ ] Run all tests
- [ ] Check MyPy
- [ ] Review new code
- [ ] Update documentation

**Verification:**
```bash
# All tests
pytest tests/test_runner_characterization.py tests/test_runner_safety.py -v

# Type checking
mypy src/elspeth/core/experiments/runner.py

# Line count (should have increased)
wc -l src/elspeth/core/experiments/runner.py
```

**Phase 1 Checklist:**
- [ ] CheckpointManager class added and tested
- [ ] 5 dataclasses added and tested
- [ ] All existing tests still pass (27/27)
- [ ] MyPy passes with no errors
- [ ] Code committed and pushed

---

## Phase 2: Simple Helper Extractions (3 hours)

**Objective:** Extract simple, focused helper methods from run()

**Risk Level:** 🟢 LOW
**Estimated Time:** 3 hours

### Step 2.1: Extract Retry Summary Calculation (30 min)

**Task:** Extract retry summary logic into helper method

- [ ] Create `_calculate_retry_summary()` method
- [ ] Test the method
- [ ] Replace in `run()` method
- [ ] Run tests
- [ ] Commit

**Code to add to `ExperimentRunner` class:**

```python
def _calculate_retry_summary(self, results: ProcessingResult) -> dict[str, int] | None:
    """Calculate retry statistics from processing results.

    Returns retry summary dict if any retries occurred, None otherwise.
    """
    retry_summary: dict[str, int] = {
        "total_requests": len(results.records) + len(results.failures),
        "total_retries": 0,
        "exhausted": len(results.failures),
    }

    retry_present = False

    # Count retries in successful results
    for record in results.records:
        info = record.get("retry")
        if info:
            retry_present = True
            attempts = int(info.get("attempts", 1))
            retry_summary["total_retries"] += max(attempts - 1, 0)

    # Count retries in failures
    for failure in results.failures:
        info = failure.get("retry")
        if info:
            retry_present = True
            attempts = int(info.get("attempts", 0))
            retry_summary["total_retries"] += max(attempts - 1, 0)

    return retry_summary if retry_present else None
```

**Replace in run() method (around lines 197-216):**
```python
# BEFORE:
retry_summary: dict[str, int] = {
    "total_requests": len(results) + len(failures),
    "total_retries": 0,
    "exhausted": len(failures),
}
retry_present = False
for record in results:
    info = record.get("retry")
    if info:
        retry_present = True
        attempts = int(info.get("attempts", 1))
        retry_summary["total_retries"] += max(attempts - 1, 0)
for failure in failures:
    info = failure.get("retry")
    if info:
        retry_present = True
        attempts = int(info.get("attempts", 0))
        retry_summary["total_retries"] += max(attempts - 1, 0)
if retry_present:
    metadata["retry_summary"] = retry_summary

# AFTER (using ProcessingResult):
# (Note: Will need to update to use ProcessingResult in later step)
retry_summary = self._calculate_retry_summary(ProcessingResult(records=results, failures=failures))
if retry_summary:
    metadata["retry_summary"] = retry_summary
```

**Test:**
```python
# Add to tests/test_runner_characterization.py

def test_calculate_retry_summary_no_retries() -> None:
    """Unit: _calculate_retry_summary returns None when no retries."""
    from elspeth.core.experiments.runner import ExperimentRunner, ProcessingResult

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Test",
    )

    result = ProcessingResult(
        records=[{"data": "test"}],
        failures=[],
    )

    summary = runner._calculate_retry_summary(result)
    assert summary is None


def test_calculate_retry_summary_with_retries() -> None:
    """Unit: _calculate_retry_summary counts retries correctly."""
    from elspeth.core.experiments.runner import ExperimentRunner, ProcessingResult

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Test",
    )

    result = ProcessingResult(
        records=[
            {"retry": {"attempts": 3}},  # 2 retries
            {"retry": {"attempts": 1}},  # 0 retries
        ],
        failures=[
            {"retry": {"attempts": 2}},  # 1 retry
        ],
    )

    summary = runner._calculate_retry_summary(result)
    assert summary is not None
    assert summary["total_requests"] == 3
    assert summary["total_retries"] == 3  # 2 + 0 + 1
    assert summary["exhausted"] == 1
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py::test_calculate_retry_summary -v
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py tests/test_runner_characterization.py
git commit -m "Refactor: Extract _calculate_retry_summary() (step 3/12)

Extract retry summary calculation into focused helper method.

Complexity reduction: ~8 from run() method
Test coverage: 2 unit tests added
All existing tests pass: 29/29"
```

---

### Step 2.2: Extract Security Level Resolution (20 min)

**Task:** Extract security level resolution logic

- [ ] Create `_resolve_security_level()` method
- [ ] Create `_resolve_determinism_level()` method
- [ ] Replace in `run()` method
- [ ] Run tests
- [ ] Commit

**Code:**
```python
def _resolve_security_level(self, df: pd.DataFrame) -> SecurityLevel:
    """Resolve final security level from DataFrame and configuration."""
    df_security_level = getattr(df, "attrs", {}).get("security_level") if hasattr(df, "attrs") else None
    self._active_security_level = resolve_security_level(self.security_level, df_security_level)
    return self._active_security_level


def _resolve_determinism_level(self, df: pd.DataFrame) -> DeterminismLevel:
    """Resolve final determinism level from DataFrame and configuration."""
    df_determinism_level = getattr(df, "attrs", {}).get("determinism_level") if hasattr(df, "attrs") else None
    self._active_determinism_level = resolve_determinism_level(self.determinism_level, df_determinism_level)
    return self._active_determinism_level
```

**Replace in run() (lines 228-234):**
```python
# BEFORE:
df_security_level = getattr(df, "attrs", {}).get("security_level") if hasattr(df, "attrs") else None
self._active_security_level = resolve_security_level(self.security_level, df_security_level)
metadata["security_level"] = self._active_security_level

df_determinism_level = getattr(df, "attrs", {}).get("determinism_level") if hasattr(df, "attrs") else None
self._active_determinism_level = resolve_determinism_level(self.determinism_level, df_determinism_level)
metadata["determinism_level"] = self._active_determinism_level

# AFTER:
metadata["security_level"] = self._resolve_security_level(df)
metadata["determinism_level"] = self._resolve_determinism_level(df)
```

**Verification:**
```bash
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py
git commit -m "Refactor: Extract security/determinism resolution (step 4/12)

Extract level resolution into focused helper methods:
- _resolve_security_level()
- _resolve_determinism_level()

Complexity reduction: ~4 from run() method
All tests pass: 29/29"
```

---

### Step 2.3: Extract Prompt Compilation (30 min)

**Task:** Extract prompt compilation logic

- [ ] Create `_compile_system_prompt()` method
- [ ] Create `_compile_user_prompt()` method
- [ ] Create `_compile_criteria_prompts()` method
- [ ] Run tests
- [ ] Commit

**Code:**
```python
def _compile_system_prompt(self, engine: PromptEngine) -> PromptTemplate:
    """Compile system prompt template."""
    return engine.compile(
        self.prompt_system or "",
        name=f"{self.experiment_name or 'experiment'}:system",
        defaults=self.prompt_defaults or {},
    )


def _compile_user_prompt(self, engine: PromptEngine) -> PromptTemplate:
    """Compile user prompt template."""
    return engine.compile(
        self.prompt_template or "",
        name=f"{self.experiment_name or 'experiment'}:user",
        defaults=self.prompt_defaults or {},
    )


def _compile_criteria_prompts(self, engine: PromptEngine) -> dict[str, PromptTemplate]:
    """Compile criteria prompt templates."""
    criteria_templates: dict[str, PromptTemplate] = {}

    if not self.criteria:
        return criteria_templates

    for crit in self.criteria:
        template_text = crit.get("template", self.prompt_template or "")
        crit_name = crit.get("name") or template_text
        defaults = dict(self.prompt_defaults or {})
        defaults.update(crit.get("defaults", {}))
        criteria_templates[crit_name] = engine.compile(
            template_text,
            name=f"{self.experiment_name or 'experiment'}:criteria:{crit_name}",
            defaults=defaults,
        )

    return criteria_templates
```

**Replace in run() (lines 86-112):**
```python
# BEFORE:
engine = self.prompt_engine or PromptEngine()
system_template = engine.compile(
    self.prompt_system or "",
    name=f"{self.experiment_name or 'experiment'}:system",
    defaults=self.prompt_defaults or {},
)
user_template = engine.compile(
    self.prompt_template or "",
    name=f"{self.experiment_name or 'experiment'}:user",
    defaults=self.prompt_defaults or {},
)
criteria_templates: dict[str, PromptTemplate] = {}
if self.criteria:
    for crit in self.criteria:
        template_text = crit.get("template", self.prompt_template or "")
        crit_name = crit.get("name") or template_text
        defaults = dict(self.prompt_defaults or {})
        defaults.update(crit.get("defaults", {}))
        criteria_templates[crit_name] = engine.compile(
            template_text,
            name=f"{self.experiment_name or 'experiment'}:criteria:{crit_name}",
            defaults=defaults,
        )
self._compiled_system_prompt = system_template
self._compiled_user_prompt = user_template
self._compiled_criteria_prompts = criteria_templates

# AFTER:
engine = self.prompt_engine or PromptEngine()
system_template = self._compile_system_prompt(engine)
user_template = self._compile_user_prompt(engine)
criteria_templates = self._compile_criteria_prompts(engine)
self._compiled_system_prompt = system_template
self._compiled_user_prompt = user_template
self._compiled_criteria_prompts = criteria_templates
```

**Verification:**
```bash
pytest tests/test_experiments.py::test_experiment_runner_jinja_prompts -v
pytest tests/test_experiments.py::test_experiment_runner_with_criteria -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py
git commit -m "Refactor: Extract prompt compilation methods (step 5/12)

Extract prompt compilation into focused methods:
- _compile_system_prompt()
- _compile_user_prompt()
- _compile_criteria_prompts()

Complexity reduction: ~12 from run() method
All tests pass: 29/29"
```

---

### Step 2.4: Extract Aggregation (20 min)

**Task:** Extract aggregation logic

- [ ] Create `_run_aggregators()` method
- [ ] Replace in `run()` method
- [ ] Run tests
- [ ] Commit

**Code:**
```python
def _run_aggregators(self, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute aggregation plugins on results.

    Returns dict mapping aggregator name to derived data.
    """
    aggregates: dict[str, Any] = {}

    for plugin in self.aggregator_plugins or []:
        derived = plugin.finalize(results)
        if not derived:
            continue

        # Standardize: ensure failures key exists
        if isinstance(derived, dict) and "failures" not in derived:
            derived["failures"] = []

        aggregates[plugin.name] = derived

    return aggregates
```

**Replace in run() (lines 182-191):**
```python
# BEFORE:
aggregates: dict[str, Any] = {}
for plugin in self.aggregator_plugins or []:
    derived = plugin.finalize(results)
    if derived:
        if isinstance(derived, dict) and "failures" not in derived:
            derived["failures"] = []
        aggregates[plugin.name] = derived
if aggregates:
    payload["aggregates"] = aggregates

# AFTER:
aggregates = self._run_aggregators(results)
if aggregates:
    payload["aggregates"] = aggregates
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py::test_run_aggregator_receives_complete_results -v
pytest tests/test_experiments.py::test_experiment_runner_plugins -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py
git commit -m "Refactor: Extract _run_aggregators() (step 6/12)

Extract aggregation logic into focused method.

Complexity reduction: ~5 from run() method
All tests pass: 29/29"
```

---

### Phase 2 Completion Checklist

- [ ] 4 extraction steps completed
- [ ] All tests pass (29/29)
- [ ] MyPy passes
- [ ] Complexity reduced by ~29 points so far
- [ ] Code committed and pushed

**Verification:**
```bash
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py tests/test_runner_safety.py -v
mypy src/elspeth/core/experiments/runner.py
```

---

## Phase 3: Complex Method Extractions (4 hours)

**Objective:** Extract larger, more complex method groups from run()

**Risk Level:** 🟡 MEDIUM
**Estimated Time:** 4 hours

### Step 3.1: Extract Row Preparation Logic (60 min)

**Task:** Extract checkpoint loading and row batch preparation

- [ ] Create `_prepare_row_batch()` method
- [ ] Test with checkpoints
- [ ] Replace in `run()` method
- [ ] Run all tests
- [ ] Commit

**Code:**
```python
def _prepare_row_batch(
    self,
    df: pd.DataFrame,
    checkpoint_manager: CheckpointManager | None,
) -> RowBatch:
    """Prepare rows for processing, applying checkpoint filtering.

    Returns RowBatch containing tuples of (index, row, context, row_id).
    """
    rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]] = []

    for idx, row_series in df.iterrows():
        row_dict = row_series.to_dict()

        # Determine row ID for checkpointing
        row_id: str | None = None
        if checkpoint_manager:
            checkpoint_field = checkpoint_manager.field
            if checkpoint_field in row_dict:
                row_id = str(row_dict[checkpoint_field])

                # Skip if already processed
                if checkpoint_manager.is_processed(row_id):
                    logger.debug(f"Skipping already processed row: {row_id}")
                    continue

        rows_to_process.append((int(idx), row_series, row_dict, row_id))

    return RowBatch(rows=rows_to_process)
```

**Replace in run() (lines 115-132):**
```python
# BEFORE:
checkpoint_manager: CheckpointManager | None = None
if self.checkpoint_config:
    checkpoint_path = Path(self.checkpoint_config["path"])
    checkpoint_field = self.checkpoint_config["field"]
    checkpoint_manager = CheckpointManager(path=checkpoint_path, field=checkpoint_field)

rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]] = []
for idx, row_series in df.iterrows():
    row_dict = row_series.to_dict()
    row_id: str | None = None
    if checkpoint_manager:
        if checkpoint_field in row_dict:
            row_id = str(row_dict[checkpoint_field])
            if checkpoint_manager.is_processed(row_id):
                logger.debug(f"Skipping already processed row: {row_id}")
                continue
    rows_to_process.append((int(idx), row_series, row_dict, row_id))

# AFTER:
checkpoint_manager: CheckpointManager | None = None
if self.checkpoint_config:
    checkpoint_path = Path(self.checkpoint_config["path"])
    checkpoint_field = self.checkpoint_config["field"]
    checkpoint_manager = CheckpointManager(path=checkpoint_path, field=checkpoint_field)

batch = self._prepare_row_batch(df, checkpoint_manager)
rows_to_process = batch.rows
```

**Test:**
```python
# Add to tests/test_runner_characterization.py

def test_prepare_row_batch_no_checkpoint(simple_runner: ExperimentRunner) -> None:
    """Unit: _prepare_row_batch without checkpointing returns all rows."""
    df = pd.DataFrame([{"id": "A"}, {"id": "B"}, {"id": "C"}])

    batch = simple_runner._prepare_row_batch(df, checkpoint_manager=None)

    assert batch.count == 3
    assert len(batch.rows) == 3


def test_prepare_row_batch_with_checkpoint_filtering(tmp_path: Path) -> None:
    """Unit: _prepare_row_batch filters already processed rows."""
    from elspeth.core.experiments.runner import CheckpointManager

    checkpoint_file = tmp_path / "test.jsonl"
    mgr = CheckpointManager(path=checkpoint_file, field="id")
    mgr.mark_processed("A")  # Mark A as processed

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Test",
    )

    df = pd.DataFrame([{"id": "A"}, {"id": "B"}, {"id": "C"}])
    batch = runner._prepare_row_batch(df, checkpoint_manager=mgr)

    # Should only have B and C (A was filtered)
    assert batch.count == 2
    row_ids = [row[3] for row in batch.rows]
    assert row_ids == ["B", "C"]
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py::test_prepare_row_batch -v
pytest tests/test_runner_characterization.py::test_run_checkpoint_idempotency -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py tests/test_runner_characterization.py
git commit -m "Refactor: Extract _prepare_row_batch() (step 7/12)

Extract row preparation and checkpoint filtering logic.

Complexity reduction: ~10 from run() method
Test coverage: 2 unit tests added
All tests pass: 31/31"
```

---

### Step 3.2: Extract Row Processing Orchestration (90 min)

**Task:** Extract the complex row processing loop with retries and early stopping

- [ ] Create `_execute_row_processing()` method
- [ ] Create `_process_single_row()` helper
- [ ] Test both methods
- [ ] Replace in `run()` method
- [ ] Run all tests
- [ ] Commit

**Code:**
```python
def _execute_row_processing(
    self,
    batch: RowBatch,
    system_template: PromptTemplate,
    user_template: PromptTemplate,
    criteria_templates: dict[str, PromptTemplate],
    row_plugins: list,
    checkpoint_manager: CheckpointManager | None,
) -> tuple[ProcessingResult, dict[str, Any] | None]:
    """Execute row processing with retries and early stopping.

    Returns (ProcessingResult, early_stop_info).
    """
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    early_stop_info: dict[str, Any] | None = None

    # Result handlers for callback functions
    def on_success(idx: int, record: dict[str, Any], row_id: str | None) -> None:
        results.append(record)
        if checkpoint_manager and row_id:
            checkpoint_manager.mark_processed(row_id)

    def on_failure(failure: dict[str, Any]) -> None:
        failures.append(failure)

    handlers = ResultHandlers(on_success=on_success, on_failure=on_failure)

    # Process rows with ThreadPoolExecutor if configured
    max_workers = (self.concurrency_config or {}).get("max_workers", 1)

    if max_workers > 1:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for idx, row_series, row_dict, row_id in batch.rows:
                future = executor.submit(
                    self._process_single_row,
                    idx,
                    row_series,
                    row_dict,
                    row_id,
                    system_template,
                    user_template,
                    criteria_templates,
                    row_plugins,
                    handlers,
                )
                futures.append((idx, future))

            # Collect results in order
            for idx, future in sorted(futures, key=lambda x: x[0]):
                early_stop = future.result()
                if early_stop:
                    early_stop_info = early_stop
                    break
    else:
        # Sequential execution
        for idx, row_series, row_dict, row_id in batch.rows:
            early_stop = self._process_single_row(
                idx,
                row_series,
                row_dict,
                row_id,
                system_template,
                user_template,
                criteria_templates,
                row_plugins,
                handlers,
            )
            if early_stop:
                early_stop_info = early_stop
                break

    return ProcessingResult(records=results, failures=failures), early_stop_info


def _process_single_row(
    self,
    idx: int,
    row_series: pd.Series,
    row_dict: dict[str, Any],
    row_id: str | None,
    system_template: PromptTemplate,
    user_template: PromptTemplate,
    criteria_templates: dict[str, PromptTemplate],
    row_plugins: list,
    handlers: ResultHandlers,
) -> dict[str, Any] | None:
    """Process a single row with retry logic and early stop checking.

    Returns early_stop info if triggered, None otherwise.
    """
    # Render prompts
    system_prompt = system_template.render(row_dict)
    user_prompt = user_template.render(row_dict)

    # Execute with retry logic
    record: dict[str, Any] | None = None
    retry_config = self.retry_config or {}
    max_attempts = retry_config.get("max_attempts", 1)

    for attempt in range(1, max_attempts + 1):
        try:
            # Call LLM
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                metadata={"row_index": idx, "row_id": row_id or str(idx)},
            )

            # Build record
            record = {
                "context": row_dict,
                "response": response.get("content"),
                "raw": response.get("raw"),
                "row_index": idx,
            }

            # Add retry info if retried
            if attempt > 1:
                record["retry"] = {"attempts": attempt}

            # Run row processors
            for plugin in row_plugins:
                if hasattr(plugin, "process"):
                    plugin.process(record, metadata={"row_index": idx})

            # Success - call handler
            handlers.on_success(idx, record, row_id)
            break

        except Exception as e:
            logger.warning(f"Row {idx} attempt {attempt}/{max_attempts} failed: {e}")
            if attempt >= max_attempts:
                # All retries exhausted - record failure
                failure = {
                    "context": row_dict,
                    "error": str(e),
                    "row_index": idx,
                    "retry": {"attempts": attempt},
                }
                handlers.on_failure(failure)
                record = None
            else:
                # Will retry
                continue

    # Early stop check
    if record and self.early_stop_plugins:
        for plugin in self.early_stop_plugins:
            stop_signal = plugin.check(record, metadata={"row_index": idx})
            if stop_signal:
                return {
                    "reason": stop_signal.get("reason", "unknown"),
                    "row_index": idx,
                    "plugin": plugin.name,
                }

    return None
```

**Replace in run() (lines 135-175 approximately):**
```python
# BEFORE: [Large complex processing loop with ThreadPoolExecutor, retries, etc.]

# AFTER:
result, early_stop_info = self._execute_row_processing(
    batch=batch,
    system_template=system_template,
    user_template=user_template,
    criteria_templates=criteria_templates,
    row_plugins=self.row_processor_plugins or [],
    checkpoint_manager=checkpoint_manager,
)
results = result.records
failures = result.failures
```

**Test:**
```python
# Add to tests/test_runner_characterization.py

def test_execute_row_processing_sequential() -> None:
    """Unit: _execute_row_processing handles sequential execution."""
    from elspeth.core.experiments.runner import ExperimentRunner, RowBatch
    from elspeth.core.prompts import PromptEngine

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
    )

    engine = PromptEngine()
    system_tpl = engine.compile("Test", name="test")
    user_tpl = engine.compile("Process {{ id }}", name="test")

    df = pd.DataFrame([{"id": "A"}, {"id": "B"}])
    batch = runner._prepare_row_batch(df, checkpoint_manager=None)

    result, early_stop = runner._execute_row_processing(
        batch=batch,
        system_template=system_tpl,
        user_template=user_tpl,
        criteria_templates={},
        row_plugins=[],
        checkpoint_manager=None,
    )

    assert result.records == 2
    assert len(result.failures) == 0
    assert early_stop is None
```

**Verification:**
```bash
pytest tests/test_runner_characterization.py -v
pytest tests/test_experiments.py -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py tests/test_runner_characterization.py
git commit -m "Refactor: Extract row processing orchestration (step 8/12)

Extract complex row processing loop:
- _execute_row_processing(): Main orchestration
- _process_single_row(): Single row with retries

Complexity reduction: ~35 from run() method
Test coverage: 1 integration test added
All tests pass: 32/32"
```

---

### Step 3.3: Extract Metadata Assembly (30 min)

**Task:** Extract metadata building logic

- [ ] Create `_build_execution_metadata()` method
- [ ] Replace in `run()` method
- [ ] Run tests
- [ ] Commit

**Code:**
```python
def _build_execution_metadata(
    self,
    df: pd.DataFrame,
    result: ProcessingResult,
    aggregates: dict[str, Any],
    early_stop_info: dict[str, Any] | None = None,
) -> ExecutionMetadata:
    """Build execution metadata from processing results.

    Includes counts, security levels, retry summary, and aggregate info.
    """
    retry_summary = self._calculate_retry_summary(result)

    # Build base metadata
    metadata = ExecutionMetadata(
        rows=len(result.records),
        row_count=len(df),
        security_level=self._active_security_level,
        determinism_level=self._active_determinism_level,
    )

    # Add optional fields
    if retry_summary:
        metadata.retry_summary = retry_summary

    if result.failures:
        metadata.failures = result.failures

    if aggregates:
        metadata.aggregates = aggregates

    if early_stop_info:
        metadata.early_stop = early_stop_info

    # Cost tracking (if available)
    if hasattr(self.llm_client, "get_cost_summary"):
        metadata.cost_summary = self.llm_client.get_cost_summary()

    return metadata
```

**Replace in run() (lines 193-238):**
```python
# BEFORE: [Metadata dict building with multiple conditionals]

# AFTER:
metadata = self._build_execution_metadata(df, result, aggregates, early_stop_info)
```

**Verification:**
```bash
pytest tests/test_experiments.py -v
pytest tests/test_runner_characterization.py::test_run_result_structure -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py
git commit -m "Refactor: Extract _build_execution_metadata() (step 9/12)

Extract metadata assembly into focused method.

Complexity reduction: ~15 from run() method
All tests pass: 32/32"
```

---

### Step 3.4: Extract Sink Dispatch (20 min)

**Task:** Extract sink dispatching logic

- [ ] Create `_dispatch_to_sinks()` method
- [ ] Replace in `run()` method
- [ ] Run tests
- [ ] Commit

**Code:**
```python
def _dispatch_to_sinks(
    self,
    payload: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Dispatch results payload to all configured sinks.

    Sinks receive both payload and metadata for writing.
    """
    for sink in self.sinks or []:
        try:
            sink.write(payload, metadata=metadata)
        except Exception as e:
            logger.error(f"Sink {sink.__class__.__name__} failed: {e}")
            # Continue to other sinks even if one fails
```

**Replace in run() (lines 240-242):**
```python
# BEFORE:
for sink in self.sinks or []:
    sink.write(payload, metadata=metadata)

# AFTER:
self._dispatch_to_sinks(payload, metadata.to_dict())
```

**Verification:**
```bash
pytest tests/test_experiments.py::test_experiment_runner_sinks -v
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py
git commit -m "Refactor: Extract _dispatch_to_sinks() (step 10/12)

Extract sink dispatching with error isolation.

Complexity reduction: ~3 from run() method
All tests pass: 32/32"
```

---

### Phase 3 Completion Checklist

- [ ] 4 complex extractions completed
- [ ] All tests pass (32/32)
- [ ] MyPy passes
- [ ] Complexity reduced significantly (~63 points total)
- [ ] Code committed and pushed

**Verification:**
```bash
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py tests/test_runner_safety.py -v
mypy src/elspeth/core/experiments/runner.py
```

---

## Phase 4: Refactor Main Method (1 hour)

**Objective:** Simplify run() to orchestrate helper methods (Template Method pattern)

**Risk Level:** 🟡 MEDIUM
**Estimated Time:** 1 hour

### Step 4.1: Restructure run() Method (45 min)

**Task:** Replace inline logic with calls to helper methods

- [ ] Refactor run() to call extracted methods
- [ ] Simplify control flow
- [ ] Run all tests
- [ ] Commit

**Final run() method structure:**

```python
def run(self, df: pd.DataFrame) -> dict[str, Any]:
    """Execute experiment on DataFrame with LLM processing.

    Template method orchestrating:
    1. Prompt compilation
    2. Row preparation with checkpoint filtering
    3. Row processing with retries and early stopping
    4. Aggregation
    5. Metadata assembly
    6. Sink dispatch

    Args:
        df: DataFrame with rows to process

    Returns:
        Results payload with metadata
    """
    # 1. Compile prompts
    engine = self.prompt_engine or PromptEngine()
    system_template = self._compile_system_prompt(engine)
    user_template = self._compile_user_prompt(engine)
    criteria_templates = self._compile_criteria_prompts(engine)

    # Cache compiled templates
    self._compiled_system_prompt = system_template
    self._compiled_user_prompt = user_template
    self._compiled_criteria_prompts = criteria_templates

    # 2. Prepare rows with checkpoint filtering
    checkpoint_manager: CheckpointManager | None = None
    if self.checkpoint_config:
        checkpoint_path = Path(self.checkpoint_config["path"])
        checkpoint_field = self.checkpoint_config["field"]
        checkpoint_manager = CheckpointManager(path=checkpoint_path, field=checkpoint_field)

    batch = self._prepare_row_batch(df, checkpoint_manager)

    # 3. Execute row processing
    result, early_stop_info = self._execute_row_processing(
        batch=batch,
        system_template=system_template,
        user_template=user_template,
        criteria_templates=criteria_templates,
        row_plugins=self.row_processor_plugins or [],
        checkpoint_manager=checkpoint_manager,
    )

    # 4. Run aggregators
    aggregates = self._run_aggregators(result.records)

    # 5. Build metadata
    metadata = self._build_execution_metadata(df, result, aggregates, early_stop_info)

    # 6. Assemble payload
    payload: dict[str, Any] = {
        "results": result.records,
        "failures": result.failures,
        "metadata": metadata.to_dict(),
    }

    if aggregates:
        payload["aggregates"] = aggregates

    # 7. Dispatch to sinks
    self._dispatch_to_sinks(payload, metadata.to_dict())

    # 8. Cleanup
    self._active_security_level = None
    self._active_determinism_level = None

    return payload
```

**Verification:**
```bash
# Full test suite
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py -v

# Type checking
mypy src/elspeth/core/experiments/runner.py

# Line count (should be significantly reduced)
wc -l src/elspeth/core/experiments/runner.py
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py
git commit -m "Refactor: Simplify run() to orchestration method (step 11/12)

Transform run() into clean Template Method:
- 8 focused orchestration steps
- Calls to 10 extracted helper methods
- Clear control flow with comments

Before: 171 lines, complexity 73
After: ~50 lines, complexity ~8

All tests pass: 32/32"
```

---

### Step 4.2: Documentation and Cleanup (15 min)

**Task:** Update docstrings and clean up dead code

- [ ] Update run() docstring
- [ ] Review all helper method docstrings
- [ ] Remove any dead code
- [ ] Run tests
- [ ] Commit

**Actions:**
```bash
# 1. Review docstrings
grep -A 5 "def run\|def _" src/elspeth/core/experiments/runner.py | less

# 2. Check for unused imports
mypy src/elspeth/core/experiments/runner.py

# 3. Format code
black src/elspeth/core/experiments/runner.py
```

**Commit:**
```bash
git add src/elspeth/core/experiments/runner.py
git commit -m "Docs: Update docstrings after refactoring (step 12/12)

- Enhanced run() docstring with orchestration steps
- Verified all helper method docstrings
- Cleaned up formatting
- All tests pass: 32/32"
```

---

### Phase 4 Completion Checklist

- [ ] run() simplified to ~50 lines
- [ ] All helper methods documented
- [ ] All tests pass (32/32)
- [ ] MyPy passes
- [ ] Code formatted
- [ ] Code committed and pushed

**Verification:**
```bash
pytest tests/ -v -k "test_experiments or test_runner"
mypy src/elspeth/core/experiments/runner.py
```

---

## Phase 5: Testing & Validation (3 hours)

**Objective:** Comprehensive validation before merge

**Risk Level:** 🟢 LOW (read-only validation)
**Estimated Time:** 3 hours

### Step 5.1: Baseline Comparison (30 min)

**Task:** Compare against baseline snapshots

- [ ] Run full test suite
- [ ] Generate new coverage report
- [ ] Compare test results
- [ ] Compare coverage
- [ ] Document changes

**Commands:**
```bash
# 1. Test results
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py \
       -v --tb=short > after_refactor_tests.txt 2>&1

# 2. Coverage
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py \
       --cov=src/elspeth/core/experiments/runner \
       --cov-report=html:after_refactor_coverage \
       --cov-report=term > after_refactor_coverage.txt 2>&1

# 3. Type checking
mypy src/elspeth/core/experiments/runner.py > after_refactor_mypy.txt 2>&1

# 4. Line count
wc -l src/elspeth/core/experiments/runner.py > after_refactor_lines.txt

# 5. Compare
echo "=== TEST COMPARISON ===" > refactor_comparison.txt
echo "Before:" >> refactor_comparison.txt
grep "passed" baseline_tests.txt >> refactor_comparison.txt
echo "After:" >> refactor_comparison.txt
grep "passed" after_refactor_tests.txt >> refactor_comparison.txt
echo "" >> refactor_comparison.txt

echo "=== COVERAGE COMPARISON ===" >> refactor_comparison.txt
echo "Before:" >> refactor_comparison.txt
grep "TOTAL" baseline_coverage.txt >> refactor_comparison.txt
echo "After:" >> refactor_comparison.txt
grep "TOTAL" after_refactor_coverage.txt >> refactor_comparison.txt
echo "" >> refactor_comparison.txt

echo "=== LINE COUNT ===" >> refactor_comparison.txt
echo "Before:" >> refactor_comparison.txt
cat baseline_lines.txt >> refactor_comparison.txt
echo "After:" >> refactor_comparison.txt
cat after_refactor_lines.txt >> refactor_comparison.txt

# View comparison
cat refactor_comparison.txt
```

**Expected Results:**
- ✅ All tests still pass (32/32)
- ✅ Coverage maintained or improved (≥89%)
- ✅ MyPy: no errors
- ✅ Line count reduced (from 765 to ~400-500)

**Commit:**
```bash
git add after_refactor_*.txt refactor_comparison.txt
git commit -m "Docs: Add post-refactoring baseline comparison

Compare before/after metrics:
- Tests: 18 → 32 (all passing)
- Coverage: 89% → maintained
- Lines: 765 → ~450
- Complexity: 73 → ~8"
```

---

### Step 5.2: Manual Testing (45 min)

**Task:** Execute manual smoke tests

- [ ] Run sample experiment
- [ ] Verify checkpointing works
- [ ] Test with failures
- [ ] Test with aggregators
- [ ] Test with early stop

**Test Script:**
```python
# Create: manual_test_refactor.py

"""Manual smoke test for refactored ExperimentRunner."""

import pandas as pd
from elspeth.core.experiments.runner import ExperimentRunner


class SimpleLLM:
    def generate(self, *, system_prompt, user_prompt, metadata=None):
        return {
            "content": f"Processed: {metadata.get('row_id')}",
            "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        }


class CountAggregator:
    name = "counter"

    def finalize(self, results):
        return {"count": len(results)}


# Test 1: Basic execution
print("Test 1: Basic execution...")
runner = ExperimentRunner(
    llm_client=SimpleLLM(),
    sinks=[],
    prompt_system="You are a test.",
    prompt_template="Process: {{ field }}",
)

df = pd.DataFrame([{"field": f"row{i}"} for i in range(5)])
result = runner.run(df)

assert len(result["results"]) == 5
assert len(result["failures"]) == 0
print("✅ Test 1 passed")

# Test 2: With aggregator
print("\nTest 2: With aggregator...")
runner2 = ExperimentRunner(
    llm_client=SimpleLLM(),
    sinks=[],
    prompt_system="Test",
    prompt_template="Test",
    aggregator_plugins=[CountAggregator()],
)

result2 = runner2.run(df)
assert "aggregates" in result2
assert result2["aggregates"]["counter"]["count"] == 5
print("✅ Test 2 passed")

# Test 3: With checkpointing
print("\nTest 3: With checkpointing...")
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    checkpoint_file = Path(tmpdir) / "test.jsonl"

    runner3 = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Test",
        checkpoint_config={"path": str(checkpoint_file), "field": "id"},
    )

    df_check = pd.DataFrame([{"id": "A"}, {"id": "B"}, {"id": "C"}])

    # First run
    result3a = runner3.run(df_check)
    assert len(result3a["results"]) == 3

    # Second run - all checkpointed
    result3b = runner3.run(df_check)
    assert len(result3b["results"]) == 0
    print("✅ Test 3 passed")

print("\n🎉 All manual tests passed!")
```

**Run:**
```bash
python manual_test_refactor.py
```

**Expected Output:**
```
Test 1: Basic execution...
✅ Test 1 passed

Test 2: With aggregator...
✅ Test 2 passed

Test 3: With checkpointing...
✅ Test 3 passed

🎉 All manual tests passed!
```

---

### Step 5.3: Performance Testing (30 min)

**Task:** Verify no performance regression

- [ ] Create benchmark script
- [ ] Run baseline benchmark
- [ ] Compare results
- [ ] Document findings

**Benchmark Script:**
```python
# Create: benchmark_refactor.py

"""Performance benchmark for refactored runner."""

import time
import pandas as pd
from elspeth.core.experiments.runner import ExperimentRunner


class BenchmarkLLM:
    def __init__(self):
        self.call_count = 0

    def generate(self, *, system_prompt, user_prompt, metadata=None):
        self.call_count += 1
        # Simulate small latency
        time.sleep(0.01)
        return {"content": "test", "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}}


def benchmark(row_count: int, workers: int = 1) -> float:
    """Run benchmark with given configuration."""
    llm = BenchmarkLLM()
    runner = ExperimentRunner(
        llm_client=llm,
        sinks=[],
        prompt_system="Test",
        prompt_template="Test {{ id }}",
        concurrency_config={"max_workers": workers} if workers > 1 else None,
    )

    df = pd.DataFrame([{"id": i} for i in range(row_count)])

    start = time.time()
    result = runner.run(df)
    duration = time.time() - start

    assert len(result["results"]) == row_count
    return duration


if __name__ == "__main__":
    print("Running performance benchmarks...")
    print("=" * 60)

    # Benchmark 1: Sequential processing
    print("\nBenchmark 1: 50 rows, sequential")
    t1 = benchmark(50, workers=1)
    print(f"  Duration: {t1:.2f}s")

    # Benchmark 2: Parallel processing
    print("\nBenchmark 2: 50 rows, 5 workers")
    t2 = benchmark(50, workers=5)
    print(f"  Duration: {t2:.2f}s")
    print(f"  Speedup: {t1/t2:.2f}x")

    # Benchmark 3: Large dataset
    print("\nBenchmark 3: 200 rows, 10 workers")
    t3 = benchmark(200, workers=10)
    print(f"  Duration: {t3:.2f}s")

    print("\n" + "=" * 60)
    print("✅ Benchmarks complete!")
```

**Run:**
```bash
python benchmark_refactor.py > benchmark_results.txt 2>&1
cat benchmark_results.txt
```

**Acceptance Criteria:**
- Sequential processing: < 1s for 50 rows
- Parallel speedup: > 3x with 5 workers
- No crashes or errors

---

### Step 5.4: Integration Test Suite (30 min)

**Task:** Run full integration test suite

- [ ] Run all experiment tests
- [ ] Run integration tests
- [ ] Run characterization tests
- [ ] Run safety tests
- [ ] Verify all pass

**Commands:**
```bash
# Full suite with verbose output
pytest tests/ -v -k "experiment" --tb=short

# With coverage
pytest tests/ -k "experiment" --cov=src/elspeth/core/experiments --cov-report=term-missing

# Check for flaky tests (run 3 times)
for i in {1..3}; do
  echo "Run $i:"
  pytest tests/test_experiments.py tests/test_experiment_runner_integration.py \
         tests/test_runner_characterization.py tests/test_runner_safety.py -q
done
```

**Expected Results:**
- ✅ All tests pass: 32/32
- ✅ No flaky tests (consistent across runs)
- ✅ Coverage ≥ 89%

---

### Step 5.5: Code Quality Check (30 min)

**Task:** Verify code quality improvements

- [ ] Run linters
- [ ] Check complexity metrics
- [ ] Verify type coverage
- [ ] Document quality improvements

**Commands:**
```bash
# 1. Ruff linting
python -m ruff check src/elspeth/core/experiments/runner.py

# 2. MyPy type checking
python -m mypy src/elspeth/core/experiments/runner.py --strict

# 3. Complexity (if you have radon)
# pip install radon
radon cc src/elspeth/core/experiments/runner.py -a

# 4. Generate quality report
cat > quality_report.md << 'EOF'
# Code Quality Report - Post Refactoring

## Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Lines | 765 | ~450 | -41% |
| Complexity (run) | 73 | ~8 | -89% |
| Test Count | 18 | 32 | +78% |
| Coverage | 89% | ≥89% | ✅ |
| Type Errors | 0 | 0 | ✅ |
| Lint Warnings | TBD | 0 | ✅ |

## New Structure

### Public Methods
- `run()` - Main orchestration (complexity ~8)

### Private Helpers (New)
1. `_compile_system_prompt()` - Complexity ~2
2. `_compile_user_prompt()` - Complexity ~2
3. `_compile_criteria_prompts()` - Complexity ~5
4. `_resolve_security_level()` - Complexity ~2
5. `_resolve_determinism_level()` - Complexity ~2
6. `_calculate_retry_summary()` - Complexity ~6
7. `_prepare_row_batch()` - Complexity ~4
8. `_execute_row_processing()` - Complexity ~8
9. `_process_single_row()` - Complexity ~10
10. `_run_aggregators()` - Complexity ~4
11. `_build_execution_metadata()` - Complexity ~5
12. `_dispatch_to_sinks()` - Complexity ~3

**Total Complexity: ~61 (distributed across 12 focused methods)**
**Average per Method: ~5.1**

## Supporting Classes (New)
1. `CheckpointManager` - Checkpoint persistence
2. `ExperimentContext` - Compiled configuration
3. `RowBatch` - Prepared rows
4. `ProcessingResult` - Execution results
5. `ResultHandlers` - Callback functions
6. `ExecutionMetadata` - Metadata with to_dict()

## Test Coverage

### New Test Files
- `tests/test_runner_characterization.py` - 6 invariant tests
- `tests/test_runner_safety.py` - 3 edge case tests

### Test Breakdown
- Unit tests: 8 (helper methods)
- Integration tests: 18 (original)
- Characterization: 6 (behavioral invariants)
- Safety: 3 (edge cases)
- **Total: 35 tests**

## SonarQube Impact

### Issues Resolved
- ✅ S3776: Cognitive complexity > 40 (run method)
- ✅ Code structure improved for maintainability

### Remaining Work
- Other complexity hotspots (suite_runner, etc.)
- See: sonar_issues_triaged.md

EOF

cat quality_report.md
```

**Commit:**
```bash
git add benchmark_results.txt quality_report.md
git commit -m "Docs: Add quality and performance validation

Post-refactoring validation complete:
- All 32 tests passing
- Coverage maintained at 89%
- Performance: no regression
- Complexity: 73 → 8 (run method)
- Code quality: all checks pass"
```

---

### Step 5.6: Final Review and Cleanup (15 min)

**Task:** Final checks before merge

- [ ] Review all commits
- [ ] Verify branch is clean
- [ ] Update PR description
- [ ] Request code review

**Commands:**
```bash
# 1. Review commit history
git log --oneline origin/refactor/sonar-code-quality..HEAD

# 2. Check for uncommitted changes
git status

# 3. Verify tests one last time
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py -v

# 4. Push final changes
git push origin refactor/sonar-code-quality
```

**Expected Commit Count:** ~18 commits
- Phase 0: 4 commits (safety net)
- Phase 1: 2 commits (supporting classes)
- Phase 2: 4 commits (simple extractions)
- Phase 3: 4 commits (complex extractions)
- Phase 4: 2 commits (main refactor + docs)
- Phase 5: 2 commits (validation + quality)

---

### Phase 5 Completion Checklist

- [ ] Baseline comparison complete
- [ ] Manual tests passing
- [ ] Performance benchmarks acceptable
- [ ] Integration tests passing (35 tests)
- [ ] Code quality validated
- [ ] Final review complete
- [ ] Branch pushed to remote
- [ ] Ready for PR

---

## Success Criteria

**Must Pass Before Merging:**
- [ ] All 32+ tests passing
- [ ] MyPy: no errors
- [ ] Coverage ≥ 89%
- [ ] SonarQube complexity for run() < 15
- [ ] No performance regression (< 5%)
- [ ] All characterization tests pass
- [ ] All safety tests pass
- [ ] Baseline comparison documented
- [ ] Quality report generated
- [ ] Peer review approved

**Final Verification Commands:**
```bash
# Full test suite
pytest tests/test_experiments.py \
       tests/test_experiment_runner_integration.py \
       tests/test_runner_characterization.py \
       tests/test_runner_safety.py \
       -v --cov=src/elspeth/core/experiments/runner --cov-report=html

# Linting
python -m ruff check src/elspeth/core/experiments/runner.py

# Type checking
python -m mypy src/elspeth/core/experiments/runner.py
```

**Expected Final State:**
- ✅ 32/32 tests passing (18 original + 6 characterization + 3 safety + unit tests)
- ✅ Coverage: ≥89%
- ✅ Complexity: run() method < 10 (target ~8)
- ✅ Line count: ~450 (reduction from 765)
- ✅ All helper methods < 15 complexity
- ✅ No type errors
- ✅ No lint warnings

---

## Rollback Triggers

**Abort refactoring and rollback if:**
1. Test failure rate > 5% at any phase
2. Coverage drops below 85%
3. Performance regression > 10%
4. New type errors introduced
5. Behavioral changes detected in characterization tests

**Rollback Procedure:**
```bash
# If need to abort
git reset --hard origin/refactor/sonar-code-quality
git clean -fd

# Return to baseline state
git checkout main
```

---

## Post-Merge Tasks

**After PR is merged:**
1. Update SonarQube issue status
2. Mark S3776 for `runner.py:75` as resolved
3. Update `sonar_issues_triaged.md` with progress
4. Plan next refactoring target (suite_runner.py)

---

## Notes and Reminders

**During Execution:**
- ☕ Take breaks between phases
- 🧪 Run tests after EVERY commit
- 📝 Update todo list as you progress
- 🔄 Commit frequently (at least once per step)
- 📊 Monitor test execution time
- 🛑 Stop if characterization tests fail

**If Blocked:**
- Review baseline tests to understand expected behavior
- Check git log for related commits
- Consult risk mitigation document
- Consider creating a minimal reproduction test
- Ask for help if stuck > 30 minutes

---

## Estimated Timeline

| Phase | Time | Start | End |
|-------|------|-------|-----|
| **Phase 0** | 3.5h | T+0 | T+3.5h |
| *Break* | 0.5h | T+3.5h | T+4h |
| **Phase 1** | 2h | T+4h | T+6h |
| **Phase 2** | 3h | T+6h | T+9h |
| *Break* | 1h | T+9h | T+10h |
| **Phase 3** | 4h | T+10h | T+14h |
| *Break* | 0.5h | T+14h | T+14.5h |
| **Phase 4** | 1h | T+14.5h | T+15.5h |
| **Phase 5** | 3h | T+15.5h | T+18.5h |
| **Total** | 18.5h | - | - |

**Recommended Schedule:**
- **Day 1 (AM):** Phase 0 + Phase 1 (5.5h)
- **Day 1 (PM):** Phase 2 (3h)
- **Day 2 (AM):** Phase 3 (4h)
- **Day 2 (PM):** Phase 4 + Phase 5 (4h)

---

## Completion Summary Template

**Copy this template when finished:**

```markdown
# Refactoring Complete: ExperimentRunner.run()

## Results

### Metrics
- **Before:** 765 lines, complexity 73
- **After:** XXX lines, complexity XX
- **Reduction:** XX% lines, XX% complexity

### Tests
- **Before:** 18 tests, 89% coverage
- **After:** XX tests, XX% coverage
- **Added:** XX characterization + XX safety + XX unit tests

### Time
- **Estimated:** 17.5 hours
- **Actual:** XX hours
- **Variance:** XX%

### Commits
- **Total:** XX commits
- **Files Changed:** X
- **Lines Added:** +XXX
- **Lines Removed:** -XXX

## Lessons Learned
- [Key insight 1]
- [Key insight 2]
- [Key insight 3]

## Future Opportunities

### Test Coverage Enhancement

**Context:** While coverage increased from 71% to 75% on runner.py during this refactoring, the characterization tests focus on integration-level behavioral verification rather than granular unit test coverage.

**Recommendation:** Consider adding focused unit tests for edge cases identified during the refactoring:
- **Checkpoint corruption scenarios** - What happens if checkpoint file is corrupted mid-write?
- **Concurrent access edge cases** - Race conditions during parallel checkpoint writes
- **Early stop edge cases** - Multiple early stop conditions firing simultaneously
- **Retry exhaustion patterns** - Complex failure scenarios with nested retries
- **Malformed data routing** - Edge cases in schema violation routing logic

**Priority:** Low (deferred to future work)

The current characterization test approach is appropriate for refactoring verification. These granular unit tests would provide additional safety for future modifications but are not required for this PR.

See functional reviewer feedback (post-approval) for additional context.

---

## Next Steps
- [ ] Merge PR
- [ ] Update SonarQube
- [ ] Plan next refactoring (suite_runner.py)
- [ ] Share learnings with team
```

---

**END OF EXECUTION PLAN**

✅ Plan complete and ready for execution.
🚀 Begin with Phase 0: Safety Net Construction.
