## Summary

`CSVSource._load_from_file()` continues reading after `csv.Error` in the main row loop, even though the same file already documents that `csv.Error` leaves `csv.reader` in an untrustworthy state; this can silently drop or misattribute subsequent rows.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sources/csv_source.py
- Line(s): 352-377
- Function/Method: `_load_from_file`

## Evidence

`csv_source.py` explicitly treats `csv.Error` during `skip_rows` as a parser-corruption boundary and stops processing:

```python
# src/elspeth/plugins/sources/csv_source.py:220-222
# csv.Error during skip means the parser consumed an unknown amount
# of data ... We record the error and stop processing to avoid silent data loss
```

```python
# src/elspeth/plugins/sources/csv_source.py:249-251
# Parser error during skip — the csv reader state may be corrupted ...
# and stop processing to prevent silent data loss.
```

But the exact same `csv.reader` object is handled differently once data-row iteration begins:

```python
# src/elspeth/plugins/sources/csv_source.py:352-377
except csv.Error as e:
    ...
    if self._on_validation_failure != "discard":
        yield SourceRow.quarantined(...)
    continue  # Skip to next row
```

So the file already acknowledges "`csv.Error` may have consumed an unknown amount of data" for this parser, but only enforces stop-on-corruption in the preamble path, not in the main row path.

The tests also reinforce that stop-on-`csv.Error` is the intended safety property when parser state may be corrupted, but only cover the `skip_rows` branch:
- [tests/unit/plugins/sources/test_csv_source.py](/home/john/elspeth/tests/unit/plugins/sources/test_csv_source.py#L457)
- [tests/unit/plugins/sources/test_csv_source.py](/home/john/elspeth/tests/unit/plugins/sources/test_csv_source.py#L976)

What the code does now:
- Records one quarantined pseudo-row for the parse failure.
- Calls `continue`, allowing the possibly-corrupted `csv.reader` to keep emitting rows.

What it should do:
- Treat a body-loop `csv.Error` the same way as the `skip_rows` path: record/quarantine once, then stop reading because subsequent row boundaries are no longer trustworthy.

## Root Cause Hypothesis

The file was partially hardened after discovering parser-state corruption in the `skip_rows` path, but the same invariant was not propagated to the main row-reading loop. The implementation still assumes a row-level `csv.Error` is localized to one row, even though the surrounding comments already state that malformed quoting can consume later input and invalidate subsequent iteration state.

## Suggested Fix

Change the `except csv.Error` block in the main row loop to stop processing after recording the parse failure, instead of continuing.

Conceptually:

```python
except csv.Error as e:
    ...
    if self._on_validation_failure != "discard":
        yield SourceRow.quarantined(...)
    return  # parser state is no longer trustworthy
```

If preserving additional context is helpful, the error message should explicitly say processing stopped because later rows may have been consumed by the malformed record.

## Impact

A malformed CSV record in the body can cause later rows to be skipped, merged, or misnumbered without receiving their own terminal outcomes. That is an audit-trail violation: rows from the external source can disappear after a single parse failure, and the system can no longer honestly prove what happened to the remainder of the file.
