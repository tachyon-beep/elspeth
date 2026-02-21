## Summary

`skip_rows` accepts negative values without validation, causing silent misconfiguration (`-N` behaves like `0`).

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sources/csv_source.py`
- Line(s): 37
- Function/Method: `CSVSourceConfig` field definition

## Evidence

Config field is unconstrained:

```python
skip_rows: int = 0
```

No validator enforces non-negative values. Runtime behavior uses:

```python
for _ in range(self._skip_rows):
    ...
```

For negative values, `range(negative)` is empty, so no rows are skipped and no error is raised. This silently ignores invalid user intent.

## Root Cause Hypothesis

`skip_rows` was typed as `int` but not bounded. Pydantic therefore accepts negative integers, and loop semantics mask the misconfiguration.

## Suggested Fix

Constrain field at definition (or validator), e.g.:

```python
from pydantic import Field
skip_rows: int = Field(default=0, ge=0)
```

(or a `field_validator` that rejects `< 0`).

## Impact

Misconfigured pipelines can ingest unintended rows without any explicit failure, leading to hard-to-debug data quality issues and incorrect source behavior.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/sources/csv_source.py.md`
- Finding index in source report: 3
- Beads: pending
