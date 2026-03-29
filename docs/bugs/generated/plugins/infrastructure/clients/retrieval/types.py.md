## Summary

`RetrievalChunk.__post_init__()` treats bare `json.dumps(metadata)` success as “valid metadata”, so `NaN`/`Infinity` values slip through and later get embedded into `__rag_sources` provenance as non-standard JSON.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/types.py`
- Line(s): 40-42
- Function/Method: `RetrievalChunk.__post_init__`

## Evidence

`RetrievalChunk` validates metadata with a plain `json.dumps(self.metadata)` call at [`src/elspeth/plugins/infrastructure/clients/retrieval/types.py:40`]( /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/types.py#L40 )-[`42`]( /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/types.py#L42 ). In Python, that is permissive: it accepts `float("nan")` and `float("inf")` and emits `NaN` / `Infinity` tokens instead of rejecting them.

That is inconsistent with ELSPETH’s canonical JSON policy. [`src/elspeth/core/canonical.py:59`]( /home/john/elspeth/src/elspeth/core/canonical.py#L59 )-[`62`]( /home/john/elspeth/src/elspeth/core/canonical.py#L62 ) explicitly raises on non-finite floats, and [`src/elspeth/core/canonical.py:159`]( /home/john/elspeth/src/elspeth/core/canonical.py#L159 )-[`177`]( /home/john/elspeth/src/elspeth/core/canonical.py#L177 ) routes audit serialization through RFC 8785 canonical JSON.

The bad metadata is then propagated directly into the RAG provenance envelope. [`src/elspeth/plugins/transforms/rag/transform.py:260`]( /home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L260 )-[`277`]( /home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L277 ) copies `chunk.metadata` into `sources_envelope` and serializes it with another plain `json.dumps(...)`. So a chunk like `RetrievalChunk(..., metadata={"score_debug": float("nan")})` passes construction and produces a `__rag_sources` string containing `NaN`.

Repo tests show this gap is currently unguarded. [`tests/unit/plugins/infrastructure/clients/retrieval/test_types.py:46`]( /home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_types.py#L46 )-[`65`]( /home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_types.py#L65 ) cover `datetime` and `bytes`, but there is no non-finite metadata case. The RAG pipeline tests only assert that `json.loads()` can read the emitted string, e.g. [`tests/integration/plugins/transforms/test_rag_pipeline.py:22`]( /home/john/elspeth/tests/integration/plugins/transforms/test_rag_pipeline.py#L22 )-[`25`]( /home/john/elspeth/tests/integration/plugins/transforms/test_rag_pipeline.py#L25 ), which does not enforce RFC-compliant JSON.

## Root Cause Hypothesis

The constructor conflates “Python’s stdlib can stringify this object” with “this metadata satisfies ELSPETH’s audit-safe JSON contract.” That works for obvious non-serializable objects, but it misses the project’s stricter invariant that non-finite numbers are forbidden, not merely encodable.

## Suggested Fix

Tighten the metadata check in `RetrievalChunk.__post_init__()` to reject non-finite values explicitly, for example by using `json.dumps(self.metadata, allow_nan=False)` instead of bare `json.dumps(...)`.

If the constructor is meant to enforce the same invariant the rest of the audit stack uses, add a unit test that `metadata={"x": float("nan")}` and `metadata={"x": float("inf")}` both raise `ValueError`.

## Impact

A retrieval provider can return metadata that looks “validated” at the boundary but still becomes invalid provenance JSON in `__rag_sources`. That breaks the contract that audit-adjacent payloads are canonical/standards-compliant, and it risks downstream failures anywhere a strict JSON parser or external consumer reads the provenance blob.
