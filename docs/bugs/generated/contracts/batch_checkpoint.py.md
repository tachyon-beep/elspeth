## Summary

`BatchCheckpointState.from_dict()` accepts corrupted `requests` entries without validating that each `custom_id` maps to a request-body mapping, so checkpoint corruption survives deserialization and crashes later when Azure batch code expands `**original_request`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py`
- Line(s): 142-145, 165-172
- Function/Method: `BatchCheckpointState.from_dict`

## Evidence

`from_dict()` only checks that `requests` is a top-level `dict`:

```python
requests = data["requests"]
if not isinstance(requests, dict):
    raise AuditIntegrityError(...)
...
return cls(
    ...
    requests=requests,
)
```

Evidence:
- `/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py:142-145`
- `/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py:165-172`

But downstream code assumes every value under `checkpoint.requests` is a mapping and unpacks it directly:

```python
for custom_id, original_request in checkpoint.requests.items():
    ...
    request_data={
        "custom_id": custom_id,
        "row_index": row_index,
        **original_request,
    },
```

Evidence:
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:723-746`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:1314-1326`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:1421-1445`

If a persisted checkpoint contains `{"requests": {"row-0": "not a dict"}}`, `BatchCheckpointState.from_dict()` accepts it, but the first terminal failure or result-reconciliation path raises `TypeError: 'str' object is not a mapping` during `**original_request`. That violates the contract stated in this file’s docstring that Tier 1 checkpoint corruption must crash at deserialization, not much later inside resume logic.

There is coverage for the top-level `requests` field being non-dict, but not for corrupted nested values:
- `/home/john/elspeth/tests/unit/contracts/test_batch_checkpoint.py:244-249`

## Root Cause Hypothesis

The contract was tightened only one level deep when the typed checkpoint replaced the old untyped dict. The field annotation says `Mapping[str, Mapping[str, Any]]`, but `from_dict()` enforces only the outer container shape and relies on callers to behave. That leaves a structural corruption hole at the Tier 1 boundary.

## Suggested Fix

Validate `requests` entries during deserialization and constructor validation, not just the outer mapping. Each key should be `str`, and each value should be a mapping/dict suitable for `request_data`.

Helpful shape:

```python
requests = data["requests"]
if not isinstance(requests, dict):
    raise AuditIntegrityError(...)

for custom_id, request_body in requests.items():
    if not isinstance(custom_id, str):
        raise AuditIntegrityError(...)
    if not isinstance(request_body, dict):
        raise AuditIntegrityError(...)
```

It would also be reasonable to mirror this in `__post_init__` so in-memory construction cannot create an invalid checkpoint state either.

## Impact

A corrupted checkpoint can deserialize successfully, then crash later during failed-batch audit emission or completed-batch call recording. That breaks the Tier 1 “crash on anomaly at read boundary” rule and can prevent per-row LLM call records from being written, leaving an incomplete audit trail for the affected batch.
---
## Summary

`BatchCheckpointState` never validates that `submitted_at` is actually an ISO datetime string, so invalid checkpoint data is accepted and later crashes in Azure batch status handling when `datetime.fromisoformat()` is called.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py`
- Line(s): 88-89, 165-170
- Function/Method: `BatchCheckpointState.__post_init__`, `BatchCheckpointState.from_dict`

## Evidence

The contract says `submitted_at` is an “ISO datetime string”, but the only validation is truthiness:

```python
if not self.submitted_at:
    raise ValueError("BatchCheckpointState.submitted_at must not be empty")
```

and `from_dict()` passes the value through unchanged:

```python
return cls(
    ...
    submitted_at=data["submitted_at"],
    ...
)
```

Evidence:
- `/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py:68-69`
- `/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py:88-89`
- `/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py:165-170`

Downstream, resume/status code assumes this field is parseable ISO text on multiple paths:

```python
submitted_at = datetime.fromisoformat(checkpoint.submitted_at)
```

Evidence:
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:830-831`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:864-877`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:892-900`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:931-932`

So a checkpoint like `{"submitted_at": 123}` or `{"submitted_at": "not-a-timestamp"}` is accepted by the target file, then fails later with `TypeError` or `ValueError` in batch polling logic instead of being rejected as checkpoint corruption at deserialization time.

Existing tests only cover empty-string rejection, not wrong type or invalid ISO format:
- `/home/john/elspeth/tests/unit/contracts/test_checkpoint_post_init.py:263-273`

## Root Cause Hypothesis

The typed checkpoint migration added presence checks but not semantic validation for string-typed fields. `submitted_at` is treated as an opaque string in the contract layer even though integration code depends on a specific parseable ISO-8601 format.

## Suggested Fix

Validate `submitted_at` in both `__post_init__` and `from_dict()`:
- Require `str`
- Require non-empty
- Require `datetime.fromisoformat(submitted_at)` to succeed

Helpful shape:

```python
if not isinstance(submitted_at, str):
    raise AuditIntegrityError(...)
try:
    datetime.fromisoformat(submitted_at)
except ValueError as exc:
    raise AuditIntegrityError(...) from exc
```

If constructor-time validation stays in `__post_init__`, raise `TypeError`/`ValueError` there and `AuditIntegrityError` in `from_dict()` for persisted corruption.

## Impact

Corrupted checkpoint state is allowed past the Tier 1 read boundary and only explodes later when the batch transform checks status, timeout, or failure latency. That makes resume failures harder to diagnose, violates the file’s own crash-on-deserialization contract, and can interrupt terminal-state handling for an in-flight batch.
