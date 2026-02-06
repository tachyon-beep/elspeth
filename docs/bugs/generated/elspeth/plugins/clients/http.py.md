# Bug Report: Non-finite JSON Values in HTTP Responses Break Call Recording and Drop Payloads

## Summary

- HTTP client accepts JSON responses containing `NaN`/`Infinity` and forwards them into audit recording, which rejects non-finite values and fails, resulting in missing response payloads and potential unrecorded calls.

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
- Data set or fixture: Mocked HTTP response with JSON containing `NaN`/`Infinity`

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/plugins/clients/http.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Mock `httpx.Response` to return `content-type: application/json` and `response.json()` containing `{"value": float("nan")}`.
2. Call `AuditedHTTPClient.post(...)` and observe `LandscapeRecorder.record_call()` failing during hashing.

## Expected Behavior

- HTTP client should validate or reject non-finite values at the external boundary and record a canonicalizable response payload (e.g., `_json_parse_failed` with raw text) without losing the audit record.

## Actual Behavior

- Non-finite values pass through `response.json()` and cause `stable_hash()`/`canonical_json()` to raise `ValueError`, which drops `response_data` and can prevent a complete audit record; if the request body also contains non-finite values, recording can fail entirely.

## Evidence

- `src/elspeth/plugins/clients/http.py:266-310` parses `response.json()` without validating non-finite values and sets `response_body` directly.
- `src/elspeth/core/landscape/recorder.py:2278-2283` hashes `request_data`/`response_data` with `stable_hash()`.
- `src/elspeth/core/canonical.py:58-61` raises `ValueError` for non-finite floats (`NaN`/`Infinity`).

## Impact

- User-facing impact: HTTP calls can raise unexpected `ValueError` despite successful responses, breaking pipeline execution.
- Data integrity / security impact: Response payloads can be lost from the audit trail, violating audit completeness and replay/verify.
- Performance or cost impact: Potential retries and failed runs due to avoidable exceptions.

## Root Cause Hypothesis

- The HTTP client treats `response.json()` output as safe without enforcing the canonical JSON non-finite value policy, so malformed external JSON surfaces as internal serialization errors during audit recording.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/plugins/clients/http.py` to parse JSON with explicit rejection of `NaN`/`Infinity` (e.g., `json.loads(response.text, parse_constant=...)`) and fallback to `_json_parse_failed` with raw text; optionally pre-validate request `json` payload for non-finite values before making the call.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/plugins/clients/test_audited_http_client.py` asserting that JSON with `NaN`/`Infinity` is recorded as parse failure and does not crash.
- Risks or migration steps: Behavior change for non-standard JSON responses; ensure callers handle parse-failed responses.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:629-645` (Canonical JSON rejects NaN/Infinity)
- Observed divergence: HTTP client allows non-finite values from external JSON to reach audit hashing, which then rejects them.
- Reason (if known): Missing boundary validation for external JSON responses.
- Alignment plan or decision needed: Enforce non-finite rejection at the HTTP client boundary and record parse-failed payloads deterministically.

## Acceptance Criteria

- HTTP responses containing `NaN`/`Infinity` do not crash audit recording and are captured as explicit parse failures with raw text preserved.
- No call recording path can fail due to non-finite values from external JSON.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/clients/test_audited_http_client.py -k nan`
- New tests required: yes, add coverage for non-finite JSON in responses (and optionally request payloads).

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:629-645`
