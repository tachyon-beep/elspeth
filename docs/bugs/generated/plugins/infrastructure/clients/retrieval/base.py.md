## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/base.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/base.py
- Line(s): 12-74
- Function/Method: `RetrievalError`, `RetrievalProvider`

## Evidence

`[base.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/base.py#L12)` defines a minimal error/protocol contract:
```python
class RetrievalError(PluginRetryableError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message, retryable=retryable, status_code=status_code)

@runtime_checkable
class RetrievalProvider(Protocol):
    def search(..., *, state_id: str, token_id: str | None) -> list[RetrievalChunk]: ...
    def check_readiness(self) -> CollectionReadinessResult: ...
    def close(self) -> None: ...
```

The concrete providers match that contract in current repo usage:
- `[azure_search.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py#L128)` implements `search`, `[azure_search.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py#L301)` implements `check_readiness`, and `[azure_search.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py#L365)` implements `close`.
- `[chroma.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py#L171)` implements `search`, `[chroma.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py#L281)` implements `check_readiness`, and `[chroma.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py#L309)` implements `close`.

The transform consumes the protocol consistently:
- `[transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L135)` calls `check_readiness()`.
- `[transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L192)` calls `search(..., state_id=..., token_id=...)`.
- `[transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L322)` calls `close()`.

Tests also cover the current contract shape:
- `[test_transform.py](/home/john/elspeth/tests/unit/plugins/transforms/rag/test_transform.py#L191)` verifies retryable `RetrievalError` propagates.
- `[test_transform.py](/home/john/elspeth/tests/unit/plugins/transforms/rag/test_transform.py#L205)` verifies non-retryable `RetrievalError` becomes `TransformResult.error`.
- `[test_chroma.py](/home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py#L289)` verifies `isinstance(provider, RetrievalProvider)`.

I checked for protocol mismatches, missing required methods, schema/return-type inconsistencies, and obvious audit-lineage gaps whose primary fix would live in `base.py`; none were concretely demonstrated from current integrations.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No change recommended in `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/base.py` based on current evidence.

## Impact

No confirmed breakage attributable to this file. Residual risk is limited to future provider implementations violating the protocol in ways not caught by current tests, but I did not find a present, concrete defect whose primary fix belongs in `base.py`.
