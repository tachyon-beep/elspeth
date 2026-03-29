## Summary

`RowExportRecord` and `ArtifactExportRecord` are missing persisted audit fields, so the export contract silently drops `rows.source_data_ref` and `artifacts.idempotency_key` from audit exports.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/export_records.py`
- Line(s): 104-111, 213-223
- Function/Method: `RowExportRecord`, `ArtifactExportRecord`

## Evidence

`export_records.py` defines the exported row and artifact shapes, but those TypedDicts omit fields that are present in the authoritative audit contracts and database schema:

```python
# /home/john/elspeth/src/elspeth/contracts/export_records.py:104-111
class RowExportRecord(TypedDict):
    record_type: Literal["row"]
    run_id: str
    row_id: str
    row_index: int
    source_node_id: str
    source_data_hash: str | None

# /home/john/elspeth/src/elspeth/contracts/export_records.py:213-223
class ArtifactExportRecord(TypedDict):
    record_type: Literal["artifact"]
    run_id: str
    artifact_id: str
    sink_node_id: str
    produced_by_state_id: str | None
    artifact_type: str
    path_or_uri: str | None
    content_hash: str | None
    size_bytes: int | None
```

The underlying Tier-1 contracts do have those fields:

- [`/home/john/elspeth/src/elspeth/contracts/audit.py#L129`](\/home/john/elspeth/src/elspeth/contracts/audit.py#L129) through [`/home/john/elspeth/src/elspeth/contracts/audit.py#L135`](\/home/john/elspeth/src/elspeth/contracts/audit.py#L135): `Row.source_data_ref`
- [`/home/john/elspeth/src/elspeth/contracts/audit.py#L344`](\/home/john/elspeth/src/elspeth/contracts/audit.py#L344) through [`/home/john/elspeth/src/elspeth/contracts/audit.py#L353`](\/home/john/elspeth/src/elspeth/contracts/audit.py#L353): `Artifact.idempotency_key`

The database schema persists them too:

- [`/home/john/elspeth/src/elspeth/core/landscape/schema.py#L121`](\/home/john/elspeth/src/elspeth/core/landscape/schema.py#L121) through [`/home/john/elspeth/src/elspeth/core/landscape/schema.py#L127`](\/home/john/elspeth/src/elspeth/core/landscape/schema.py#L127): `rows.source_data_ref`
- [`/home/john/elspeth/src/elspeth/core/landscape/schema.py#L321`](\/home/john/elspeth/src/elspeth/core/landscape/schema.py#L321) through [`/home/john/elspeth/src/elspeth/core/landscape/schema.py#L327`](\/home/john/elspeth/src/elspeth/core/landscape/schema.py#L327): `artifacts.idempotency_key`

The exporter then emits records that match the incomplete TypedDicts, so the data is actually lost from exports:

```python
# /home/john/elspeth/src/elspeth/core/landscape/exporter.py:374-381
row_record: RowExportRecord = {
    "record_type": "row",
    "run_id": run_id,
    "row_id": row.row_id,
    "row_index": row.row_index,
    "source_node_id": row.source_node_id,
    "source_data_hash": row.source_data_hash,
}

# /home/john/elspeth/src/elspeth/core/landscape/exporter.py:593-603
artifact_record: ArtifactExportRecord = {
    "record_type": "artifact",
    "run_id": run_id,
    "artifact_id": artifact.artifact_id,
    "sink_node_id": artifact.sink_node_id,
    "produced_by_state_id": artifact.produced_by_state_id,
    "artifact_type": artifact.artifact_type,
    "path_or_uri": artifact.path_or_uri,
    "content_hash": artifact.content_hash,
    "size_bytes": artifact.size_bytes,
}
```

Why those fields matter:

- [`/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L255`](\/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L255) through [`/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L258`](\/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L258) treats missing `source_data_ref` as an audit-integrity failure: “cannot resume without payload”.
- [`/home/john/elspeth/tests/integration/audit/test_recorder_artifacts.py#L113`](\/home/john/elspeth/tests/integration/audit/test_recorder_artifacts.py#L113) through [`/home/john/elspeth/tests/integration/audit/test_recorder_artifacts.py#L174`](\/home/john/elspeth/tests/integration/audit/test_recorder_artifacts.py#L174) explicitly documents `idempotency_key` as the retry-deduplication key that must be persisted.
- [`/home/john/elspeth/docs/architecture/overview.md#L646`](\/home/john/elspeth/docs/architecture/overview.md#L646) describes sink idempotency keys as part of delivery semantics.

So the code exports “complete audit data” in name, but not in fact, because two persisted audit fields disappear at the export boundary.

## Root Cause Hypothesis

`export_records.py` drifted behind the Tier-1 audit schema after `rows.source_data_ref` and `artifacts.idempotency_key` were added elsewhere. Because `LandscapeExporter` constructs typed records against these TypedDicts, the stale contract made the omission look type-correct, and there are no export tests asserting these fields survive into exported records.

## Suggested Fix

Add the missing fields to the target TypedDicts, then update the exporter and exporter tests to populate/assert them.

Helpful shape:

```python
class RowExportRecord(TypedDict):
    record_type: Literal["row"]
    run_id: str
    row_id: str
    row_index: int
    source_node_id: str
    source_data_hash: str
    source_data_ref: str | None

class ArtifactExportRecord(TypedDict):
    record_type: Literal["artifact"]
    run_id: str
    artifact_id: str
    sink_node_id: str
    produced_by_state_id: str
    artifact_type: str
    path_or_uri: str
    content_hash: str
    size_bytes: int
    idempotency_key: str | None
```

Then extend:

- [`/home/john/elspeth/src/elspeth/core/landscape/exporter.py`](\/home/john/elspeth/src/elspeth/core/landscape/exporter.py) to emit `row.source_data_ref` and `artifact.idempotency_key`
- [`/home/john/elspeth/tests/unit/core/landscape/test_exporter.py`](\/home/john/elspeth/tests/unit/core/landscape/test_exporter.py) to assert both fields are exported
- [`/home/john/elspeth/tests/unit/contracts/test_export_records.py`](\/home/john/elspeth/tests/unit/contracts/test_export_records.py) to cover the new contract fields

## Impact

Audit exports are incomplete relative to the Landscape source of truth. Consumers of exported runs cannot see:

- which retained payload ref backs each source row
- which idempotency key a sink used to deduplicate retry side effects

That weakens traceability for exported audits, especially around source-payload recovery and explaining why a retried sink write did or did not create duplicate artifacts.
