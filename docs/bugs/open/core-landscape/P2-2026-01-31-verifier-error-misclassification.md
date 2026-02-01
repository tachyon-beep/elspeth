# Bug Report: CallVerifier misclassifies error calls as missing payloads

## Summary

- `CallVerifier` treats `recorded_response is None` as `payload_missing=True`, but ERROR calls with no response_ref are legitimate (call failed before response).

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/plugins/clients/verifier.py:208-222` - treats `recorded_response is None` as missing without checking call status.
- Never checks `call.status` or `call.error_json`
- ERROR calls with no response_ref are legitimate

## Impact

- User-facing impact: False "missing payload" reports for error calls
- Data integrity: None (verification, not recording)

## Proposed Fix

- Check call.status before marking as payload_missing; ERROR calls with no response are expected

## Acceptance Criteria

- ERROR calls with no response_ref not counted as missing payloads

## Verification (2026-02-01)

**Status: STILL VALID**

- `CallVerifier` still marks `payload_missing` when `recorded_response` is `None` without checking `call.status`. (`src/elspeth/plugins/clients/verifier.py:208-222`)
