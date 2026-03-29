## Summary

`CallReplayer.replay()` reconstructs recorded payloads with a shallow `dict(...)` copy, so nested JSON arrays come back as frozen `tuple`s instead of `list`s in replay mode.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py`
- Line(s): 239-245
- Function/Method: `CallReplayer.replay`

## Evidence

`get_call_response_data()` returns a `CallDataResult`, and `CallDataResult.__post_init__()` deep-freezes nested containers:

```python
# src/elspeth/core/landscape/row_data.py:138-149
if self.state in self._STATES_WITH_DATA:
    ...
    freeze_fields(self, "data")
```

That means recorded JSON like `{"choices": [{"x": 1}]}` is stored in-memory as a deeply frozen structure (`MappingProxyType`, nested `tuple`s).

`replayer.py` only does a shallow outer copy:

```python
# src/elspeth/plugins/infrastructure/clients/replayer.py:239-245
if call_data.state == CallDataState.AVAILABLE:
    response_data: dict[str, Any] = dict(call_data.data)
```

So nested containers stay frozen. A replayed payload with arrays is returned with tuple-valued fields instead of JSON-style lists.

The adjacent verifier already compensates for this exact contract:

```python
# src/elspeth/plugins/infrastructure/clients/verifier.py:395-399
# CallDataResult.data is deep-frozen (dict→MappingProxyType, list→tuple).
# Thaw back to mutable types so DeepDiff compares content, not container types.
recorded_response = deep_thaw(call_data.data)
```

This matters because recorded responses are defined as normal dict/list wire shapes. For example, `LLMCallResponse.raw_response` is arbitrary provider JSON and can contain nested arrays:

```python
# src/elspeth/contracts/call_data.py:125-140
raw_response: Mapping[str, Any]
...
"raw_response": deep_thaw(self.raw_response)
```

The current replay path therefore returns a different data shape than the originally recorded response.

## Root Cause Hypothesis

The replayer was updated to use `CallDataResult`, but its reconstruction logic only thawed the outer mapping and forgot that `CallDataResult` deep-freezes nested containers by design. That makes replay mode leak the storage-layer immutability representation into the runtime payload contract.

## Suggested Fix

Use `deep_thaw()` when reconstructing both response and error payloads before building `ReplayedCall`, matching the verifier’s approach.

Example:

```python
from elspeth.contracts.freeze import deep_thaw

...

if call_data.state == CallDataState.AVAILABLE:
    response_data = deep_thaw(call_data.data)
```

If `error_json` is parsed, it should also be validated/thawed to a plain `dict[str, Any]` before returning.

## Impact

Replay mode can diverge from live mode for any recorded response containing nested arrays or nested frozen mappings. Clients consuming replayed payloads may see tuple/list mismatches, fail schema checks, serialize differently, or produce different downstream behavior than the original run. That undermines replay correctness and the audit guarantee that replay returns the recorded response rather than a mutated representation.
---
## Summary

`CallReplayer.replay()` treats `CALL_NOT_FOUND` after a successful `find_call_by_request_hash()` lookup as an ordinary missing payload instead of a Tier 1 audit-integrity failure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py`
- Line(s): 218-249
- Function/Method: `CallReplayer.replay`

## Evidence

`replayer.py` first finds a specific call record:

```python
# src/elspeth/plugins/infrastructure/clients/replayer.py:207-216
call = self._recorder.find_call_by_request_hash(...)
if call is None:
    raise ReplayMissError(...)
```

It then asks for that exact call’s payload state:

```python
# src/elspeth/plugins/infrastructure/clients/replayer.py:218-249
call_data = self._recorder.get_call_response_data(call.call_id)

...
else:
    # PURGED, STORE_NOT_CONFIGURED, or CALL_NOT_FOUND — response was
    # expected but payload is unavailable. Raise with explicit reason.
    raise ReplayPayloadMissingError(call.call_id, request_hash)
```

But `CALL_NOT_FOUND` means the call row vanished between the two queries. The verifier handles this as corruption/TOCTOU, not as a normal missing payload:

```python
# src/elspeth/plugins/infrastructure/clients/verifier.py:366-374
if call_data.state == CallDataState.CALL_NOT_FOUND:
    raise AuditIntegrityError(
        f"CALL_NOT_FOUND for call_id={call.call_id} after successful "
        f"find_call_by_request_hash — audit record vanished between queries. "
        f"Possible database corruption or concurrent modification."
    )
```

There is even a dedicated verifier regression test for this invariant:

```python
# tests/unit/plugins/clients/test_verifier.py:1146-1163
recorder.find_call_by_request_hash.return_value = mock_call
recorder.get_call_response_data.return_value = CallDataResult(
    state=CallDataState.CALL_NOT_FOUND, data=None
)
with pytest.raises(AuditIntegrityError, match="CALL_NOT_FOUND"):
    verifier.verify(...)
```

No equivalent protection exists in `test_replayer.py`.

## Root Cause Hypothesis

When `CallDataState` handling was expanded, replay grouped `CALL_NOT_FOUND` with genuine payload-availability states like `PURGED` and `STORE_NOT_CONFIGURED`. That loses the distinction between “payload missing” and “audit row disappeared after lookup,” which are very different failure classes under ELSPETH’s Tier 1 rules.

## Suggested Fix

Handle `CALL_NOT_FOUND` explicitly and raise `AuditIntegrityError`, mirroring `CallVerifier.verify()`. Keep only true payload-availability states (`PURGED`, `STORE_NOT_CONFIGURED`, `HASH_ONLY`) on the `ReplayPayloadMissingError` path.

## Impact

A vanished audit row is currently reported as if the payload store were merely missing data. That hides a Tier 1 integrity violation behind an operational-looking replay error, sending operators toward the wrong fix and weakening ELSPETH’s crash-on-corruption guarantees for audit data.
