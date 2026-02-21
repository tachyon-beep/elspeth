## Summary

`explain_row()` silently treats an invalid empty `source_data_ref` as "no payload," masking a Tier-1 audit anomaly instead of crashing.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — truthiness check inconsistency; write path always produces SHA-256 hash, never empty string)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py`
- Line(s): 421
- Function/Method: `explain_row`

## Evidence

`explain_row()` gates payload loading with a truthiness check:

```python
if row.source_data_ref and self._payload_store:
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py:421`)

This means `source_data_ref=""` is treated as absent and skipped, returning lineage with `payload_available=False` instead of surfacing corruption.

In the same module, `get_row_data()` uses explicit `None` checks, not truthiness:

```python
if row.source_data_ref is None:
    return RowDataResult(state=RowDataState.NEVER_STORED, data=None)
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py:137`)

Also, `source_data_ref` is nullable but not constrained non-empty in schema (`/home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py:122`), and `create_row()` accepts `payload_ref` directly (`/home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py:56`, `:100`), so bad refs can enter.

## Root Cause Hypothesis

A convenience truthiness check (`if row.source_data_ref`) was used instead of strict invariant checks for Tier-1 data (`None` vs invalid value), causing invalid-but-falsy values to be silently downgraded to "payload unavailable."

## Suggested Fix

In `explain_row()`, switch to strict checks:

- Use `row.source_data_ref is not None` and `self._payload_store is not None`.
- Explicitly reject `""` (and optionally malformed refs) with `AuditIntegrityError`.
- Keep `KeyError` as the only graceful "purged" path.

## Impact

Audit integrity is weakened: a corrupted `source_data_ref` can be hidden as normal payload absence, violating crash-on-corruption expectations and potentially misleading lineage investigations.

## Triage

Triage: Downgraded P1→P2. Inconsistency with get_row_data() which correctly uses is-not-None. Write path uses content-addressed store returning SHA-256 hex. Fix is trivial: change to is not None.
