# Bug Report: resolve_headers masks missing SchemaContract fields in ORIGINAL mode

## Summary

- In ORIGINAL mode, `resolve_headers` falls back to normalized names if `SchemaContract.get_field()` returns `None`, silently hiding internal contract corruption instead of crashing.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 3aa2fa93d8ebd2650c7f3de23b318b60498cd81c (RC2.3-pipeline-row)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: None

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/header_modes.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Construct a valid `SchemaContract` with at least one field.
2. Corrupt its `_by_normalized` index (e.g., `object.__setattr__(contract, "_by_normalized", {})`) so `get_field()` returns `None` for a known field.
3. Call `resolve_headers(contract=contract, mode=HeaderMode.ORIGINAL, custom_mapping=None)`.
4. Observe that the missing field silently falls back to its normalized name.

## Expected Behavior

- `resolve_headers` should raise (or crash) if a contract field lookup fails, because contracts are system-owned data and must be pristine.

## Actual Behavior

- `resolve_headers` silently uses the normalized name when `contract.get_field()` returns `None`, masking internal corruption and emitting incorrect headers.

## Evidence

- `resolve_headers` uses `contract.get_field()` and falls back to the normalized name on `None`: `src/elspeth/contracts/header_modes.py:96`, `src/elspeth/contracts/header_modes.py:97`.
- This is a bug-hiding defensive pattern disallowed for system-owned data: `CLAUDE.md:918`, `CLAUDE.md:920`.

## Impact

- User-facing impact: Output headers in ORIGINAL mode may silently revert to normalized names, breaking external handoff expectations.
- Data integrity / security impact: Hides internal contract corruption, undermining audit integrity guarantees.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Defensive fallback in `resolve_headers` treats missing contract fields as acceptable, contrary to the full-trust contract invariant.

## Proposed Fix

- Code changes (modules/files): Update `resolve_headers` in `src/elspeth/contracts/header_modes.py` to raise when `contract.get_field(name)` returns `None` instead of falling back to `name`.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that corrupts the contract index and asserts `resolve_headers(..., mode=ORIGINAL)` raises.
- Risks or migration steps: This will cause a hard failure if contract indices are corrupted; this is intended per auditability rules.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918`, `CLAUDE.md:920`.
- Observed divergence: Defensive fallback (`field.original_name if field else name`) masks system-owned data corruption instead of crashing.
- Reason (if known): Likely added for convenience/robustness, but conflicts with audit integrity rules.
- Alignment plan or decision needed: Enforce hard failure on missing contract fields in ORIGINAL mode.

## Acceptance Criteria

- `resolve_headers` raises an error if `contract.get_field(name)` returns `None`.
- Existing tests for NORMALIZED/ORIGINAL/CUSTOM modes still pass.
- New test covering corrupted contract index passes (asserts raise).

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_header_modes.py -v`
- New tests required: yes, add a test for missing/invalid contract field lookup in ORIGINAL mode.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Prohibition on defensive programming)
