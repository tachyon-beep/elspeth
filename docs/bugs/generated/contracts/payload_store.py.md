## Summary

`PayloadStore` defines payload references as raw SHA-256 digests and claims only two protocol exceptions, but the surrounding audit API accepts arbitrary explicit refs; that mismatch causes runtime `ValueError` crashes when recorded refs are later resolved through the filesystem backend.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/payload_store.py`
- Line(s): 9-11, 43-73, 76-95
- Function/Method: `PayloadStore` protocol / module contract

## Evidence

`payload_store.py` says the protocol’s exception vocabulary is complete:

```python
# /home/john/elspeth/src/elspeth/contracts/payload_store.py:9-11
IntegrityError and PayloadNotFoundError are the complete exception vocabulary
for this protocol — one for corruption, one for absence. Do not add further
exception subtypes without strong justification.
```

It also documents every reference as a SHA-256 digest:

```python
# /home/john/elspeth/src/elspeth/contracts/payload_store.py:46-47, 65, 80, 91
where payloads are stored by their SHA-256 hash.
content_hash: SHA-256 hex digest
```

But the concrete backend rejects anything that is not exactly 64 lowercase hex chars and raises `ValueError`:

```python
# /home/john/elspeth/src/elspeth/core/payload_store.py:60-77
if not _SHA256_HEX_PATTERN.match(content_hash):
    raise ValueError(...)
```

Higher layers explicitly allow caller-supplied refs that are not hashes:

```python
# /home/john/elspeth/src/elspeth/core/landscape/recorder.py:476-490
request_ref: str | None = None,
response_ref: str | None = None,
...
request_ref=request_ref,
response_ref=response_ref,
```

That behavior is tested with non-hash refs:

```python
# /home/john/elspeth/tests/integration/audit/test_recorder_calls.py:527-539
explicit_ref = "explicit-reference-123"
...
response_ref=explicit_ref
assert call.response_ref == explicit_ref
```

and:

```python
# /home/john/elspeth/tests/unit/core/landscape/test_execution_repository.py:1331-1343
request_ref="existing-ref-123",
response_ref="existing-ref-456",
assert call.response_ref == "existing-ref-456"
```

Later, retrieval unconditionally routes `response_ref` back through `PayloadStore.retrieve()` and only handles `PayloadNotFoundError`, integrity errors, and `OSError`:

```python
# /home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:1008-1017
payload_bytes = self._payload_store.retrieve(row.response_ref)
except PayloadNotFoundError:
    return CallDataResult(state=CallDataState.PURGED, data=None)
except PayloadIntegrityError as e:
...
except OSError as e:
...
```

So an allowed explicit ref like `"existing-ref-456"` reaches the filesystem backend, which raises `ValueError`; that exception is outside the contract promised by `payload_store.py` and is not translated into an audit-state result or `AuditIntegrityError`.

This breaks downstream consumers that assume `get_call_response_data()` returns a valid `CallDataState`, such as verifier and replayer:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/verifier.py:325-330
call_data = self._recorder.get_call_response_data(call.call_id)
if call_data.state != CallDataState.AVAILABLE:
```

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py:219-248
call_data = self._recorder.get_call_response_data(call.call_id)
...
elif call_data.state == CallDataState.HASH_ONLY:
```

## Root Cause Hypothesis

The contract in `payload_store.py` models a payload reference as “the SHA-256 hex digest” and freezes the protocol to two exception types, but the rest of the audit layer has evolved to treat refs as opaque caller-provided identifiers. Because the target file is the source-of-truth interface, that mismatch propagates into implementation and caller assumptions: writers persist arbitrary refs, while readers assume every ref is valid for the payload store backend.

## Suggested Fix

Make the contract in `/home/john/elspeth/src/elspeth/contracts/payload_store.py` accurately represent one model and force the rest of the codebase to follow it.

Preferred direction: treat store references as opaque `payload_ref` values in the protocol, and add an explicit invalid-reference exception for refs that a backend cannot interpret.

Example shape:

```python
class InvalidPayloadRefError(Exception):
    def __init__(self, payload_ref: str) -> None:
        self.payload_ref = payload_ref
        super().__init__(f"Invalid payload ref: {payload_ref!r}")

class PayloadStore(Protocol):
    def store(self, content: bytes) -> str: ...
    def retrieve(self, payload_ref: str) -> bytes: ...
    def exists(self, payload_ref: str) -> bool: ...
    def delete(self, payload_ref: str) -> bool: ...
```

Then align callers to either:

1. Reject non-store-managed refs at record time, if refs are meant to be store-only.
2. Or handle `InvalidPayloadRefError` as an audit-integrity/infrastructure state when reading persisted refs.

At minimum, the contract must stop claiming the two-exception vocabulary is complete while the shipped backend raises `ValueError` for legal-by-API explicit refs.

## Impact

Recorded call payloads can be written with explicit refs that the only payload-store backend cannot resolve later. That means replay/verification/query paths can fail with an uncaught `ValueError` instead of returning `PURGED`/`HASH_ONLY` or raising `AuditIntegrityError` with context. The result is brittle audit retrieval, broken cache/replay behavior for externally referenced payloads, and a contract violation at a core audit boundary.
