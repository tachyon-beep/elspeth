## Summary

Exporter output silently drops creation timestamps for `node`, `edge`, `row`, `token`, and `artifact` records, so the “self-contained” audit export cannot reconstruct the full execution chronology from the export alone.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/exporter.py
- Line(s): 250-265, 270-278, 374-381, 386-396, 593-602
- Function/Method: `LandscapeExporter._iter_records`

## Evidence

`exporter.py` builds these records without the timestamp fields that exist in the Tier 1 audit models:

```python
# src/elspeth/core/landscape/exporter.py
node_record = {
    "record_type": "node",
    ...
    "sequence_in_pipeline": node.sequence_in_pipeline,
}

edge_record = {
    "record_type": "edge",
    ...
    "default_mode": edge.default_mode.value,
}

row_record = {
    "record_type": "row",
    ...
    "source_data_hash": row.source_data_hash,
}

token_record = {
    "record_type": "token",
    ...
    "expand_group_id": token.expand_group_id,
}

artifact_record = {
    "record_type": "artifact",
    ...
    "size_bytes": artifact.size_bytes,
}
```

The underlying audit contracts do carry those timestamps:

- `Node.registered_at`: [/home/john/elspeth/src/elspeth/contracts/audit.py:82](/home/john/elspeth/src/elspeth/contracts/audit.py#L82)
- `Edge.created_at`: [/home/john/elspeth/src/elspeth/contracts/audit.py:112](/home/john/elspeth/src/elspeth/contracts/audit.py#L112)
- `Row.created_at`: [/home/john/elspeth/src/elspeth/contracts/audit.py:126](/home/john/elspeth/src/elspeth/contracts/audit.py#L126)
- `Token.created_at`: [/home/john/elspeth/src/elspeth/contracts/audit.py:142](/home/john/elspeth/src/elspeth/contracts/audit.py#L142)
- `Artifact.created_at`: [/home/john/elspeth/src/elspeth/contracts/audit.py:341](/home/john/elspeth/src/elspeth/contracts/audit.py#L341)

The export schema also omits them, confirming the loss happens at export time rather than storage time:

- [/home/john/elspeth/src/elspeth/contracts/export_records.py:38](/home/john/elspeth/src/elspeth/contracts/export_records.py#L38)
- [/home/john/elspeth/src/elspeth/contracts/export_records.py:54](/home/john/elspeth/src/elspeth/contracts/export_records.py#L54)
- [/home/john/elspeth/src/elspeth/contracts/export_records.py:104](/home/john/elspeth/src/elspeth/contracts/export_records.py#L104)
- [/home/john/elspeth/src/elspeth/contracts/export_records.py:113](/home/john/elspeth/src/elspeth/contracts/export_records.py#L113)
- [/home/john/elspeth/src/elspeth/contracts/export_records.py:213](/home/john/elspeth/src/elspeth/contracts/export_records.py#L213)

Tests explicitly protect timestamp export for `run`, `operation`, `call`, `routing_event`, and `batch`, but not these omitted record types:

- [/home/john/elspeth/tests/unit/core/landscape/test_exporter.py:941](/home/john/elspeth/tests/unit/core/landscape/test_exporter.py#L941)

What the code does: exports partial record metadata.

What it should do: export all recorded chronology fields needed for third-party timeline reconstruction.

## Root Cause Hypothesis

The exporter was built record-type-by-record-type and only some timestamp-bearing models were mapped to export fields. The “full audit data” promise was enforced for a subset of record types, but `node`, `edge`, `row`, `token`, and `artifact` never got the same timestamp preservation treatment.

## Suggested Fix

Add ISO-8601 timestamp fields to the affected export records and emit them in `_iter_records()`.

Example shape:

```python
"registered_at": node.registered_at.isoformat(),
"created_at": edge.created_at.isoformat(),
"created_at": row.created_at.isoformat(),
"created_at": token.created_at.isoformat(),
"created_at": artifact.created_at.isoformat(),
```

Also update:

- `src/elspeth/contracts/export_records.py`
- `tests/unit/core/landscape/test_exporter.py`

## Impact

The exported bundle is not actually self-contained for chronology-sensitive audit questions. An external reviewer cannot determine when nodes were registered, edges created, rows ingested, tokens spawned, or artifacts written without going back to the original database, which violates the stated export goal for compliance and legal inquiry.
---
## Summary

Artifact export omits `idempotency_key`, so retry-deduplication provenance recorded in Landscape is lost from the exported audit bundle.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/exporter.py
- Line(s): 593-602
- Function/Method: `LandscapeExporter._iter_records`

## Evidence

Artifacts are recorded with an optional retry deduplication key:

- `Artifact.idempotency_key`: [/home/john/elspeth/src/elspeth/contracts/audit.py:353](/home/john/elspeth/src/elspeth/contracts/audit.py#L353)
- Repository API documents it as “for retry deduplication”: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:1415](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L1415)
- It is persisted on insert: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:1449](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L1449)
- Tests verify it is stored: [/home/john/elspeth/tests/unit/core/landscape/test_batch_recording.py:1030](/home/john/elspeth/tests/unit/core/landscape/test_batch_recording.py#L1030), [/home/john/elspeth/tests/unit/core/landscape/test_execution_repository.py:1061](/home/john/elspeth/tests/unit/core/landscape/test_execution_repository.py#L1061)

But the exporter drops it:

```python
artifact_record = {
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

The export record contract omits it too:

- [/home/john/elspeth/src/elspeth/contracts/export_records.py:213](/home/john/elspeth/src/elspeth/contracts/export_records.py#L213)

What the code does: exports sink output identity without the retry/dedupe key.

What it should do: include the dedupe key when present, because it is part of the recorded artifact provenance.

## Root Cause Hypothesis

`ArtifactExportRecord` was defined before retry-deduplication metadata was added to `Artifact`, and the exporter mapping was never updated when `idempotency_key` became part of the persisted model.

## Suggested Fix

Add `idempotency_key: str | None` to `ArtifactExportRecord` and emit:

```python
"idempotency_key": artifact.idempotency_key,
```

Also add exporter tests that cover artifacts with and without an idempotency key.

## Impact

On exported evidence alone, an auditor cannot tell whether two sink writes were separate business outputs or retries of the same logical write. That weakens post-export analysis of sink retry behavior and deduplication correctness.
