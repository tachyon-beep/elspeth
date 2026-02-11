# Bug Report: CallVerifier skips hash verification when payloads are purged

## Summary

- When a recorded response payload is missing/purged but `response_hash` exists, `CallVerifier.verify()` returns early with `payload_missing=True` and never compares `live_response` against the recorded hash, so verify mode cannot validate integrity in `ATTRIBUTABLE_ONLY` runs.

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
- Data set or fixture: Baseline run with response payloads purged or payload store disabled (`ATTRIBUTABLE_ONLY`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/clients/verifier.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Record a call with `response_data` so `response_hash` is stored, then purge payloads or run without a payload store (so `get_call_response_data()` returns `None`).
2. Instantiate `CallVerifier` against that run and call `verify()` with a `live_response` that differs from the original response.
3. Observe that `verify()` returns `payload_missing=True` and exits without hash comparison, and no mismatch is recorded.

## Expected Behavior

- When `recorded_response` is unavailable but `response_hash` exists, `CallVerifier` should compare `stable_hash(live_response)` to the recorded `response_hash` and mark match/mismatch accordingly, even while noting `payload_missing`.

## Actual Behavior

- `CallVerifier.verify()` returns early on missing payload (when `response_expected=True`) without any hash comparison, so drift cannot be detected in `ATTRIBUTABLE_ONLY` runs.

## Evidence

- Early return on missing payload skips any hash comparison in `src/elspeth/plugins/clients/verifier.py:212-226`.
  `src/elspeth/plugins/clients/verifier.py:212-226`
- `response_hash` is computed and stored even if payloads are purged in `src/elspeth/core/landscape/recorder.py:2278-2309`.
  `src/elspeth/core/landscape/recorder.py:2278-2309`
- Auditability standard requires hash-based verifiability after payload deletion in `CLAUDE.md:9-17`.
  `CLAUDE.md:9-17`
- Reproducibility grades explicitly state `ATTRIBUTABLE_ONLY` can “verify via hashes” in `docs/architecture/landscape-system.md:742-748`.
  `docs/architecture/landscape-system.md:742-748`

## Impact

- User-facing impact: Verify mode cannot confirm drift or integrity when payloads are purged, making `ATTRIBUTABLE_ONLY` runs unverifiable.
- Data integrity / security impact: Audit trail guarantee (“integrity is always verifiable”) is violated; drift can go undetected.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `CallVerifier.verify()` treats missing payload as a terminal condition and does not use the recorded `response_hash` for comparison when `recorded_response` is unavailable.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/clients/verifier.py`: when `recorded_response is None` and `call.response_hash` exists, compute `stable_hash(live_response)` and compare to `call.response_hash`. Mark `is_match` and `mismatches/matches` accordingly while keeping `payload_missing=True`.
  - Update `VerificationResult`/`has_differences` logic so hash-based mismatches are surfaced even when payload is missing (e.g., add a `hash_mismatch` flag or include a `differences` entry like `{"hash_mismatch": {...}}`).
- Config or schema changes: None.
- Tests to add/update:
  - Add a test where `response_hash` exists but payload is missing; ensure hash match counts as match and mismatch counts as mismatch.
- Risks or migration steps:
  - Low risk; behavior changes only for payload-missing scenarios and aligns with documented auditability guarantees.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:9-17`, `docs/architecture/landscape-system.md:742-748`
- Observed divergence: Verifier does not verify via hashes when payloads are purged.
- Reason (if known): Early return on `payload_missing` without hash comparison.
- Alignment plan or decision needed: Implement hash-based verification path for missing payloads and surface mismatches in report.

## Acceptance Criteria

- When payloads are missing but `response_hash` exists, `verify()` performs hash comparison and correctly updates `matches`, `mismatches`, and `has_differences`.
- A new test demonstrates that hash mismatch is detected in `ATTRIBUTABLE_ONLY` conditions.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/clients/test_verifier.py -k payload`
- New tests required: yes, add hash-compare coverage for payload-missing path.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/architecture/landscape-system.md`, `CLAUDE.md`
