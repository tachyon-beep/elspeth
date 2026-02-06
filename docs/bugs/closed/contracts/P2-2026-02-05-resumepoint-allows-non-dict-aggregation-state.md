# Bug Report: ResumePoint Allows Non-Dict Aggregation State (Tier 1 Validation Gap)

## Status: CLOSED

**Fixed:** 2026-02-06
**Fixed by:** Claude Opus 4.5
**Bead:** elspeth-rapid-7dmz

## Summary

- `ResumePoint` does not validate that `aggregation_state` is a `dict`, so malformed or corrupted checkpoint JSON can propagate into resume logic and violate Tier 1 "crash immediately on audit data anomalies" rules.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: e0060836
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Checkpoint with malformed `aggregation_state_json` (e.g., JSON list or string)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/contracts/checkpoint.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a checkpoint with a non-dict aggregation state (e.g., call `CheckpointManager.create_checkpoint(..., aggregation_state=["bad"])`, which serializes to JSON).
2. Call `RecoveryManager.get_resume_point(...)` and then `Orchestrator.resume(...)` for that run.

## Expected Behavior

- `ResumePoint` creation (or recovery) should raise immediately if `aggregation_state` is not a `dict`, treating it as corrupted Tier 1 audit data.

## Actual Behavior

- `ResumePoint` accepts any JSON type; malformed `aggregation_state` propagates into resume logic and can later fail with non-actionable errors or undefined behavior.

## Evidence

- `src/elspeth/contracts/checkpoint.py:31-43` defines `ResumePoint` without any invariant checks, even though `aggregation_state` is typed as `dict[str, Any] | None`.
- `src/elspeth/core/checkpoint/recovery.py:145-154` deserializes `aggregation_state_json` via `json.loads` and passes it directly into `ResumePoint` without type validation.
- `src/elspeth/engine/orchestrator/core.py:1705-1707` assumes `aggregation_state` is a dict when building `restored_state`.
- `src/elspeth/engine/executors.py:1606-1627` expects checkpoint state to be a dict and uses dict methods during restore.

## Impact

- User-facing impact: Resume can fail with unclear errors when checkpoints are corrupted or malformed.
- Data integrity / security impact: Violates Tier 1 rule to crash immediately on audit data anomalies; corrupted checkpoint data may progress further than allowed.
- Performance or cost impact: Potential repeated resume attempts that fail late, wasting operator time.

## Root Cause Hypothesis

- `ResumePoint` lacks a `__post_init__` invariant check to enforce that `aggregation_state` is a dict when present, allowing invalid Tier 1 data to flow into resume logic.

## Fix Applied

### Code Changes

1. **`src/elspeth/contracts/checkpoint.py`**: Added `__post_init__` method to `ResumePoint` dataclass that validates `aggregation_state` is either `None` or a `dict`. Raises `ValueError` with a descriptive message if the type is incorrect.

```python
def __post_init__(self) -> None:
    """Validate aggregation_state is dict or None - Tier 1 crash on invalid types.

    Per CLAUDE.md Data Manifesto: Checkpoints are Tier 1 audit data.
    If aggregation_state is not a dict (when present), this indicates
    corrupted checkpoint data - crash immediately, no silent coercion.
    """
    if self.aggregation_state is not None and not isinstance(self.aggregation_state, dict):
        raise ValueError(
            f"aggregation_state must be dict or None, got {type(self.aggregation_state).__name__}: "
            f"{self.aggregation_state!r}"
        )
```

### Tests Added

2. **`tests/core/checkpoint/test_checkpoint_contracts.py`**: Added two new test classes:

   - `TestResumePointAggregationStateValidation`: Contract-level tests for `ResumePoint` validation
     - `test_resume_point_accepts_dict_aggregation_state`
     - `test_resume_point_accepts_none_aggregation_state`
     - `test_resume_point_rejects_list_aggregation_state`
     - `test_resume_point_rejects_string_aggregation_state`
     - `test_resume_point_rejects_int_aggregation_state`

   - `TestRecoveryRejectsNonDictAggregationState`: Integration tests for recovery path
     - `test_get_resume_point_raises_on_list_aggregation_state_json`
     - `test_get_resume_point_raises_on_string_aggregation_state_json`
     - `test_get_resume_point_raises_on_int_aggregation_state_json`
     - `test_get_resume_point_succeeds_with_valid_dict_aggregation_state_json`

### Verification

All 144 checkpoint tests pass including the 9 new tests.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25-33` (Tier 1 audit data must crash on any anomaly; no coercion or silent recovery).
- Observed divergence: Corrupted aggregation state can pass through `ResumePoint` without immediate crash.
- Reason (if known): Missing invariant enforcement in the `ResumePoint` contract.
- Alignment plan or decision needed: Enforce `aggregation_state` type at `ResumePoint` construction to fail fast on audit data corruption.

## Acceptance Criteria

- [x] `ResumePoint` rejects non-dict `aggregation_state` with a clear `ValueError`.
- [x] `RecoveryManager.get_resume_point()` fails immediately on non-dict `aggregation_state_json`.
- [x] Resume path does not proceed with malformed aggregation state.

## Tests

- Suggested tests to run: `python -m pytest tests/core/checkpoint/test_checkpoint_contracts.py -k "ResumePoint or Recovery" -v`
- New tests required: yes, contract validation test for `ResumePoint` non-dict `aggregation_state` and recovery test for malformed `aggregation_state_json`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 audit data rules)
