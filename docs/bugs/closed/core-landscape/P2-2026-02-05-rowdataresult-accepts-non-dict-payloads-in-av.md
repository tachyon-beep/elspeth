# Bug Report: RowDataResult Accepts Non-Dict Payloads in AVAILABLE State

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `RowDataResult` still enforces only None/non-None invariants and does not enforce dict type for AVAILABLE.
  - `get_row_data()` still forwards decoded JSON directly into AVAILABLE without shape validation.
  - Repro still accepts `RowDataResult(state=AVAILABLE, data=[...])`.
- Current evidence:
  - `src/elspeth/core/landscape/row_data.py:56`
  - `src/elspeth/core/landscape/_query_methods.py:145`
  - `src/elspeth/core/landscape/_query_methods.py:146`

## Summary

- RowDataResult does not validate that AVAILABLE data is a `dict`, so non-dict JSON payloads (e.g., arrays, scalars) are treated as valid audit data instead of crashing on Tier 1 corruption.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Payload store containing JSON array (e.g., `[1, 2, 3]`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/landscape/row_data.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `FilesystemPayloadStore` and store a JSON array payload (e.g., `payload_ref = store.store(b"[1,2,3]")`).
2. Create a row with `source_data_ref=payload_ref` (via `LandscapeRecorder.create_row` using `payload_ref`).
3. Call `LandscapeRecorder.get_row_data(row_id)`.

## Expected Behavior

- The system should crash immediately (raise) when decoded payload data is not a `dict`, because Tier 1 audit data must be pristine and type-correct.

## Actual Behavior

- `get_row_data()` returns `RowDataResult(state=AVAILABLE, data=[1,2,3])`, allowing non-dict audit data to propagate without error.

## Evidence

- `src/elspeth/core/landscape/row_data.py:56` only enforces None vs non-None and never validates that `data` is a `dict` for AVAILABLE state.
- `src/elspeth/core/landscape/recorder.py:2023` and `src/elspeth/core/landscape/recorder.py:2024` decode JSON into `data` without any type validation before constructing `RowDataResult`.

## Impact

- User-facing impact: Downstream callers may treat malformed payloads as valid rows and either mis-handle data or fail later with less actionable errors.
- Data integrity / security impact: Violates Tier 1 audit integrity by allowing corrupted or malformed payloads to be treated as valid audit records.
- Performance or cost impact: None expected.

## Root Cause Hypothesis

- `RowDataResult.__post_init__` enforces only None/non-None invariants and omits type validation for AVAILABLE data, allowing non-dict payloads to pass through as valid audit data.

## Proposed Fix

- Code changes (modules/files): Add type validation in `src/elspeth/core/landscape/row_data.py:56` to require `data` to be a `dict` when `state == AVAILABLE` and raise a `TypeError` or `ValueError` otherwise.
- Config or schema changes: None
- Tests to add/update: Add a unit test in `tests/core/landscape/test_row_data.py` asserting AVAILABLE with non-dict data raises; optionally extend `tests/property/core/test_row_data_properties.py` with non-dict examples.
- Risks or migration steps: Minimal; may surface previously hidden corruption or bad payloads.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25` and `CLAUDE.md:29` (Tier 1 audit data must crash on any anomaly; no coercion or defaults).
- Observed divergence: Non-dict audit payloads are accepted as AVAILABLE instead of crashing.
- Reason (if known): Missing type validation in `RowDataResult.__post_init__`.
- Alignment plan or decision needed: Enforce dict-only payloads for AVAILABLE results to comply with Tier 1 trust requirements.

## Acceptance Criteria

- `RowDataResult(state=AVAILABLE, data=<non-dict>)` raises immediately.
- `get_row_data()` raises when payload JSON is valid but not an object/dict.
- New unit/property tests cover non-dict AVAILABLE payloads and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_row_data.py -v`
- New tests required: yes, add a unit test for non-dict AVAILABLE data

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard, Three-Tier Trust Model)

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `6bcbbf2a`
- Fix summary: Enforce dict payload invariant for RowDataResult AVAILABLE state
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.

