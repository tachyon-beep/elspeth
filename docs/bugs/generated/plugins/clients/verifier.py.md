# Bug Report: CallVerifier misclassifies error calls as missing payloads and hides drift

## Summary

- CallVerifier never inspects the recorded call status or error_json, so ERROR calls with no response_ref are treated as “payload missing,” masking drift between error vs success and inflating missing_payloads.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Recorded call with status=ERROR and no response_ref

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/clients/verifier.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Record a call with status=ERROR and no response_ref (common for failed external calls).
2. Call `CallVerifier.verify(...)` with the same request_data and a live_response dict from a successful live call.
3. Observe `payload_missing=True`, `has_differences=False`, and `missing_payloads` incremented.

## Expected Behavior

- ERROR calls should not be treated as missing payloads; verification should compare error status (and error_json when available) to the live outcome and report drift if they differ.

## Actual Behavior

- ERROR calls are flagged as `payload_missing` because `get_call_response_data()` returns None, and no drift is reported.

## Evidence

- `CallVerifier.verify()` never checks call status and treats `recorded_response is None` as missing payload: `src/elspeth/plugins/clients/verifier.py:208-222`.
- Recorder explicitly documents that ERROR calls may have no response_ref, so None is expected: `src/elspeth/core/landscape/recorder.py:2471-2486`.
- Call contract includes `status` and `error_json`, which are ignored by CallVerifier: `src/elspeth/contracts/audit.py:260-271`.
- CallReplayer handles ERROR calls correctly by checking status and error_json: `src/elspeth/plugins/clients/replayer.py:204-220`.

## Impact

- User-facing impact: Verify mode can miss real drift when a baseline error becomes a success (or vice versa), producing false confidence.
- Data integrity / security impact: Audit trail stats misclassify error calls as missing payloads, reducing trust in verification results.
- Performance or cost impact: minimal.

## Root Cause Hypothesis

- CallVerifier assumes a missing response payload always indicates purge/missing data and ignores `call.status` and `call.error_json`, so ERROR calls are misclassified.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/clients/verifier.py`: inspect `call.status` and `call.error_json` before treating `recorded_response is None` as missing; treat ERROR calls as a distinct verification path.
  - Extend `VerificationResult` to include recorded_status/live_status and error details, or add optional `live_status`/`live_error` params to `verify()` so error calls can be compared explicitly.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests in `tests/plugins/clients/test_verifier.py` for recorded ERROR calls with no response_ref, verifying they are not counted as missing_payloads and that status mismatches are reported.
- Risks or migration steps:
  - API change if `verify()` gains `live_status`/`live_error` parameters; update callers accordingly.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/landscape/recorder.py:2471-2476` (error calls may have no response_ref); `src/elspeth/plugins/clients/replayer.py:204-220` (expected handling of ERROR calls).
- Observed divergence: CallVerifier treats error calls as missing payloads rather than an expected error-path case.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Define verify-mode semantics for ERROR calls (status-only vs error_json diff) and implement consistent handling in CallVerifier.

## Acceptance Criteria

- ERROR calls with no response_ref are not counted as missing_payloads.
- Verify reports drift when recorded status=ERROR and live status=SUCCESS (or vice versa).
- Tests cover ERROR-path verification and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/clients/test_verifier.py -k error`
- New tests required: yes, add ERROR-call verification cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/design/architecture.md` (verify mode discussion)
