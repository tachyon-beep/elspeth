## Summary

`JSONSink` in `mode="append"` can append to an existing JSONL file without validating schema compatibility, allowing silent schema drift/corruption in normal (non-resume) runs.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 — append mode is uncommon in normal runs, resume path already validates, JSONL is inherently schema-flexible

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/json_sink.py`
- Line(s): `43`, `104-195`, `309-322`
- Function/Method: `JSONSink.write`, `JSONSink._write_jsonl_batch`, `JSONSink.validate_output_target`

## Evidence

`JSONSink` exposes append mode:

```python
# json_sink.py
mode: Literal["write", "append"] = "write"
```

It has a validator method (`validate_output_target`) but the normal append write path does not call it:

```python
# json_sink.py:_write_jsonl_batch
if self._file is None:
    file_mode = "a" if self._mode == "append" else "w"
    self._file = open(self._path, file_mode, encoding=self._encoding)

for row in rows:
    json.dump(row, self._file)
    self._file.write("\n")
```

By contrast, CSV append explicitly validates before appending (`/home/john/elspeth-rapid/src/elspeth/plugins/sinks/csv_sink.py:340-352`).

Engine normal-run sink execution just calls `sink.write(...)` (`/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:292-323`) and does not pre-validate output target; only CLI resume path does (`/home/john/elspeth-rapid/src/elspeth/cli.py:1769`).

So `mode="append"` in normal runs can append into incompatible JSONL structure without failure.

## Root Cause Hypothesis

Schema compatibility checks for JSONL were implemented for resume workflows, but not enforced inside the append write path itself, leaving a gap for direct append-mode runs.

## Suggested Fix

In `JSONSink._write_jsonl_batch`, before first append open (`self._file is None and self._mode == "append"`), call `validate_output_target()` and raise `ValueError` if invalid (including missing/extra field diagnostics), mirroring CSV sink behavior.

Also add tests for JSONL append-mode schema mismatch (fixed/flexible).

## Impact

Rows can be written into structurally incompatible JSONL files while run states still complete successfully, violating sink schema contracts and creating hard-to-audit mixed-schema artifacts.
