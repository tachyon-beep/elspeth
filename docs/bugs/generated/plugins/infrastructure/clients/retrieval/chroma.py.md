## Summary

Chroma query failures are never written to the Landscape audit trail: `search()` raises `RetrievalError` on the failure path, but only records `record_call(... status=SUCCESS ...)` after a successful query.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py
- Line(s): 185-193, 252-264
- Function/Method: `ChromaSearchProvider.search`

## Evidence

`search()` wraps the SDK call, but on exception it immediately re-raises as `RetrievalError`:

```python
start_time = time.monotonic()
try:
    results = self._collection.query(...)
except Exception as exc:
    raise RetrievalError(f"Chroma query failed: {exc}", retryable=True) from exc
```

Only the success path records an audit call:

```python
if self._recorder is not None:
    call_index = self._recorder.allocate_call_index(state_id)
    self._recorder.record_call(
        ...,
        status=CallStatus.SUCCESS,
        ...
    )
```

So if Chroma times out, disconnects, or rejects the request, the call vanishes from the audit trail entirely.

Nearby infrastructure follows the opposite pattern and records failures before re-raising:
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:309-331`
- `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:373-397`

That matches ELSPETH’s audit rule that failed external calls are still auditable facts.

## Root Cause Hypothesis

The provider was built around “manual success auditing” because it uses the Chroma SDK directly instead of `AuditedHTTPClient`, but the error branch never got the matching `CallStatus.ERROR` recording logic.

## Suggested Fix

Allocate the call index before the external query, and record both outcomes:

- On success: keep the existing `SUCCESS` record.
- On SDK/infrastructure failure: record `ERROR` with the request payload, error type/message, and latency, then raise `RetrievalError`.
- If audit recording itself fails, raise an audit-integrity exception rather than silently losing the call.

## Impact

When Chroma search fails, the Landscape has no corresponding call record, no request hash, and no terminal error payload for that external interaction. Retries/quarantines can happen with no auditable evidence of the underlying call failure, which breaks “if it’s not recorded, it didn’t happen.”
---
## Summary

The retrieval provider creates missing Chroma collections during startup, so readiness can never truthfully report “not found”; a typoed or absent collection is silently mutated into an empty collection.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py
- Line(s): 145-149, 281-300
- Function/Method: `ChromaSearchProvider.__init__`, `ChromaSearchProvider.check_readiness`

## Evidence

Constructor eagerly does this:

```python
self._collection = self._client.get_or_create_collection(
    name=config.collection,
    metadata={"hnsw:space": config.distance_function},
)
```

But the readiness method claims it is checking whether the collection exists and has documents:

```python
"""Check that the ChromaDB collection exists and has documents."""
count = self._collection.count()
```

Once `get_or_create_collection()` has run, “missing collection” is no longer representable; the provider has already created it.

The repo’s explicit probe code uses `get_collection()` and preserves the distinction:

- `/home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py:64-83`

The transform also records readiness as an auditable fact before failing startup:

- `/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py:135-152`

With the current target-file behavior, that readiness record can only say “empty”, not “not found”, even when the collection did not exist before startup.

## Root Cause Hypothesis

Connection setup and collection existence validation were conflated in `__init__`. Using the sink-style creation API in a retrieval client erased an important operational state.

## Suggested Fix

Do not create collections in the retrieval client constructor.

A safer shape is:

- `__init__`: build only the Chroma client.
- `check_readiness()`: call `get_collection()` and return `CollectionReadinessResult(..., message="not found")` when absent.
- `search()`: resolve the collection with `get_collection()` after readiness has passed, or cache a collection object obtained without creating it.

## Impact

Startup against the wrong collection name mutates persistent/remote Chroma state and records a misleading readiness fact. Operators and auditors lose the distinction between “the corpus was empty” and “the corpus did not exist,” which matters for root-cause analysis and operational safety.
---
## Summary

Several Chroma search failure paths escape as raw exceptions instead of `RetrievalError`, so the RAG transform’s retry/quarantine contract is bypassed and the run can crash on malformed provider data or transient count failures.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py
- Line(s): 180-183, 198-215, 219-247
- Function/Method: `ChromaSearchProvider.search`

## Evidence

The provider protocol promises `RetrievalError` on search failures:

- `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/base.py:34-60`

The transform only handles `RetrievalError`:

- `/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py:181-201`

But `search()` has uncaught branches:

1. Pre-query `count()` is outside any wrapper:

```python
collection_count = self._collection.count()
if collection_count == 0:
    return []
```

A remote `ConnectionError`/`ChromaError` here leaks as a raw exception.

2. Post-parse normalization can still throw raw exceptions:

```python
for doc, distance, metadata, doc_id in zip(documents, distances, metadatas, ids, strict=True):
    ...
    metadata=dict(metadata) if metadata else {},
```

If Chroma returns mismatched list lengths, `zip(..., strict=True)` raises raw `ValueError`.
If metadata is a non-mapping truthy value, `dict(metadata)` raises raw `TypeError`.

Only the initial key/index extraction is converted to `RetrievalError`; these later Tier 3 shape violations are not.

## Root Cause Hypothesis

The method partially treats Chroma responses as a trust boundary, but the wrapping stops too early. Validation was added around the obvious dict access, not around the full response-normalization path.

## Suggested Fix

Convert all external/integration failure paths in `search()` into `RetrievalError`:

- Wrap `count()` or remove it entirely and let Chroma return fewer than `top_k`.
- Wrap result normalization so `ValueError`/`TypeError` caused by malformed Chroma payloads become non-retryable `RetrievalError` with context.
- Keep genuine programming errors unwrapped, but classify SDK/response-shape issues consistently as provider failures.

## Impact

A transient Chroma outage or malformed SDK response can crash the run outside the retrieval error contract, skipping the transform’s intended retry/quarantine behavior. That makes failure handling inconsistent and turns external-boundary problems into hard pipeline crashes.
