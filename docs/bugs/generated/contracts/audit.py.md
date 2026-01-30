# Bug Report: Audit contract enum validation is incomplete (silent acceptance of wrong/None enum values)

## Summary

- Audit contract classes that declare strict enum fields (Call, RoutingEvent, Batch, TokenOutcome) do not enforce enum types at runtime, and `_validate_enum` allows `None` for required enum fields, so invalid or null enum values can slip into Tier‑1 audit objects without crashing.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 27d291cb8f74c8012217cd0332e377a2463e07de (detached HEAD)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In a Python REPL, construct a `Call` with a string enum:
   `Call(..., call_type="http", status="success", ...)`
2. Construct a `Run` with `status=None` (required enum field).
3. Observe that neither instantiation raises, despite strict enum contract expectations.

## Expected Behavior

- Any non‑enum (including `None` for required fields) should raise immediately on construction to enforce Tier‑1 audit integrity.

## Actual Behavior

- `Call`, `RoutingEvent`, `Batch`, and `TokenOutcome` accept non‑enum values with no error.
- Required enum fields in `Run`/`Node`/`Edge` allow `None` because `_validate_enum` explicitly skips validation on `None`.

## Evidence

- `Call` is documented as strict enum contract but has no runtime validation (`src/elspeth/contracts/audit.py:253-271`).
- `RoutingEvent` strict enum contract without validation (`src/elspeth/contracts/audit.py:290-305`).
- `Batch` strict enum contract without validation (`src/elspeth/contracts/audit.py:308-324`).
- `TokenOutcome` enum field without validation (`src/elspeth/contracts/audit.py:543-566`).
- `_validate_enum` allows `None` (`src/elspeth/contracts/audit.py:28-36`), and `Run.status` is non‑optional yet only validated via `_validate_enum` (`src/elspeth/contracts/audit.py:39-64`).

## Impact

- User-facing impact: Incorrect enum values can propagate through audit objects, leading to misleading explain outputs or downstream comparisons failing silently.
- Data integrity / security impact: Violates Tier‑1 audit trail contract (“crash on invalid data”), risking silent audit corruption.
- Performance or cost impact: Minimal, but adds debugging cost when invalid values are accepted silently.

## Root Cause Hypothesis

- Enum validation was added only for `Run`, `Node`, and `Edge`, and `_validate_enum` was written to tolerate `None` for optional enums, but that tolerance is reused for required enum fields and missing in other strict contract classes.

## Proposed Fix

- Code changes (modules/files):
  - Add `__post_init__` validation to `Call`, `RoutingEvent`, `Batch`, and `TokenOutcome` in `src/elspeth/contracts/audit.py`.
  - Update `_validate_enum` to support an `allow_none: bool` parameter; set `allow_none=False` for required enums and `allow_none=True` for optional fields (e.g., `Run.export_status`).
- Config or schema changes: N/A
- Tests to add/update:
  - Add tests that constructing these classes with string/`None` enums raises `TypeError` (e.g., in `tests/contracts/test_audit.py`).
- Risks or migration steps:
  - Tightening validation may break tests or callers that currently pass raw strings; those call sites should be corrected to pass enums.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` (Auditability Standard; Tier 1 trust model: crash on invalid audit data).
- Observed divergence: Audit contract classes allow invalid enum values without crashing.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce enum validation uniformly in audit contracts and disallow `None` for required enum fields.

## Acceptance Criteria

- Constructing `Call`, `RoutingEvent`, `Batch`, or `TokenOutcome` with non‑enum values raises `TypeError`.
- Constructing `Run`/`Node`/`Edge` with `None` for required enums raises `TypeError`.
- Existing enum‑correct paths continue to pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_audit.py -k "Call or RoutingEvent or Batch or TokenOutcome or Run"`
- New tests required: yes, add invalid‑enum and `None` enum validation tests for the affected classes.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
