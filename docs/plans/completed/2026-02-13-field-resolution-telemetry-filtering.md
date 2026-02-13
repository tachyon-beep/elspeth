# FieldResolutionApplied Granularity Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure `FieldResolutionApplied` telemetry events are filtered out at `lifecycle` granularity and emitted only at `rows`/`full` granularity.

**Architecture:** This fix is intentionally localized to telemetry granularity classification in `should_emit()` so behavior changes are isolated to emission policy rather than event production. We will first encode expected behavior in unit tests, then update classification logic, then run targeted tests to ensure no regression in existing lifecycle/row/external-call filtering behavior.

**Tech Stack:** Python 3.13, pytest, structural pattern matching (`match/case`) in telemetry filtering.

**Prerequisites:**
- Working virtualenv at `.venv`.
- Ability to run targeted pytest commands.
- No pending unrelated local changes in telemetry files.

---

### Task 1: Lock Expected Behavior with Failing Tests

**Files:**
- Modify: `tests/unit/telemetry/test_filtering.py`
- Reference: `docs/bugs/open/engine-spans/P2-2026-02-05-fieldresolutionapplied-bypasses-granularity-f.md`

**Step 1: Add event factory for `FieldResolutionApplied`**

```python
def _field_resolution_applied() -> FieldResolutionApplied:
    return FieldResolutionApplied(
        timestamp=_NOW,
        run_id=_RUN_ID,
        source_plugin="csv",
        field_count=2,
        normalization_version="v1",
        resolution_mapping={"Customer ID": "customer_id", "Order Amount": "order_amount"},
    )
```

**Why this test setup:** We need a concrete event instance to verify granularity behavior directly in filtering unit tests.

**Step 2: Add explicit granularity tests for `FieldResolutionApplied`**

```python
def test_field_resolution_applied_suppressed_at_lifecycle(self) -> None:
    assert should_emit(_field_resolution_applied(), LIFECYCLE) is False

def test_field_resolution_applied_emits_at_rows(self) -> None:
    assert should_emit(_field_resolution_applied(), ROWS) is True

def test_field_resolution_applied_emits_at_full(self) -> None:
    assert should_emit(_field_resolution_applied(), FULL) is True
```

**Why these tests:** They codify the bug ticket acceptance criteria and prevent regression.

**Step 3: Include event in row-event matrix**

```python
_ROW_FACTORIES = [
    pytest.param(_row_created, id="RowCreated"),
    pytest.param(_transform_completed, id="TransformCompleted"),
    pytest.param(_gate_evaluated, id="GateEvaluated"),
    pytest.param(_token_completed, id="TokenCompleted"),
    pytest.param(_field_resolution_applied, id="FieldResolutionApplied"),
]
```

**Why matrix update:** Keeps comprehensive test coverage aligned with event taxonomy and avoids one-off test drift.

**Step 4: Run tests to verify RED state (expected failure pre-fix)**

Run:
` .venv/bin/python -m pytest tests/unit/telemetry/test_filtering.py -k field_resolution -v`

Expected output:
- At least one failure showing `FieldResolutionApplied` currently emits at `lifecycle`.

**Definition of Done:**
- [ ] `FieldResolutionApplied` tests exist
- [ ] Tests fail pre-fix for the right reason (lifecycle currently `True`)

---

### Task 2: Implement Granularity Classification Fix

**Files:**
- Modify: `src/elspeth/telemetry/filtering.py`

**Step 1: Import `FieldResolutionApplied` in filtering module**

```python
from elspeth.contracts.events import (
    ExternalCallCompleted,
    FieldResolutionApplied,
    GateEvaluated,
    ...
)
```

**Step 2: Classify `FieldResolutionApplied` as row-level**

```python
case (
    RowCreated()
    | TransformCompleted()
    | GateEvaluated()
    | TokenCompleted()
    | FieldResolutionApplied()
):
    return granularity in (TelemetryGranularity.ROWS, TelemetryGranularity.FULL)
```

**Why this implementation:** It preserves forward-compatible fail-open behavior for truly unknown events while explicitly classifying a known event to match documented granularity contracts.

**Step 3: Align docstring comments in `should_emit()` to include `FieldResolutionApplied` in row-level events.**

**Step 4: Run tests to verify GREEN state**

Run:
` .venv/bin/python -m pytest tests/unit/telemetry/test_filtering.py -v`

Expected output:
- All tests in file pass, including new `FieldResolutionApplied` coverage.

**Definition of Done:**
- [ ] Filtering logic includes explicit `FieldResolutionApplied` classification
- [ ] Targeted test file passes

---

### Task 3: Regression and Risk Validation

**Files:**
- Modify: `tests/unit/telemetry/test_property_based.py`
- Modify: `tests/property/telemetry/test_emit_completeness.py`
- Modify: `docs/guides/telemetry.md`
- Modify: `docs/reference/configuration.md`

**Step 1: Run focused telemetry suite**

Run:
` .venv/bin/python -m pytest tests/unit/telemetry/test_manager.py tests/unit/telemetry/test_property_based.py tests/property/telemetry/test_emit_completeness.py -q`

**Why:** Confirms no collateral behavior changes in manager-level filtering and emission handling.

**Step 2: Verify no unintended formatting/lint issues in edited files**

Run:
` .venv/bin/python -m ruff check src/elspeth/telemetry/filtering.py tests/unit/telemetry/test_filtering.py tests/unit/telemetry/test_property_based.py tests/property/telemetry/test_emit_completeness.py`

**Step 3: Align telemetry event docs with implemented behavior**

- Update `docs/guides/telemetry.md` and `docs/reference/configuration.md` to explicitly list `FieldResolutionApplied` under `rows` granularity.

**Step 4: Summarize risk and rollout posture**

- Blast radius: Low (single filter function + unit tests)
- One-way door: None
- Runtime behavior change: Only suppresses one event in `lifecycle` mode
- Compatibility impact: Improves alignment with existing telemetry docs

**Definition of Done:**
- [ ] Focused telemetry regression tests pass
- [ ] Lint checks pass
- [ ] Risk is documented as low and acceptable

---

## Risk/Complexity Gate

### Complexity Assessment
- Code complexity: Low (single pattern-match branch update)
- Test complexity: Low to medium (adds event coverage + matrix inclusion)
- Integration complexity: Low (no schema/config changes)

### Risk Assessment
- Functional risk: Low
- Data integrity risk: Low
- Operational risk: Low (reduced telemetry volume in lifecycle mode)
- Reversibility: High (single-file code rollback)

### Go/No-Go Decision Criteria
- **GO** if: New tests fail before fix and pass after fix; no regressions in focused telemetry tests.
- **NO-GO** if: Manager/property-based telemetry tests show behavior drift outside intended granularity change.
