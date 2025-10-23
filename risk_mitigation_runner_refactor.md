# Risk Mitigation Plan: ExperimentRunner.run() Refactoring

**Target:** `src/elspeth/core/experiments/runner.py:75`
**Pre-Refactoring Assessment:** 2025-10-23
**Status:** ✅ READY TO PROCEED (with mitigation measures in place)

---

## Current State Assessment

### ✅ Test Coverage Status

**Overall Runner Coverage:** 89% (447 statements, 29 missed)

**Test Files:**
- `tests/test_experiment_runner_integration.py` - 1 test
- `tests/test_experiments.py` - 17 tests

**Total Tests:** 18 tests ✅ ALL PASSING

**Test Scenarios Covered:**
1. ✅ Basic experiment execution
2. ✅ Criteria-based experiments
3. ✅ Plugin integration (row, aggregator, validation)
4. ✅ Jinja2 prompt rendering
5. ✅ Concurrency control
6. ✅ Cost tracking
7. ✅ Retry logic (transient/permanent failures)
8. ✅ Failure recording
9. ✅ Checkpointing
10. ✅ Rate limiting
11. ✅ Early stop (config-based)
12. ✅ Early stop (plugin-based)
13. ✅ Artifact pipeline integration
14. ✅ Middleware hooks (before_request, after_response, on_retry_exhausted)

**Coverage Gaps (11% uncovered):**
- Some error paths
- Edge cases in schema validation
- Rare concurrent edge cases

**Assessment:** ✅ **EXCELLENT** - 89% coverage with comprehensive scenario coverage

---

## Risk Assessment Matrix

| Risk | Probability | Impact | Severity | Mitigation |
|------|-------------|--------|----------|------------|
| **Breaking existing behavior** | Medium | Critical | HIGH | Behavioral tests + incremental |
| **Test failures** | Low | High | MEDIUM | Run tests after each step |
| **Performance regression** | Low | Medium | LOW | Benchmark before/after |
| **Introducing bugs** | Medium | High | HIGH | Type checking + unit tests |
| **Missing edge cases** | Medium | Medium | MEDIUM | Characterization tests |
| **Concurrent issues** | Low | Medium | LOW | Existing concurrency tests |
| **Checkpoint corruption** | Low | High | MEDIUM | Existing checkpoint tests |
| **Plugin incompatibility** | Low | Medium | LOW | Plugin integration tests |

---

## Critical Behavioral Invariants

These behaviors **MUST** be preserved:

### 1. Execution Order Guarantees
```python
# INVARIANT: Results maintain input order regardless of parallelization
records_with_index.sort(key=lambda item: item[0])
results = [record for _, record in records_with_index]
```
**Verification:** `test_experiment_runner` checks result order

### 2. Checkpoint Atomicity
```python
# INVARIANT: Each processed row is checkpointed exactly once
if checkpoint_path and row_id is not None:
    if processed_ids is not None:
        processed_ids.add(row_id)
    self._append_checkpoint(checkpoint_path, row_id)
```
**Verification:** `test_checkpoint_skips_processed` validates this

### 3. Early Stop Propagation
```python
# INVARIANT: Early stop checks at:
# - Row preparation loop (line 128)
# - Sequential processing loop (line 161)
# - During parallel execution (via event)
```
**Verification:** `test_experiment_runner_early_stop` validates this

### 4. Retry Metadata Consistency
```python
# INVARIANT: Retry summary counts must match:
# total_retries = sum(max(attempts - 1, 0) for all records + failures)
```
**Verification:** `test_execute_llm_retry` validates retry behavior

### 5. Metadata Propagation
```python
# INVARIANT: These metadata fields must always be present:
# - security_level (resolved from df + config)
# - determinism_level (resolved from df + config)
# - rows, row_count
```
**Verification:** Integration tests check metadata structure

### 6. Plugin Lifecycle
```python
# INVARIANT: Aggregators run after all row processing:
for plugin in self.aggregator_plugins or []:
    derived = plugin.finalize(results)  # Gets ALL results
```
**Verification:** `test_experiment_runner_plugins` validates plugin order

### 7. Failure Isolation
```python
# INVARIANT: Single row failure doesn't stop other rows
# (unless early stop triggered)
```
**Verification:** `test_runner_records_failures` validates this

### 8. Sink Dispatch Contract
```python
# INVARIANT: Sinks receive payload with:
# - results: list[dict]
# - failures: list[dict]
# - metadata: dict
# - aggregates: dict (if any)
```
**Verification:** `test_experiment_runner_handles_retries_and_artifact_pipeline`

---

## Pre-Refactoring Safety Measures

