## Summary

`CallReplayer.replay()` can silently fabricate an empty response (`{}`) for error calls that actually had a recorded response reference, when `response_hash` is missing.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 -- scenario requires explicit response_ref without response_data, which no production caller does; standard recording flow always sets response_hash when response exists

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/clients/replayer.py
- Line(s): 212-221
- Function/Method: `CallReplayer.replay`

## Evidence

In `replayer.py`, payload-missing detection is currently:

```python
response_expected = call.response_hash is not None or call.status == CallStatus.SUCCESS
if response_data is None and response_expected:
    raise ReplayPayloadMissingError(...)
if response_data is None:
    response_data = {}
```

(`/home/john/elspeth-rapid/src/elspeth/plugins/clients/replayer.py:215-221`)

But recorder APIs explicitly allow calls with `response_ref` and no `response_data` (therefore no `response_hash`):

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:135`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:161-163`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:362`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py:386-388`
- `/home/john/elspeth-rapid/tests/unit/core/landscape/test_call_recording.py:232-247`
- `/home/john/elspeth-rapid/tests/unit/core/landscape/test_call_recording.py:620-633`

So if such a call is `ERROR` and `get_call_response_data()` returns `None` (purged store / unavailable store), replay will incorrectly fall through to `{}` instead of failing fast.

## Root Cause Hypothesis

`response_expected` is inferred from `response_hash` or `SUCCESS` status, but not from `response_ref`. That misses a valid "response existed" signal and causes silent fallback behavior.

## Suggested Fix

Treat `response_ref` as an additional evidence signal that a response was expected:

```python
response_expected = (
    call.response_ref is not None
    or call.response_hash is not None
    or call.status == CallStatus.SUCCESS
)
```

Then keep raising `ReplayPayloadMissingError` when `response_data is None and response_expected`.

Add a unit test for `ERROR + response_ref set + response_hash None + missing payload -> ReplayPayloadMissingError`.

## Impact

Replay mode can return synthetic `{}` instead of the real recorded error payload, causing silent behavior drift and violating auditability expectations ("No inference - if it's not recorded, it didn't happen"; `CLAUDE.md:19`).
