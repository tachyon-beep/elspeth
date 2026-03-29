## Summary

A single malformed CSV record causes `AzureBlobSource` to quarantine the entire blob and stop, so valid rows after the bad record disappear instead of being processed or individually quarantined.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py
- Line(s): 533-575, 615-618
- Function/Method: `_load_csv`

## Evidence

`AzureBlobSource._load_csv()` parses the whole blob with one `pd.read_csv(...)` call:

```python
df = pd.read_csv(
    io.StringIO(text_data),
    delimiter=delimiter,
    header=header_arg,
    names=names_arg,
    dtype=str,
    keep_default_na=False,
    on_bad_lines="error",
)
```

If any structural CSV error occurs, the code catches `ParserError`/`EmptyDataError`, records one blob-level validation error, yields at most one quarantined `SourceRow`, and returns immediately. See [/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L533](/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L533) and [/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L556](/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L556).

That behavior is materially weaker than the local-file CSV source, which reads record-by-record and quarantines malformed rows while continuing with later rows. See [/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L343](/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L343) through [/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L377](/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L377), and [/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L389](/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L389) through [/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L412](/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L412).

The orchestrator expects each quarantined row to be routed and recorded individually, not collapsed into one synthetic blob-level failure. See [/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1764](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1764) through [/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1864](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1864).

I also verified the parser behavior locally with the same `pd.read_csv` settings used at line 547: an input like `id,name\n1,alice\n2,"bob\n3,carol\n` raises `ParserError: EOF inside string starting at row 2`. In this implementation, that means row 1 is lost along with row 3 because `_load_csv()` returns after yielding only one blob-level quarantine.

## Root Cause Hypothesis

The Azure blob CSV path was implemented as a whole-file pandas parse, while the canonical CSV source uses a streaming `csv.reader` path that can preserve row boundaries and continue after row-level failures. In this file, `on_bad_lines="error"` plus a top-level `ParserError` handler turns a single bad record into a terminal file-level failure.

## Suggested Fix

Replace the whole-file pandas parse in `_load_csv()` with record-by-record parsing equivalent to `CSVSource._load_from_file()`, operating over an in-memory text stream. The fix should preserve:

```python
reader = csv.reader(io.StringIO(text_data, newline=""), delimiter=delimiter)
```

Then:
- read the header explicitly before normalization
- validate field counts per row
- quarantine malformed rows with line metadata
- continue processing later rows when the parser state is still usable
- reserve file-level quarantine for truly unrecoverable cases only

Reusing the `csv_source.py` logic directly would be safer than keeping two divergent CSV implementations.

## Impact

Valid rows after a malformed CSV record are silently dropped from the run. The audit trail records only one blob-level quarantine instead of the actual per-row outcomes, so operators cannot prove what happened to the unaffected rows. This violates the source-boundary rule in `CLAUDE.md` that bad external rows should be quarantined while other rows continue.
---
## Summary

The CSV header normalization path does not preserve the actual external headers because pandas rewrites duplicate headers before `resolve_field_names()` sees them, so the audit trail can record fabricated original names like `User ID.1`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py
- Line(s): 547-555, 577-586, 602-605, 843-850
- Function/Method: `_load_csv`, `get_field_resolution`

## Evidence

In the CSV path, the code obtains `raw_headers` from `df.columns` after pandas has already parsed the file:

```python
df = pd.read_csv(...)
raw_headers = [str(header) for header in df.columns]
self._field_resolution = resolve_field_names(raw_headers=raw_headers, ...)
```

See [/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L547](/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L547) through [/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L586](/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py#L586).

`resolve_field_names()` assumes `raw_headers` are the true external names and stores them verbatim into the audit resolution mapping. See [/home/john/elspeth/src/elspeth/plugins/sources/field_normalization.py#L229](/home/john/elspeth/src/elspeth/plugins/sources/field_normalization.py#L229) through [/home/john/elspeth/src/elspeth/plugins/sources/field_normalization.py#L263](/home/john/elspeth/src/elspeth/plugins/sources/field_normalization.py#L263).

That mapping is then used to build `SchemaContract.original_name` values and later to restore ORIGINAL headers in sinks. See [/home/john/elspeth/src/elspeth/contracts/schema_contract_factory.py#L75](/home/john/elspeth/src/elspeth/contracts/schema_contract_factory.py#L75) through [/home/john/elspeth/src/elspeth/contracts/schema_contract_factory.py#L92](/home/john/elspeth/src/elspeth/contracts/schema_contract_factory.py#L92), and [/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py#L185](/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py#L185) through [/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py#L200](/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py#L200).

I verified locally that the exact `pd.read_csv` pattern used here rewrites duplicate headers before this code runs:

```python
text = "User ID,User ID,Amount $\n1,2,100\n"
df = pd.read_csv(io.StringIO(text), delimiter=",", header=0, dtype=str, keep_default_na=False, on_bad_lines="error")
list(df.columns) == ["User ID", "User ID.1", "Amount $"]
```

So `get_field_resolution()` will expose `User ID.1` as if it came from Azure, even though the external blob actually contained `User ID` twice. That breaks header custody and can also bypass collision detection, because normalization now runs on the fabricated pandas names instead of the real source headers.

## Root Cause Hypothesis

The implementation relies on pandas for initial header parsing, but ELSPETH’s field-resolution contract requires custody of the literal external header names. Pandas mutates duplicate headers during parse, and this file treats those mutated names as authoritative.

## Suggested Fix

Capture the raw CSV header row before pandas mutates it, or stop using pandas for the CSV path. The fix should ensure that:
- `resolve_field_names()` receives the literal header row from the blob
- duplicate original headers trigger the intended normalization/collision checks
- `resolution_mapping` and `SchemaContract.original_name` reflect what Azure actually provided

A shared parser path with `csv_source.py` would fix this as well.

## Impact

Audit metadata can claim the source provided headers that never existed, such as `User ID.1`. ORIGINAL-header sinks may emit fabricated column names, and lineage/explanations can no longer prove the exact external schema that entered the run. This is an audit-integrity failure in a source plugin, even when the row payloads themselves still parse.
