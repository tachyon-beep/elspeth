## Summary

`AzureBlobSink` can write rows missing required schema fields (for CSV this can appear as blank cells) instead of failing fast.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/plugins/azure/blob_sink.py`
- Function/Method: `write`, `_serialize_csv`

## Evidence

- Source report: `docs/bugs/generated/plugins/azure/blob_sink.py.md`
- Sink serialization path does not enforce effective required-field presence pre-write.

## Root Cause Hypothesis

Schema class and serialization exist, but required-field checks were not added to write path.

## Suggested Fix

Validate required fields before serialization, mirroring strict sink behavior.

## Impact

Output artifacts can look valid while violating schema contract.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/azure/blob_sink.py.md`
- Beads: elspeth-rapid-gkrd
