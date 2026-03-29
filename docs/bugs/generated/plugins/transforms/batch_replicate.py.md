## Summary

`BatchReplicate.process()` rebuilds a brand-new `SchemaContract` for replicated rows and throws away the upstream contract’s mode, original header names, and field types.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/transforms/batch_replicate.py`
- Line(s): 202-218
- Function/Method: `BatchReplicate.process`

## Evidence

`batch_replicate.py` synthesizes its multi-row output contract from raw keys only:

```python
fields = tuple(
    FieldContract(
        normalized_name=key,
        original_name=key,
        python_type=object,
        required=False,
        source="inferred",
    )
    for key in all_keys
)
output_contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/batch_replicate.py:208`

That does three destructive things for every replicated child token:

1. It hard-downgrades the contract mode to `OBSERVED`, even if the input rows were `FIXED` or `FLEXIBLE`.
2. It replaces every `original_name` with the normalized key.
3. It replaces every field type with `object`.

Other transforms preserve contract metadata instead of rebuilding it from scratch. For example:

```python
output_contract = narrow_contract_to_output(
    input_contract=row.contract,
    output_row=output,
)
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/web_scrape.py:362`
Source: `/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py:169`

That preservation matters because sink header restoration in `ORIGINAL` mode reads `field.original_name` from the contract:

```python
if mode == HeaderMode.ORIGINAL:
    ...
    result[name] = field.original_name
```

Source: `/home/john/elspeth/src/elspeth/contracts/header_modes.py:100`

And sinks prefer contract-based original-header resolution:

```python
if sink._output_contract is not None:
    return resolve_headers(
        contract=sink._output_contract,
        mode=HeaderMode.ORIGINAL,
        custom_mapping=None,
    )
```

Source: `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:88`

So after `batch_replicate`, an `ORIGINAL`-mode sink will emit normalized names for preserved input columns, because the transform has overwritten the original-name metadata.

The type erasure is also real: `SchemaContract.validate()` skips type checks for `python_type is object`:

```python
if fc.python_type is object:
    continue
```

Source: `/home/john/elspeth/src/elspeth/contracts/schema_contract.py:257`

That conflicts with the project’s Tier 2 rule that pipeline data types remain trustworthy and should not be silently degraded: `/home/john/elspeth/CLAUDE.md:35`

## Root Cause Hypothesis

The transform fixed a prior “missing contract on `success_multi()`” bug by constructing a union-of-keys contract locally, but it used the simplest possible representation instead of propagating/merging the input contracts. That solved token expansion mechanically while discarding the metadata ELSPETH relies on for header custody and schema fidelity.

## Suggested Fix

Build the output contract by preserving and merging the input row contracts, then add only the truly new field (`copy_index`) as inferred metadata.

A safe shape would be:

1. Merge all valid input contracts with `SchemaContract.merge(...)`.
2. Preserve the merged contract’s mode, `original_name`, and `python_type` for existing fields.
3. Add `copy_index` only when enabled, using an inferred `int` field.
4. Keep the result locked.

Using existing helpers is preferable to rebuilding `FieldContract`s manually. At minimum, the fix should stop forcing:

- `mode="OBSERVED"`
- `original_name=key` for preserved fields
- `python_type=object` for preserved fields

## Impact

Any pipeline that sends `batch_replicate` output to sinks using `headers: original` can emit normalized headers instead of the source headers, breaking the “engine takes custody of original headers” contract.

It also weakens downstream schema guarantees by erasing trusted Tier 2 type information and downgrading contract mode, which can mask incompatibilities that should have remained visible after replication.
