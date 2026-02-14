# Plugins-Sources Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | JSONSource crashes on invalid byte sequences in JSON array mode | json_source.py | P1 | P1 | Confirmed |
| 2 | skip_rows can silently drop all remaining CSV data | csv_source.py | P1 | P2 | Downgraded |
| 3 | UnicodeDecodeError from CSV file reads is unhandled | csv_source.py | P2 | P2 | Confirmed |
| 4 | skip_rows accepts negative values without validation | csv_source.py | P3 | P3 | Confirmed |

**Result:** 3 confirmed (1 P1, 1 P2, 1 P3), 1 downgraded.

## Detailed Assessments

### Bug 1: JSONSource crashes on invalid byte sequences in JSON array mode (P1 confirmed)

Genuine P1. The asymmetry between JSONL and JSON array error handling is clear in the source code:

- **JSONL mode** (lines 186-238): Opens with `errors="surrogateescape"`, explicitly detects surrogate chars, handles `UnicodeDecodeError` in a file-level except block, and quarantines all encoding failures.
- **JSON array mode** (lines 240-261): Opens with `encoding=self._encoding` (strict, no error handler), and only catches `json.JSONDecodeError` and `ValueError`. A `UnicodeDecodeError` from `json.load()` on a file with invalid bytes will propagate uncaught.

This is a Tier 3 boundary violation: external JSON files with invalid byte sequences should be quarantined, not crash the pipeline. The fix is a one-line addition of `UnicodeDecodeError` to the except clause at line 246, matching the JSONL behavior.

### Bug 2: skip_rows silently drops all remaining CSV data (P1 -> P2)

The bug mechanism is real but the severity is overstated. The analysis claims that `contextlib.suppress(csv.Error)` during skip processing (lines 143-145) can cause the csv.reader to consume subsequent valid rows as part of a malformed logical record.

However:
1. **Python 3.13 csv is very lenient:** As noted in the test file (`test_csv_source.py:463-465`), the csv module rarely raises `csv.Error`. Unmatched quotes in non-strict mode cause the reader to consume subsequent lines into one logical row -- but this happens *without* raising, so the suppress has no effect.
2. **The suppress catches csv.Error, but the real problem is the multi-line consumption without error:** The preamble rows are often metadata/comments that happen to contain quotes. The reader advancing past valid data is a side effect of csv parsing semantics, not of error suppression.
3. **The scenario requires a specific file format:** A preamble row with an unmatched quote, followed immediately by the CSV header and data rows, where the quote causes multi-line consumption. This is a narrow real-world scenario.

Downgraded to P2 because: the data loss is real when triggered, but the trigger condition requires a specific combination of skip_rows configuration with malformed preamble content that causes multi-line consumption. The fix is worthwhile (use raw file iteration for skip, then switch to csv.reader for structured data), but this is not a common deployment scenario.

### Bug 3: UnicodeDecodeError from CSV file reads is unhandled (P2 confirmed)

Genuine P2. The CSV source opens files with `open(self._path, encoding=self._encoding, newline="")` at line 134. If the file contains bytes invalid for the specified encoding, `UnicodeDecodeError` is raised during iteration. This is not caught anywhere in `load()` -- existing handlers cover `csv.Error` and `StopIteration` but not encoding errors.

The JSON source handles this explicitly (lines 226-238 in json_source.py). The CSV source should have equivalent handling. This is a Tier 3 boundary gap: external CSV files with encoding mismatches should be quarantined, not crash the pipeline.

P2 is appropriate because: while the crash is real, it occurs on the first attempt to read the file and provides a clear error message. The pipeline does not partially process data before crashing. The user can correct the encoding setting or fix the file. The missing behavior is quarantine routing, not data loss.

### Bug 4: skip_rows accepts negative values without validation (P3 confirmed)

Genuine P3. `skip_rows: int = 0` at `csv_source.py:37` has no constraint. `range(negative)` produces an empty iterator, so negative values silently behave like 0. The fix is trivial: `Field(default=0, ge=0)`.

P3 is appropriate because: negative skip_rows is a configuration error that results in no rows being skipped (same as default), not data corruption or loss. The user would notice immediately if they intended to skip rows and none were skipped. Adding the constraint improves config validation hygiene.

## Cross-Cutting Observations

### 1. Encoding error handling asymmetry between JSON and CSV sources

Bugs 1 and 3 both expose the same pattern: the JSON source has comprehensive encoding error handling (surrogateescape, UnicodeDecodeError catch, quarantine routing) that was not replicated in the CSV source or in the JSON array mode path. A systematic review should ensure all source plugins handle encoding failures uniformly at the Tier 3 boundary.

### 2. skip_rows implementation assumes well-formed preamble

Bug 2 reveals that `skip_rows` was designed for simple header skipping (version lines, comments) but interacts badly with the csv.reader's multi-line quoted field semantics. A more robust approach would read raw lines for the skip phase (bypassing csv parsing entirely) and then create the csv.reader on the remaining file content.
