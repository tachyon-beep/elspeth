# Bug Report: JSONFormatter Silently Coerces Audit Data and Allows NaN/Infinity

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `JSONFormatter` still uses `json.dumps(record, default=str)` directly.
  - Repro still serializes `float('nan')` as `NaN` and datetime via `str(...)`.
- Current evidence:
  - `src/elspeth/core/landscape/formatters.py:105`
  - `src/elspeth/core/landscape/formatters.py:107`

## Summary

- JSONFormatter uses `json.dumps(..., default=str)` without `serialize_datetime`, allowing NaN/Infinity and silently coercing unexpected types instead of failing fast.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic audit record containing NaN/Infinity or datetime

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/core/landscape/formatters.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `JSONFormatter`.
2. Call `format` with `{"latency_ms": float("nan")}` or `{"timestamp": datetime(2026, 2, 4)}`.
3. Observe the returned JSON string.

## Expected Behavior

- NaN/Infinity should be rejected (raise `ValueError`) per audit integrity rules.
- Datetimes should be serialized to ISO-8601 using `serialize_datetime`.
- Unknown types should crash rather than being coerced.

## Actual Behavior

- NaN/Infinity are serialized as `NaN`/`Infinity` (invalid JSON).
- Datetimes are serialized via `str()` (non-ISO format).
- Unknown objects are silently coerced to strings.

## Evidence

- `src/elspeth/core/landscape/formatters.py:20-48` shows `serialize_datetime` explicitly rejects NaN/Infinity and converts datetimes to ISO strings.
- `src/elspeth/core/landscape/formatters.py:102-107` shows `JSONFormatter.format` calls `json.dumps(record, default=str)` without `serialize_datetime`, bypassing those checks.

## Impact

- User-facing impact: JSON exports can include invalid JSON tokens (`NaN`, `Infinity`) and inconsistent timestamp formats.
- Data integrity / security impact: Violates Tier 1 audit rules by coercing/normalizing data instead of crashing on anomalies.
- Performance or cost impact: Minimal; main risk is silent corruption rather than performance.

## Root Cause Hypothesis

- JSONFormatter was implemented with `default=str` for convenience and never wired to `serialize_datetime`, so audit integrity checks are skipped.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/core/landscape/formatters.py` update `JSONFormatter.format` to call `serialize_datetime(record)` and then `json.dumps(..., allow_nan=False)` without `default=str`.
- Config or schema changes: None.
- Tests to add/update: Add unit tests asserting NaN/Infinity raise `ValueError` and datetimes are ISO-8601 in JSONFormatter output.
- Risks or migration steps: JSON export will now raise if audit records contain non-serializable types or NaN/Infinity, surfacing latent data bugs.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L25-L32` (Tier 1 must crash on anomalies, no coercion) and `CLAUDE.md#L631-L643` (NaN/Infinity strictly rejected).
- Observed divergence: JSONFormatter coerces unknown types and allows NaN/Infinity instead of crashing.
- Reason (if known): Convenience `default=str` implementation.
- Alignment plan or decision needed: Enforce `serialize_datetime` + `allow_nan=False` and remove `default=str`.

## Acceptance Criteria

- JSONFormatter raises `ValueError` on NaN/Infinity.
- JSONFormatter outputs ISO-8601 strings for datetimes.
- JSONFormatter no longer coerces unknown types.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_formatters.py`
- New tests required: yes, add unit tests for JSONFormatter NaN/Infinity rejection and datetime ISO formatting.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 and canonical JSON rules)
