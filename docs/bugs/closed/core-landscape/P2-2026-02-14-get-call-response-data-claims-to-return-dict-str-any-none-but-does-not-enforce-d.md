## Summary

`get_call_response_data()` claims to return `dict[str, Any] | None` but does not enforce dict type after JSON decode, allowing Tier-1 payload corruption/type drift to pass silently.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py`
- Line(s): 593-594
- Function/Method: `get_call_response_data`

## Evidence

Current code:

```python
payload_bytes = self._payload_store.retrieve(row.response_ref)
data: dict[str, Any] = json.loads(payload_bytes.decode("utf-8"))
return data
```

`json.loads(...)` can return `list`, `str`, `int`, etc. The annotation is only static; there is no runtime validation.
By contrast, similar Tier-1 payload read logic in `/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py:146-153` explicitly validates decoded type and raises `AuditIntegrityError` when not a dict.

So this method can return non-dict data while claiming dict, masking contract violations in our own audit data path.

## Root Cause Hypothesis

The implementation relies on type hints as if they were runtime checks, but Python does not enforce them. Type validation was omitted in this read path.

## Suggested Fix

Validate decoded payload type and crash on anomaly (Tier-1 policy), e.g. with strict type check:

```python
decoded = json.loads(payload_bytes.decode("utf-8"))
if type(decoded) is not dict:
    raise AuditIntegrityError(
        f"Corrupt call response payload for call {call_id} (ref={row.response_ref}): "
        f"expected JSON object, got {type(decoded).__name__}"
    )
return decoded
```

Keep `KeyError -> None` for purged payload behavior.

## Impact

Corrupt or contract-violating call payloads can be misclassified as normal replay/verify differences instead of failing fast as audit-integrity violations, weakening Tier-1 trust guarantees.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_call_recording.py.md`
- Finding index in source report: 2
- Beads: pending
