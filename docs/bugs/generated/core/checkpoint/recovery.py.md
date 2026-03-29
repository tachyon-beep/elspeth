## Summary

Resume payload retrieval in `recovery.py` bypasses ELSPETH's Tier-1 corruption handling, so corrupted or non-UTF-8 row payloads escape as raw low-context exceptions instead of `AuditIntegrityError`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [src/elspeth/core/checkpoint/recovery.py](/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L261)
- Line(s): 261-273
- Function/Method: `RecoveryManager.get_unprocessed_row_data`

## Evidence

`get_unprocessed_row_data()` reads stored row payloads directly and only handles the "purged" case:

```python
try:
    payload_bytes = payload_store.retrieve(source_data_ref)
    degraded_data = json.loads(payload_bytes.decode("utf-8"))
except PayloadNotFoundError as exc:
    raise ValueError(...) from exc
```

Source: [src/elspeth/core/checkpoint/recovery.py](/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L261)

That is incomplete for the payload-store contract. The protocol explicitly says `retrieve()` can also raise integrity failures, not just absence:

```python
Raises:
    PayloadNotFoundError: If content not found
    IntegrityError: If content doesn't match expected hash
```

Source: [src/elspeth/contracts/payload_store.py](/home/john/elspeth/src/elspeth/contracts/payload_store.py#L61)

Elsewhere in the codebase, the same payload path is treated as Tier 1 and wrapped with audit-context-rich `AuditIntegrityError`, including hash-mismatch, storage I/O, bad UTF-8, bad JSON, and wrong top-level type:

```python
except PayloadIntegrityError as e:
    raise AuditIntegrityError(...)
except OSError as e:
    raise AuditIntegrityError(...)
...
except (json.JSONDecodeError, UnicodeDecodeError) as e:
    raise AuditIntegrityError(...)
if type(decoded_data) is not dict:
    raise AuditIntegrityError(...)
```

Sources:
- [src/elspeth/core/landscape/query_repository.py](/home/john/elspeth/src/elspeth/core/landscape/query_repository.py#L165)
- [src/elspeth/core/landscape/execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L1002)

`recovery.py` does none of that, even though resumed row payloads are also "our data" after persistence. Existing tests cover only purge and happy-path restoration, not corruption/integrity failures:

- [tests/unit/core/checkpoint/test_recovery.py](/home/john/elspeth/tests/unit/core/checkpoint/test_recovery.py#L740)
- [tests/unit/core/checkpoint/test_recovery.py](/home/john/elspeth/tests/unit/core/checkpoint/test_recovery.py#L774)

What the code does:
- Returns a contextual `ValueError` for purged payloads.
- Leaks raw `IntegrityError`, `UnicodeDecodeError`, `JSONDecodeError`, or malformed-content failures for every other corruption path.

What it should do:
- Treat persisted row payload corruption as Tier 1 audit corruption and raise `AuditIntegrityError` with `run_id`, `row_id`, and `source_data_ref`.

## Root Cause Hypothesis

`RecoveryManager.get_unprocessed_row_data()` reimplemented payload retrieval inline instead of reusing the repository's established Tier-1 payload parsing/wrapping logic. During that duplication, only the retention/purge path was handled, while corruption and decode failures were omitted.

## Suggested Fix

Wrap all persisted-payload corruption paths exactly as the query repositories do, or extract/shared-reuse a helper for "retrieve + decode + validate dict" behavior.

Example shape:

```python
from elspeth.contracts.payload_store import IntegrityError as PayloadIntegrityError

try:
    payload_bytes = payload_store.retrieve(source_data_ref)
except PayloadNotFoundError as exc:
    raise ValueError(f"Row {row_id} payload has been purged (hash={exc.content_hash}) - cannot resume") from exc
except PayloadIntegrityError as exc:
    raise AuditIntegrityError(
        f"Payload integrity check failed for row {row_id} (ref={source_data_ref}) during resume: {exc}"
    ) from exc
except OSError as exc:
    raise AuditIntegrityError(
        f"Payload retrieval failed for row {row_id} (ref={source_data_ref}) during resume: {type(exc).__name__}: {exc}"
    ) from exc

try:
    degraded_data = json.loads(payload_bytes.decode("utf-8"))
except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    raise AuditIntegrityError(
        f"Corrupt payload for row {row_id} (ref={source_data_ref}) during resume: {exc}"
    ) from exc

if type(degraded_data) is not dict:
    raise AuditIntegrityError(
        f"Corrupt payload for row {row_id} (ref={source_data_ref}) during resume: expected JSON object, got {type(degraded_data).__name__}"
    )
```

Add unit coverage for:
- payload hash mismatch
- invalid UTF-8
- invalid JSON
- non-dict JSON payload

## Impact

A damaged persisted row payload can currently abort resume with the wrong exception type and poor context, weakening ELSPETH's Tier-1 "crash immediately with maximal evidence" contract. Operators get a less actionable failure, and audit corruption is not classified consistently with the rest of the Landscape read path.
