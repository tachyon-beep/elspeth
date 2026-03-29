## Summary

`JSONSource` skips mandatory source-boundary field normalization, so JSON keys remain raw instead of becoming canonical normalized names; this breaks downstream `PipelineRow` access/contracts and causes `headers: original` sinks to fail because no field-resolution mapping is ever recorded.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [/home/john/elspeth/src/elspeth/plugins/sources/json_source.py](/home/john/elspeth/src/elspeth/plugins/sources/json_source.py)
- Line(s): 145-159, 378-383
- Function/Method: `JSONSource.__init__`, `JSONSource._validate_and_yield`

## Evidence

`json_source.py` explicitly opts out of normalization:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/json_source.py:145-159
# JSON sources don't need field normalization (no headers to normalize)
...
initial_contract = create_contract_from_config(self._schema_config)
...
self._contract_builder = ContractBuilder(initial_contract)
```

On first valid row it hard-codes an identity mapping instead of original->normalized resolution:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/json_source.py:378-383
if self._contract_builder is not None and not self._first_valid_row_processed:
    field_resolution = {k: k for k in validated_row}
    self._contract_builder.process_first_row(validated_row, field_resolution)
```

That conflicts with the project’s source-boundary contract:

- [/home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py#L167](/home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py#L167) says “Field normalization is mandatory at all source boundaries. Raw headers are always normalized to valid Python identifiers.”
- [/home/john/elspeth/docs/release/feature-inventory.md#L35](/home/john/elspeth/docs/release/feature-inventory.md#L35) lists `JSON Source` special features as including field normalization.

Downstream code assumes normalized names are canonical:

```python
# /home/john/elspeth/src/elspeth/contracts/schema_contract.py:563-603
def __getitem__(self, key: str) -> Any:
    normalized = self._contract.resolve_name(key)
    return self._data[normalized]

def __getattr__(self, key: str) -> Any:
    return self[key]
```

The integration expectation is visible in tests for source contracts:

```python
# /home/john/elspeth/tests/integration/plugins/sources/test_contract.py:137-148
assert pipeline_row["amount_usd"] == "100"
assert pipeline_row.amount_usd == "100"
assert pipeline_row["Amount USD"] == "100"
```

`JSONSource` also never overrides `get_field_resolution()`, so sinks using `headers: original` will fail when they ask Landscape for the source mapping:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:185-190
resolution_mapping = ctx.landscape.get_source_field_resolution(ctx.run_id)
if resolution_mapping is None:
    raise ValueError(
        "headers: original but source did not record field resolution. "
    )
```

That failure mode is already enforced by sink tests:

- [/home/john/elspeth/tests/unit/plugins/sinks/test_sink_display_headers.py#L149](/home/john/elspeth/tests/unit/plugins/sinks/test_sink_display_headers.py#L149)
- [/home/john/elspeth/tests/unit/plugins/sinks/test_sink_display_headers.py#L298](/home/john/elspeth/tests/unit/plugins/sinks/test_sink_display_headers.py#L298)

What the code does now:
- Keeps JSON keys exactly as provided.
- Builds contracts with `original_name == normalized_name`.
- Records no field-resolution metadata.

What it should do:
- Normalize JSON object keys at the Tier-3 source boundary.
- Preserve original keys in field-resolution metadata and contract `original_name`.
- Return that mapping from `get_field_resolution()` so `headers: original` sinks can restore source names.

## Root Cause Hypothesis

`JSONSource` assumes “JSON keys are not headers,” so it treats them as already-safe canonical field names. That assumption contradicts ELSPETH’s broader source-boundary rule: any external field names must be normalized once before entering Tier 2. Because of that mistaken assumption, the plugin never computes or stores original->normalized name resolution.

## Suggested Fix

Normalize JSON object keys in `json_source.py` before schema validation, using the same normalization utilities/pattern as other sources.

At minimum:

```python
# sketch
from elspeth.plugins.sources.field_normalization import resolve_field_names

raw_keys = list(row.keys())
resolution = resolve_field_names(raw_headers=raw_keys, field_mapping=None, columns=None)
normalized_row = {resolution.resolution_mapping[k]: v for k, v in row.items()}
```

Then:
- validate `normalized_row`, not the raw row
- feed the real `resolution_mapping` into `ContractBuilder.process_first_row(...)`
- store the mapping/version on the source instance
- override `get_field_resolution()` to return it
- add tests for JSON/JSONL rows with keys like `"Customer ID"` and `"Amount (USD)"`, asserting:
  - `pipeline_row.customer_id` works
  - `pipeline_row["Customer ID"]` still works
  - `headers: original` JSON sink round-trips the original names

## Impact

Pipelines sourcing JSON with non-identifier keys can silently enter Tier 2 with non-canonical field names, which breaks ELSPETH’s source contract. Concrete fallout:

- transforms/templates expecting normalized access such as `row.customer_id` or normalized `required_input_fields` can fail
- contract metadata loses true original-name provenance
- sinks configured with `headers: original` fail because the source recorded no field-resolution mapping
- audit/recovery of original field names is incomplete even when the pipeline otherwise succeeds
