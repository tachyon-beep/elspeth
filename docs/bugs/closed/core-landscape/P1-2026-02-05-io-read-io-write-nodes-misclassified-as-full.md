# Bug Report: IO_READ/IO_WRITE nodes misclassified as FULL_REPRODUCIBLE

## Summary

- `compute_grade()` treats `IO_READ` and `IO_WRITE` as fully reproducible, but protocol and architecture docs define them as external/side-effectful operations that require replay, so runs with these nodes should be `REPLAY_REPRODUCIBLE`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory `LandscapeDB` with a node declared as `Determinism.IO_READ` or `Determinism.IO_WRITE`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/reproducibility.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `LandscapeDB.in_memory()` and begin a run via `LandscapeRecorder`.
2. Register a node with `determinism=Determinism.IO_READ` (or `IO_WRITE`).
3. Call `LandscapeRecorder.compute_reproducibility_grade(run_id)`.

## Expected Behavior

- The run should be graded `REPLAY_REPRODUCIBLE` because IO-based nodes depend on external state or side effects that require captured data for replay.

## Actual Behavior

- The run is graded `FULL_REPRODUCIBLE`.

## Evidence

- `compute_grade()` explicitly treats `IO_READ` and `IO_WRITE` as reproducible and only flags `EXTERNAL_CALL` and `NON_DETERMINISTIC` for replay: `src/elspeth/core/landscape/reproducibility.py:42-60`.
- Determinism contract defines `IO_READ` and `IO_WRITE` as external/side-effectful, requiring capture/replay: `docs/contracts/plugin-protocol.md:1327-1337`.
- Run-level grade definition says `FULL_REPRODUCIBLE` requires all transforms deterministic: `docs/design/architecture.md:675-680`.

## Impact

- User-facing impact: Runs with IO-based transforms are mislabeled as fully reproducible.
- Data integrity / security impact: Overstates reproducibility; replay expectations become incorrect.
- Performance or cost impact: Low.

## Root Cause Hypothesis

- The `non_reproducible` set in `compute_grade()` omits `IO_READ` and `IO_WRITE`, so IO-dependent nodes do not trigger replay grading.

## Proposed Fix

- Code changes (modules/files): Treat `IO_READ` and `IO_WRITE` as replay-required in `compute_grade()` (e.g., add them to `non_reproducible` or compute FULL only if all values are `{DETERMINISTIC, SEEDED}`); update docstring to match behavior.
- Config or schema changes: None.
- Tests to add/update: Add tests that verify `IO_READ` and `IO_WRITE` nodes produce `REPLAY_REPRODUCIBLE`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/design/architecture.md:675-680`, `docs/contracts/plugin-protocol.md:1327-1337`.
- Observed divergence: IO-based determinism values are treated as full reproducibility rather than replay-required.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Align `compute_grade()` with determinism contract by classifying IO-based nodes as replay-required.

## Acceptance Criteria

- A run containing any `IO_READ` or `IO_WRITE` nodes is graded `REPLAY_REPRODUCIBLE`.
- Tests cover IO-based determinism values.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_recorder_grades.py -v`
- New tests required: yes, add IO_READ/IO_WRITE grade tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md`, `docs/design/architecture.md`

## Resolution

**Fixed in:** 2026-02-05
**Beads issue:** elspeth-rapid-y5tk (closed)

**Fix:** Reclassified IO_READ and IO_WRITE as replay-required determinism values:
- Added `Determinism.IO_READ.value` and `Determinism.IO_WRITE.value` to the `non_reproducible` set
- Updated docstring to reflect that only DETERMINISTIC and SEEDED count as fully reproducible
- Per determinism contract: IO operations are external/side-effectful and require capture/replay

**Evidence:**
- `src/elspeth/core/landscape/reproducibility.py:71-76`: IO_READ and IO_WRITE added to `non_reproducible` set
- `src/elspeth/core/landscape/reproducibility.py:39-48`: Updated docstring to clarify only DETERMINISTIC/SEEDED are fully reproducible
- `tests/core/landscape/test_reproducibility.py:195-258`: Added two new tests verifying IO nodes grade as REPLAY_REPRODUCIBLE
- All 554 landscape tests pass