### Step 1: Create Characterization Tests ✅

**Purpose:** Document current behavior in detail

```python
# tests/test_runner_characterization.py

def test_run_method_result_structure():
    """Document exact result structure expected from run()."""
    runner = ExperimentRunner(
        llm_client=mock_llm,
        sinks=[],
        prompt_system="Test",
        prompt_template="Test {{ field }}",
    )
    df = pd.DataFrame([{"field": "value"}])
    result = runner.run(df)

    # MUST have these top-level keys
    assert set(result.keys()) >= {"results", "failures", "metadata"}

    # Metadata MUST have these fields
    assert "rows" in result["metadata"]
    assert "row_count" in result["metadata"]
    assert "security_level" in result["metadata"]
    assert "determinism_level" in result["metadata"]


def test_run_preserves_result_order():
    """INVARIANT: Results maintain DataFrame order."""
    runner = ExperimentRunner(...)
    df = pd.DataFrame([{"id": "A"}, {"id": "B"}, {"id": "C"}])
    result = runner.run(df)

    # Extract IDs in result order
    result_ids = [r["context"]["id"] for r in result["results"]]
    assert result_ids == ["A", "B", "C"]


def test_run_checkpoint_idempotency():
    """INVARIANT: Rerunning with checkpoint skips processed rows."""
    runner = ExperimentRunner(..., checkpoint_config={"path": "cp.jsonl", "field": "id"})
    df = pd.DataFrame([{"id": "A"}, {"id": "B"}])

    # First run
    result1 = runner.run(df)
    assert len(result1["results"]) == 2

    # Second run (checkpoint exists)
    result2 = runner.run(df)
    assert len(result2["results"]) == 0  # All skipped


def test_run_early_stop_terminates_processing():
    """INVARIANT: Early stop prevents further row processing."""
    class StopAfterOne:
        name = "stop_after_one"
        def reset(self): pass
        def check(self, record, metadata=None):
            return {"reason": "stopped", "row_index": metadata["row_index"]}

    runner = ExperimentRunner(..., early_stop_plugins=[StopAfterOne()])
    df = pd.DataFrame([{"id": f"row{i}"} for i in range(10)])
    result = runner.run(df)

    # Should process only 1 row
    assert len(result["results"]) == 1
    assert "early_stop" in result["metadata"]


def test_run_aggregator_receives_all_results():
    """INVARIANT: Aggregators get complete result set."""
    class RecordingAggregator:
        name = "recorder"
        def finalize(self, results):
            self.received_count = len(results)
            return {"count": self.received_count}

    agg = RecordingAggregator()
    runner = ExperimentRunner(..., aggregator_plugins=[agg])
    df = pd.DataFrame([{"id": i} for i in range(5)])
    result = runner.run(df)

    assert agg.received_count == 5
    assert result["aggregates"]["recorder"]["count"] == 5


def test_run_failure_doesnt_stop_others():
    """INVARIANT: One row failure doesn't block others."""
    class FlakyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            row_id = metadata.get("row_id", "")
            if row_id == "fail_row":
                raise RuntimeError("Simulated failure")
            return {"content": f"OK {row_id}"}

    runner = ExperimentRunner(
        llm_client=FlakyLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Test {{ id }}",
        retry_config={"max_attempts": 1},  # Don't retry
    )
    df = pd.DataFrame([{"id": "ok1"}, {"id": "fail_row"}, {"id": "ok2"}])
    result = runner.run(df)

    assert len(result["results"]) == 2  # ok1, ok2
    assert len(result["failures"]) == 1  # fail_row
```

**Action:** Create `tests/test_runner_characterization.py` with these tests

---

### Step 2: Snapshot Current Behavior ✅

**Purpose:** Capture baseline for comparison

```bash
# 1. Run tests and capture output
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py \
  -v --tb=short > baseline_test_output.txt 2>&1

# 2. Capture coverage report
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py \
  --cov=src/elspeth/core/experiments/runner \
  --cov-report=html:baseline_coverage

# 3. Benchmark performance (if needed)
python -m timeit -s "from tests.test_experiments import ..." "test_experiment_runner()"
```

**Action:** Run these commands and save outputs

---

### Step 3: Add Type Checking Safety Net ✅

**Current State:**
```bash
$ mypy src/elspeth/core/experiments/runner.py
# Check if it passes without errors
```

**Action:** Ensure MyPy passes before refactoring

---

### Step 4: Identify Unsafe Code Paths

**Review runner.py for:**

1. ✅ **Threading/Concurrency:** Lines 147-158 (parallel execution)
   - **Risk:** Race conditions in checkpoint updates
   - **Mitigation:** Existing `_early_stop_lock` and test coverage

