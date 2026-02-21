## Summary

`CSVSink.write()` can partially write a batch before raising, causing sink output to diverge from Landscape state/outcomes for that batch.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/csv_sink.py`
- Line(s): 260-274, 292-304
- Function/Method: `CSVSink.write`, `CSVSink._validate_required_fields_present`

## Evidence

`CSVSink.write()` writes rows one-by-one:

```python
# src/elspeth/plugins/sinks/csv_sink.py:272-274
for row in rows:
    writer.writerow(row)
```

Before that, it only pre-validates **missing required fields** and optional schema validation:

```python
# src/elspeth/plugins/sinks/csv_sink.py:237-245, 292-304
self._validate_required_fields_present(rows)
if self._validate_input and not self._schema_config.is_observed:
    self._schema_class.model_validate(row)
```

It does **not** pre-validate for extra/unexpected keys when `validate_input=False`. The file itself documents reliance on `DictWriter` raising on extras (`extrasaction='raise'`) at `src/elspeth/plugins/sinks/csv_sink.py:195-196`, which occurs during per-row writing.

Integration consequence:

- On any `sink.write()` exception, executor marks all token states FAILED and re-raises (`/home/john/elspeth-rapid/src/elspeth/engine/executors/sink.py:221-227`).
- Artifact registration and token outcome recording only happen on success after flush (`/home/john/elspeth-rapid/src/elspeth/engine/executors/sink.py:255-305`).

So if row 1 writes successfully and row 2 raises, the batch can be partially emitted to CSV while audit states/outcomes for that batch are recorded as failure-only (no successful artifact/outcome path). This is an audit consistency break.

## Root Cause Hypothesis

Batch atomicity is not enforced in `CSVSink.write()`. Validation and serialization checks that can fail are executed during side-effecting writes, not before them.

## Suggested Fix

Make batch writes all-or-nothing within `CSVSink.write()`:

1. Preflight-validate every row against locked `self._fieldnames` (extra keys, required keys) before writing anything.
2. Stage CSV serialization for the entire batch in-memory (`io.StringIO` + `csv.DictWriter`), then do a single file write if staging succeeds.
3. Keep hash update aligned with staged bytes to avoid read-after-write dependency.

Example direction (inside target file):

```python
# preflight: detect unexpected keys for all rows before file write
allowed = set(self._fieldnames or [])
for i, row in enumerate(rows):
    extra = sorted(set(row) - allowed)
    if extra:
        raise ValueError(f"CSVSink row {i} has unexpected fields: {extra}")
```

Then serialize batch to buffer first, and only append buffer to file on success.

## Impact

- CSV output can contain rows that are not represented as successful sink outcomes/artifacts in Landscape.
- Resume/replay behavior can become inconsistent (orphaned output rows, duplicate writes on retry paths).
- Violates auditability guarantees: external artifact state can no longer be cleanly attributable to recorded terminal states.
