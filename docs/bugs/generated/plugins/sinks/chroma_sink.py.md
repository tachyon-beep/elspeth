## Summary

Rows with all configured metadata fields absent are serialized as empty metadata dicts, which this sink’s own comment says Chroma rejects; one such row can fail the entire batch instead of being omitted or diverted.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py
- Line(s): 246-273, 321-327, 342-348, 364-370
- Function/Method: `ChromaSink.write`

## Evidence

`write()` treats each configured metadata field as optional and skips missing keys:

```python
for field in fm.metadata_fields:
    try:
        value = row[field]
    except KeyError:
        # Missing metadata field — skip it (metadata is optional per-field)
        continue
...
metadatas_list.append(meta)
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:249-266`

But if every configured metadata field is missing for a row, `meta` stays `{}` and still gets appended. A few lines later the file states:

```python
# ChromaDB rejects empty metadata dicts — pass None when no metadata fields configured
metadatas: list[dict[str, Any]] | None = metadatas_list if fm.metadata_fields else None
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:272-273`

So with `metadata_fields=["topic"]` and a row like `{"doc_id": "d1", "text": "hello"}`, the sink sends `metadatas=[{}]` to `collection.upsert()`/`add()`. If Chroma rejects empty dicts as the comment says, the code converts that `ValueError` into `_ChromaPayloadRejection` and fails the whole batch:

```python
collection.upsert(..., metadatas=metadatas)
except ValueError as ve:
    raise _ChromaPayloadRejection(str(ve)) from ve
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:321-327`

There is no test covering “metadata field configured but absent on a row”; current tests only cover valid scalars, `None`, and explicitly invalid container types. See `/home/john/elspeth/tests/unit/plugins/sinks/test_chroma_sink.py:417-519`.

## Root Cause Hypothesis

The implementation conflates two cases:

1. No metadata configured for the sink at all.
2. Metadata configured, but a specific row has no present metadata values.

Only case 1 is mapped to `metadatas=None`. Case 2 still produces `{}` per row, even though the code already knows Chroma rejects empty dict metadata payloads.

## Suggested Fix

Partition rows so rows with no present metadata are not sent with `{}` metadata entries. For example:

- Build one batch for rows with non-empty metadata dicts and send `metadatas=[...]`.
- Build a second batch for rows with no metadata and send that batch with `metadatas=None`.

If mixed batching is undesirable, another acceptable fix is to divert rows whose configured metadata set resolves to empty, but that is less aligned with the current “metadata is optional per-field” comment.

## Impact

A single row missing all optional metadata can make `overwrite`, `skip`, or `error` mode fail at the Chroma call boundary and block otherwise valid rows in the same batch. That breaks the intended per-row handling for sink-boundary data issues and turns a row-local omission into a batch-wide failure.
---
## Summary

The sink accepts non-finite float metadata (`NaN`, `Infinity`) but later hashes the outbound payload with `canonical_json()`, which strictly rejects those values; this can crash after a successful Chroma write and leave the external side effect without the intended audit record.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py
- Line(s): 177-185, 255-258, 399-426
- Function/Method: `ChromaSink._compute_payload_hash`, `ChromaSink.write`

## Evidence

The sink’s metadata validator allows any `float` value:

```python
if value is not None and not isinstance(value, (str, int, float, bool)):
    bad_fields[field] = type(value).__name__
else:
    meta[field] = value
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:255-258`

It then hashes the actual payload sent to Chroma:

```python
payload = canonical_json({"ids": ids, "documents": documents, "metadatas": metadatas})
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:183`

`canonical_json()` rejects non-finite floats by design:

```python
if isinstance(obj, float | np.floating):
    if math.isnan(obj) or math.isinf(obj):
        raise ValueError(...)
```

Source: `/home/john/elspeth/src/elspeth/core/canonical.py:60-63`

Critically, the hash is computed after the Chroma write succeeds and outside the error-recording `except` block:

```python
# after successful upsert/add
content_hash, payload_size = self._compute_payload_hash(write_ids, write_documents, write_metadatas)

...
ctx.record_call(...)
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:399-426`

So a row containing metadata like `{"score": float("nan")}` passes local validation, may be written to Chroma, then raises `ValueError` during hashing before `ctx.record_call()` runs. The existing tests explicitly accept generic floats and do not cover non-finite values. See `/home/john/elspeth/tests/unit/plugins/sinks/test_chroma_sink.py:417-445`.

## Root Cause Hypothesis

Validation in `write()` checks only Python type membership, not the canonical-audit invariants that the same payload must satisfy later. The sink therefore admits values that its own audit hashing path cannot serialize.

## Suggested Fix

Reject non-finite floats during metadata validation, before any Chroma call. A local helper using `math.isfinite()` for float values is sufficient. The rejection should happen per row, with diversion if this sink wants to preserve row-local handling, or with an offensive crash if the project decides non-finite pipeline floats are always upstream bugs.

## Impact

This creates a bad failure mode: the external system may already contain the new document while ELSPETH crashes before recording the successful call metadata and content hash. That undermines the audit trail’s “write happened and we can prove exactly what was sent” guarantee.
