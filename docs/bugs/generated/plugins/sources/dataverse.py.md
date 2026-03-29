## Summary

Dataverse source locks an inferred schema contract on the first valid row but never validates later rows against that locked contract, so type drift passes through as valid pipeline data.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [src/elspeth/plugins/sources/dataverse.py](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py)
- Line(s): 650-684
- Function/Method: `load`

## Evidence

[dataverse.py](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L650) validates each row with `self._schema_class.model_validate(normalized_row)`, then on the first valid row calls `self._contract_builder.process_first_row(...)` and immediately yields `SourceRow.valid(...)` from [lines 670-684](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L670). There is no follow-up `contract.validate(validated_row)` check after the contract is locked.

By contrast, [json_source.py](/home/john/elspeth/src/elspeth/plugins/sources/json_source.py#L386) and [csv_source.py](/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py#L431) both explicitly validate every subsequent row against the locked contract and quarantine on violations. Their comments explain why: Pydantic with flexible/observed schemas allows extra fields and does not enforce the inferred types for those fields.

That means a Dataverse stream like:

```python
# first valid row locks inferred type
{"amount": 42}

# later row changes the same field's type
{"amount": "not-an-int"}
```

will be emitted as `SourceRow.valid(...)` in Dataverse source, while the other sources would quarantine it after contract validation.

## Root Cause Hypothesis

The Dataverse source copied the first-row infer-and-lock setup but omitted the second half of the pattern used elsewhere in the repo: validating later rows against the locked `SchemaContract`. Because this source uses flexible/observed schema machinery and `allow_coercion=True` at the Tier 3 boundary, relying on Pydantic alone is insufficient once the contract has inferred field types from row 1.

## Suggested Fix

After the first valid row has locked the contract, mirror the JSON/CSV source behavior:

```python
contract = self.get_schema_contract()
if contract is not None and contract.locked:
    violations = contract.validate(validated_row)
    if violations:
        error_msg = "; ".join(str(v) for v in violations)
        ctx.record_validation_error(
            row=validated_row,
            error=error_msg,
            schema_mode=self._schema_config.mode,
            destination=self._on_validation_failure,
        )
        if self._on_validation_failure != "discard":
            yield SourceRow.quarantined(
                row=validated_row,
                error=error_msg,
                destination=self._on_validation_failure,
            )
        continue

yield SourceRow.valid(validated_row, contract=contract)
```

## Impact

Rows that violate the inferred source contract are promoted from Tier 3 to Tier 2 as if they were valid. Downstream transforms then see schema-inconsistent data that should have been quarantined at the source boundary. This breaks the source contract, weakens auditability, and can surface as later transform crashes or silent misprocessing instead of a recorded validation failure.
---
## Summary

If the first processed Dataverse row is invalid, the first valid row can crash contract inference with a `KeyError` when it contains fields absent from that invalid row.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [src/elspeth/plugins/sources/dataverse.py](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py)
- Line(s): 411-433, 648-680
- Function/Method: `_normalize_row_fields`, `load`

## Evidence

[_normalize_row_fields()`](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L411) builds `_field_resolution` only when `is_first_row` is true. For later unseen fields it does an ad hoc `normalize_field_name(k)` at [lines 427-432](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L427), but it does not add that new raw field to `self._field_resolution.resolution_mapping`.

In `load()`, `is_first_row = False` is set at [line 648](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L648) before schema validation succeeds. So this sequence is possible:

1. Row 1 is the first processed row.
2. Row 1 normalizes successfully, seeds `_field_resolution`, then fails schema validation and is quarantined.
3. Row 2 is the first valid row and contains an extra Dataverse field not present in row 1.
4. Row 2 is normalized with the stale mapping plus ad hoc normalization for the new field.
5. `process_first_row(validated_row, resolution_map)` is called with a `resolution_map` that does not contain that new field.

[contract_builder.py](/home/john/elspeth/src/elspeth/contracts/contract_builder.py#L91) explicitly treats that as a source-plugin bug and does `original_name = normalized_to_original[normalized_name]` at [line 94](/home/john/elspeth/src/elspeth/contracts/contract_builder.py#L94), which raises `KeyError`.

This is especially plausible for Dataverse because sparse entities and dynamic attributes mean later rows commonly have fields missing from earlier rows; the source itself documents that at [lines 420-424](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L420).

## Root Cause Hypothesis

The code conflates “first processed row” with “first valid row.” Field resolution is frozen from the first processed row, but contract inference is deferred until the first valid row. When those are different rows, the resolution map can be incomplete for the row used to infer the contract.

## Suggested Fix

Make the field-resolution seed align with the first valid row used for contract inference. Two safe options:

```python
# Option A: only clear is_first_row after a row validates
normalized_row = self._normalize_row_fields(cleaned_row, is_first_row)
...
validated = self._schema_class.model_validate(normalized_row)
validated_row = validated.to_row()
is_first_row = False
```

Or, if late fields before first contract lock must still be preserved, explicitly extend `_field_resolution` with newly seen fields before calling `process_first_row(...)`, including collision checks.

## Impact

A malformed early row can turn a later valid Dataverse row into a hard crash instead of either yielding a valid row or quarantining it. That violates source-boundary robustness for external data, and it can abort the whole load on a dataset that should have been partially recoverable and auditable.