2. ✅ **File I/O:** Lines 82-84 (checkpoint loading), 140 (checkpoint append)
   - **Risk:** Corrupted checkpoints
   - **Mitigation:** Existing tests verify checkpoint integrity

3. ✅ **Error Handling:** Lines 163-176 (row processing)
   - **Risk:** Missed error cases
   - **Mitigation:** Test coverage for retry/failure paths

4. ⚠️ **State Mutations:** Throughout (instance variables)
   - **Risk:** Unexpected side effects
   - **Mitigation:** **CRITICAL - Track carefully during refactoring**

---

## Refactoring Safety Protocol

### Phase 0: Pre-Flight Checklist

- [x] ✅ All existing tests pass (18/18)
- [x] ✅ Coverage is adequate (89%)
- [ ] 🔄 Characterization tests added
- [ ] 🔄 Baseline outputs captured
- [ ] 🔄 MyPy type checking passes
- [ ] 🔄 Branch created: `refactor/runner-run-method`

### Phase 1: Test-Driven Extraction

**For each extraction:**

1. ✅ **Write test first** (if not covered)
2. ✅ **Extract method** (copy logic, don't modify)
3. ✅ **Run tests** (must all pass)
4. ✅ **Replace call site** (use extracted method)
5. ✅ **Run tests again** (must all pass)
6. ✅ **Commit** (small, focused commit)

**Example Workflow:**
```bash
# 1. Write test for _calculate_retry_summary
pytest tests/test_runner_characterization.py::test_calculate_retry_summary -v

# 2. Extract method (don't change run() yet)
# ... code changes ...

# 3. Test extraction
pytest tests/test_runner_characterization.py::test_calculate_retry_summary -v

# 4. Replace call site in run()
# ... code changes ...

# 5. Test integration
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py -v

# 6. Commit
git add src/elspeth/core/experiments/runner.py tests/test_runner_characterization.py
git commit -m "Extract: _calculate_retry_summary() helper method"
```

### Phase 2: Continuous Validation

**After each step:**

```bash
# Quick smoke test
pytest tests/test_experiment_runner_integration.py -v

# Full test suite
pytest tests/test_experiments.py tests/test_experiment_runner_integration.py -v

# Type checking
mypy src/elspeth/core/experiments/runner.py

# Coverage check (should not decrease)
pytest --cov=src/elspeth/core/experiments/runner --cov-report=term-missing
```

### Phase 3: Integration Verification

**Before final PR:**

```bash
# 1. Run ALL tests
make test

# 2. Run linting
make lint

# 3. Check coverage
pytest --cov=src/elspeth --cov-report=html

# 4. Benchmark performance (if slow path was touched)
# Compare with baseline

# 5. Manual smoke test
python -m elspeth.cli suite run config/sample_suite.yaml --dry-run
```

---

## State Mutation Tracking

**Critical State Variables to Track:**

| Variable | Mutated At | New Location After Refactor |
|----------|------------|------------------------------|
| `self._compiled_system_prompt` | Line 110 | `ExperimentContext.system_template` |
| `self._compiled_user_prompt` | Line 111 | `ExperimentContext.user_template` |
| `self._compiled_criteria_prompts` | Line 112 | `ExperimentContext.criteria_templates` |
| `self._malformed_rows` | Line 120 | Keep as instance var (used by sinks) |
| `self._active_security_level` | Lines 229, 244 | Keep (used by sinks via artifacts) |
| `self._active_determinism_level` | Line 233 | Keep (used by sinks via artifacts) |
| `self._early_stop_reason` | Set by `_maybe_trigger_early_stop()` | Keep (checked at lines 236-238) |

**Verification Strategy:**
- All state variables documented
- Each mutation tracked in tests
- No new mutable state introduced

---

## Rollback Plan

**If refactoring fails:**

```bash
# Option 1: Revert specific commit
git log --oneline  # Find commit hash
git revert <commit-hash>

# Option 2: Reset branch to safe state
git reset --hard origin/refactor/sonar-code-quality

# Option 3: Abandon branch and restart
git checkout main
git branch -D refactor/runner-run-method
# Start fresh
```

**Trigger for rollback:**
- Any test failure that can't be fixed in 30 minutes
- Performance regression > 10%
- MyPy errors introduced
- Behavior change discovered

---

## Success Metrics

### Must Have (Blocking)
- [x] ✅ All 18 existing tests pass
- [ ] 🎯 All new characterization tests pass
- [ ] 🎯 MyPy type checking passes
- [ ] 🎯 No performance regression (< 5%)
- [ ] 🎯 Coverage maintained or improved (≥ 89%)

### Should Have (Non-Blocking)
- [ ] 🎯 SonarQube complexity < 15 for `run()`
- [ ] 🎯 Method length < 40 lines
- [ ] 🎯 All extracted methods have tests
- [ ] 🎯 Code review approval

### Nice to Have
- [ ] Improved coverage (> 90%)
- [ ] Documentation updates
- [ ] Performance improvement

---

## Test Gap Analysis

**Missing Test Coverage:**

1. ⚠️ **Malformed data routing** (line 117: `self._validate_plugin_schemas`)
   - **Risk:** Medium
   - **Action:** Add test for `on_schema_violation="route"`

2. ⚠️ **Empty DataFrame handling**
   - **Risk:** Low
   - **Action:** Add test for `df = pd.DataFrame()`

3. ⚠️ **Concurrent checkpoint updates** (rare race condition)
   - **Risk:** Low
   - **Action:** Existing lock should handle; stress test if time permits

4. ⚠️ **Aggregator failure handling**
   - **Risk:** Low
   - **Action:** Add test for aggregator that raises exception

**Recommendation:** Add tests #1 and #4 before refactoring

---

## Additional Safety Tests to Add

```python
# tests/test_runner_safety.py

def test_run_with_empty_dataframe():
    """Edge case: Empty DataFrame should return empty results."""
    runner = ExperimentRunner(...)
    df = pd.DataFrame()
    result = runner.run(df)

    assert result["results"] == []
    assert result["failures"] == []
    assert result["metadata"]["rows"] == 0


def test_run_with_failing_aggregator():
    """Aggregator failure should not crash run()."""
    class BrokenAggregator:
        name = "broken"
        def finalize(self, results):
            raise RuntimeError("Aggregator failure")

    runner = ExperimentRunner(..., aggregator_plugins=[BrokenAggregator()])
    df = pd.DataFrame([{"id": "test"}])

    # Should either:
    # A) Handle gracefully and continue, or
    # B) Re-raise with clear error message
    # (Check current behavior first)
    result = runner.run(df)
    # Assert based on actual behavior


def test_run_schema_violation_routing():
    """When on_schema_violation='route', malformed rows go to special sink."""
    # TODO: Implement once schema validation is understood
    pass
```

---

## Estimated Timeline with Safety Measures

| Phase | Task | Time | Risk |
|-------|------|------|------|
| **Pre-flight** | Add characterization tests | 2h | Low |
| **Pre-flight** | Capture baselines | 0.5h | None |
| **Pre-flight** | Add safety tests | 1h | Low |
| **Step 1** | Create supporting classes | 2h | Low |
| **Step 2** | Extract simple helpers | 3h | Low |
| **Step 3** | Extract complex methods | 4h | Medium |
| **Step 4** | Refactor main method | 1h | Medium |
| **Step 5** | Testing & validation | 3h | Low |
| **Cleanup** | Documentation, PR prep | 1h | None |

**Total:** 17.5 hours (~2.5 days) with full safety protocol

**Previous Estimate:** 13 hours (without safety measures)

**Difference:** +4.5 hours for comprehensive risk mitigation ✅ **WORTH IT**

---

## Decision: PROCEED or DEFER?

### ✅ PROCEED - Conditions Met

**Reasons:**
1. ✅ Excellent test coverage (89%)
2. ✅ All 18 tests currently passing
3. ✅ Comprehensive test scenarios covered
4. ✅ Clear behavioral invariants identified
5. ✅ Incremental refactoring strategy defined
6. ✅ Rollback plan in place
7. ✅ Risk mitigation measures defined

**Blockers Resolved:**
- None

**Prerequisites:**
1. ⚠️ Add characterization tests (2 hours)
2. ⚠️ Add safety tests for gaps (1 hour)
3. ⚠️ Capture baselines (30 minutes)

**Recommendation:** ✅ **PROCEED after completing prerequisites (3.5 hours)**

---

## Next Steps

1. **Create characterization tests** (`tests/test_runner_characterization.py`)
2. **Add safety gap tests** (`tests/test_runner_safety.py`)
3. **Capture baselines** (test output, coverage, performance)
4. **Verify MyPy passes** on current code
5. **Create refactoring branch** (`refactor/runner-run-method`)
6. **Begin Step 1** of implementation plan

---

**Status:** 🟡 READY (pending prerequisites)
**Risk Level:** 🟢 LOW (with mitigation measures)
**Confidence:** 🟢 HIGH (89% coverage, comprehensive tests)

---

*Generated by Claude Code - Risk Assessment*
*Date: 2025-10-23*
