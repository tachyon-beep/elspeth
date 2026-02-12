# Bug Report: resolve_headers masks contract corruption in ORIGINAL mode

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Fixed**
- Verification summary:
  - `resolve_headers()` now raises `KeyError` in ORIGINAL mode when a contract field lookup misses.
  - Regression coverage was added for contract index corruption in header resolution.
- Current evidence:
  - `src/elspeth/contracts/header_modes.py:97`
  - `tests/unit/contracts/test_header_modes.py:95`

## Summary

- `resolve_headers()` silently falls back to normalized names when a contract lookup fails, masking internal contract corruption instead of crashing as required by the Tier 1 trust model.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/header_modes.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a valid `SchemaContract` with fields and then corrupt its `_by_normalized` index (e.g., remove an entry) to simulate internal inconsistency.
2. Call `resolve_headers(contract=contract, mode=HeaderMode.ORIGINAL, custom_mapping=None)`.
3. Observe that the missing field silently falls back to its normalized name instead of raising.

## Expected Behavior

- When `contract` is provided, any missing field lookup should raise immediately (crash) because this indicates internal data corruption (Tier 1 data) and should never be silently masked.

## Actual Behavior

- `resolve_headers()` uses `contract.get_field(name)` and falls back to `name` when it returns `None`, hiding internal contract inconsistencies.

## Evidence

- Defensive fallback in `resolve_headers()` when `contract.get_field()` returns `None`. `src/elspeth/contracts/header_modes.py:94-98`
- `SchemaContract.get_field()` returns `None` on missing field via `.get()`, enabling the silent fallback path. `src/elspeth/contracts/schema_contract.py:139-148`

## Impact

- User-facing impact: Headers can silently revert to normalized names in ORIGINAL mode, producing incorrect output headers without any error signal.
- Data integrity / security impact: Masks internal contract corruption or bugs, violating Tier 1 “crash on anomaly” and audit integrity requirements.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `resolve_headers()` uses a bug-hiding fallback (`field.original_name if field else name`) for Tier 1 contract data, contrary to the “no defensive programming” and “crash on corruption” standards.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/header_modes.py`: Replace the fallback with a hard failure when `contract.get_field(name)` returns `None`, or build the mapping directly from `contract.fields` to avoid nullable lookups entirely.
- Config or schema changes: None
- Tests to add/update:
  - Add a unit test in `tests/contracts/test_header_modes.py` that simulates contract index corruption (e.g., mutating `_by_normalized`) and asserts `resolve_headers()` raises.
- Risks or migration steps:
  - Raises earlier on contract corruption; expected and aligned with Tier 1 requirements.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L29-L32` (Tier 1 crash-on-anomaly) and `CLAUDE.md#L918-L920` (no defensive programming patterns).
- Observed divergence: `resolve_headers()` suppresses a missing field in a Tier 1 contract by falling back to normalized names instead of crashing.
- Reason (if known): Unknown
- Alignment plan or decision needed: Remove fallback and enforce crash-on-anomaly for contract lookups.

## Acceptance Criteria

- `resolve_headers()` raises when a contract lookup fails in ORIGINAL mode.
- Added test fails on old behavior and passes after fix.
- No changes to behavior for NORMALIZED or CUSTOM modes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_header_modes.py`
- New tests required: yes, add a test asserting failure on contract inconsistency.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: CLAUDE.md (Tier 1 trust model; defensive programming prohibition)

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `6a42515e`
- Fix summary: Removed ORIGINAL-mode fallback to normalized header names on missing contract lookup and replaced with fail-fast `KeyError`.
- Test coverage: Added `test_original_mode_raises_on_contract_lookup_miss` in `tests/unit/contracts/test_header_modes.py`.
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.
