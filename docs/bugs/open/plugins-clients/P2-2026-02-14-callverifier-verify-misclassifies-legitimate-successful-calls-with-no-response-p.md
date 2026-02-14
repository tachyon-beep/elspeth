## Summary

`CallVerifier.verify()` misclassifies legitimate successful calls with no response payload as `missing_payload`, creating false audit drift/missing-payload signals.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/clients/verifier.py`
- Line(s): 223-225
- Function/Method: `CallVerifier.verify`

## Evidence

`verifier.py` currently treats every `SUCCESS` call as if a response payload must exist:

```python
# src/elspeth/plugins/clients/verifier.py:223-225
response_expected = call.response_hash is not None or call.status == CallStatus.SUCCESS
if recorded_response is None and response_expected:
    self._report.missing_payloads += 1
```

But the codebase allows successful calls with no response payload (`response_data=None`), which yields `response_hash=None` by design:

```python
# src/elspeth/core/landscape/_call_recording.py:135
response_hash = stable_hash(response_data) if response_data is not None else None
```

And there is an explicit test asserting this is valid behavior:

```python
# tests/unit/plugins/test_context.py:913-925
# None response - truly no data
ctx.record_call(... status=CallStatus.SUCCESS, response_data=None)
assert emitted_events[0].response_hash is None
```

So verifier’s `status == SUCCESS` check over-classifies these as payload loss even when nothing was ever recorded.

## Root Cause Hypothesis

Verifier inferred “response expected” from call status (`SUCCESS`) instead of using actual payload evidence (`response_hash` / `response_ref`). That assumption conflicts with established behavior where some successful operations legitimately have no response body.

## Suggested Fix

In `verifier.py`, determine expected response from recorded payload indicators, not status alone. For example:

```python
response_expected = call.response_hash is not None or call.response_ref is not None
```

Then keep `missing_payload` only for cases where a response is known to have existed but is now unavailable.

Also add a verifier unit test for: `SUCCESS + response_hash=None + response_ref=None + recorded_response=None` should **not** increment `missing_payloads`.

## Impact

- False `missing_payloads` counts in verify reports.
- Incorrect operational/audit signals (appears like data loss/purge when none occurred).
- Can trigger unnecessary investigation and mask real payload-retention issues by polluting metrics.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/clients/verifier.py.md`
- Finding index in source report: 1
- Beads: pending
