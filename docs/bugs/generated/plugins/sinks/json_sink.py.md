## Summary

`JSONSink` can persist a partial JSONL batch before `SinkExecutor` records any terminal state, leaving rows in the output file that have no corresponding completed sink outcome in Landscape.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/sinks/json_sink.py`
- Line(s): 282-337, 396-400
- Function/Method: `write`, `_write_jsonl_batch`, `close`

## Evidence

`write()` sends JSONL batches straight to `_write_jsonl_batch()`:

```python
if self._format == "jsonl":
    self._write_jsonl_batch(output_rows)
```

[`src/elspeth/plugins/sinks/json_sink.py:282`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sinks\/json_sink.py#L282)

`_write_jsonl_batch()` opens the real output file and writes one row at a time:

```python
self._file = open(self._path, file_mode, encoding=self._encoding)
for row in rows:
    json.dump(row, self._file)
    self._file.write("\n")
```

[`src/elspeth/plugins/sinks/json_sink.py:333`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sinks\/json_sink.py#L333)

If row `N` raises during serialization, rows `0..N-1` have already been written to the live file. `SinkExecutor` only records node states and token outcomes after `sink.write()` returns and `sink.flush()` succeeds:

```python
write_result: SinkWriteResult = sink.write(rows, ctx)
...
sink.flush()
...
# node_states/outcomes only recorded afterwards
```

[`src/elspeth/engine/executors/sink.py:230`](\/home\/john\/elspeth\/src\/elspeth\/engine\/executors\/sink.py#L230)

`BaseSink` guarantees `close()` runs even on pipeline error, and `JSONSink.close()` closes the file handle:

```python
- on_complete() and close() run inside a finally block
```

[`src/elspeth/plugins/infrastructure/base.py:356`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/infrastructure\/base.py#L356)

```python
if self._file is not None:
    self._file.close()
```

[`src/elspeth/plugins/sinks/json_sink.py:398`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sinks\/json_sink.py#L398)

So a mid-batch serialization failure can still leave previously written rows flushed by file close, but with no completed sink `node_state`, no token outcome, and no registered artifact. The CSV sink explicitly stages the whole batch first to avoid exactly this audit divergence:

```python
# This prevents partial writes ...
# audit divergence -- CSV has rows the Landscape marks as FAILED.
```

[`src/elspeth/plugins/sinks/csv_sink.py:288`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sinks\/csv_sink.py#L288)

## Root Cause Hypothesis

`JSONSink` optimized the JSONL path for appendable streaming writes, but unlike `CSVSink` it never stages or atomically commits a batch before touching the real file. That breaks ELSPETH’s “durable write first, then audit completion” contract whenever serialization fails after at least one row has already been emitted.

## Suggested Fix

Serialize the entire JSONL batch into memory first, then write the staged text to the real file in one call. Keep schema validation before opening the file. For example:

```python
staging = io.StringIO()
for row in rows:
    json.dump(row, staging, allow_nan=False)
    staging.write("\n")
payload = staging.getvalue()
self._file.write(payload)
```

That preserves the current crash-on-bug behavior while ensuring `sink.write()` either writes the whole batch or writes nothing.

## Impact

A single bad row can create silent output rows that the audit trail never marks as completed. That violates the auditability guarantee that every row reaching a sink has a corresponding terminal sink state and token outcome, and it can produce duplicate or orphaned data on retry/resume workflows.
---
## Summary

`JSONSink` emits non-standard JSON (`NaN`, `Infinity`, `-Infinity`) because it uses Python’s default `json.dump`, even though ELSPETH’s JSON policy and JSON source explicitly reject those values.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/sinks/json_sink.py`
- Line(s): 336, 356
- Function/Method: `_write_jsonl_batch`, `_write_json_array`

## Evidence

Both JSON serialization sites use the default encoder settings:

```python
json.dump(row, self._file)
```

[`src/elspeth/plugins/sinks/json_sink.py:336`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sinks\/json_sink.py#L336)

```python
json.dump(self._rows, f, indent=self._indent)
```

[`src/elspeth/plugins/sinks/json_sink.py:356`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sinks\/json_sink.py#L356)

ELSPETH’s canonical JSON policy says non-finite floats must be rejected:

```python
IMPORTANT: NaN and Infinity are strictly REJECTED
```

[`src/elspeth/core/canonical.py:8`](\/home\/john\/elspeth\/src\/elspeth\/core\/canonical.py#L8)

The JSON source enforces the same rule at parse time:

```python
NOTE: Non-standard JSON constants (NaN, Infinity, -Infinity) are rejected
at parse time per canonical JSON policy.
```

[`src/elspeth/plugins/sources/json_source.py:8`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sources\/json_source.py#L8)

And the integration tests assert that files containing these constants are quarantined:

- [`tests/integration/plugins/sources/test_trust_boundary.py:430`](\/home\/john\/elspeth\/tests\/integration\/plugins\/sources\/test_trust_boundary.py#L430)
- [`tests/integration/plugins/sources/test_trust_boundary.py:456`](\/home\/john\/elspeth\/tests\/integration\/plugins\/sources\/test_trust_boundary.py#L456)
- [`tests/integration/plugins/sources/test_trust_boundary.py:481`](\/home\/john\/elspeth\/tests\/integration\/plugins\/sources\/test_trust_boundary.py#L481)

So `JSONSink` can produce output that ELSPETH’s own `JSONSource` later refuses to ingest.

## Root Cause Hypothesis

The sink relies on Python’s permissive JSON defaults instead of enforcing ELSPETH’s stricter JSON contract at the serialization boundary. That likely happened because the file-writing path was implemented as ordinary JSON output, not as a standards-enforced boundary like the source and canonical layers.

## Suggested Fix

Pass `allow_nan=False` in both JSON serialization paths and add regression tests for `NaN`, `Infinity`, and `-Infinity` in both `json` and `jsonl` formats:

```python
json.dump(row, self._file, allow_nan=False)
json.dump(self._rows, f, indent=self._indent, allow_nan=False)
```

Combined with batch staging for JSONL, this should fail before any partial output is written.

## Impact

The sink can write files that are not valid RFC 8259 JSON and are incompatible with ELSPETH’s own JSON ingestion rules. That creates a round-trip integration break and lets non-finite numeric sentinels leak into persisted outputs instead of failing fast at the sink boundary.
