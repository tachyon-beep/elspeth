## Summary

`get_run_contract()` and `explain_field()` silently drop the `FieldContract.nullable` flag, so MCP reports misstate valid schema contracts by presenting nullable fields as if `None` were invalid.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/mcp/analyzers/contracts.py
- Line(s): 46-53, 108-116
- Function/Method: `get_run_contract`; `explain_field`

## Evidence

The target file serializes contract fields without the `nullable` attribute in both contract-reporting paths:

```python
fields = [
    {
        "normalized_name": f.normalized_name,
        "original_name": f.original_name,
        "python_type": f.python_type.__name__,
        "required": f.required,
        "source": f.source,
    }
    for f in contract.fields
]
```

`/home/john/elspeth/src/elspeth/mcp/analyzers/contracts.py:46-55`

```python
return {
    "run_id": run_id,
    "normalized_name": field_contract.normalized_name,
    "original_name": field_contract.original_name,
    "python_type": field_contract.python_type.__name__,
    "required": field_contract.required,
    "source": field_contract.source,
    "contract_mode": contract.mode,
}
```

`/home/john/elspeth/src/elspeth/mcp/analyzers/contracts.py:108-116`

But `nullable` is a first-class part of the contract model and changes validation behavior:

```python
@dataclass(frozen=True, slots=True)
class FieldContract:
    ...
    nullable: bool = False
```

`/home/john/elspeth/src/elspeth/contracts/schema_contract.py:32-53`

```python
if value is None and (not fc.required or fc.nullable):
    continue
```

`/home/john/elspeth/src/elspeth/contracts/schema_contract.py:264-269`

The contract hash also includes `nullable`, so ELSPETH treats it as audit-significant schema state, not display-only metadata:

```python
{
    "n": fc.normalized_name,
    "o": fc.original_name,
    "t": fc.python_type.__name__,
    "r": fc.required,
    "s": fc.source,
    "nullable": fc.nullable,
}
```

`/home/john/elspeth/src/elspeth/contracts/schema_contract.py:320-338`

There are explicit tests proving nullable semantics matter for valid contracts:

```python
assert field_map["score"].required is True
assert field_map["score"].nullable is True

violations = validate_output_against_contract({"score": None}, contract)
assert violations == []
```

`/home/john/elspeth/tests/unit/contracts/test_transform_contract.py:242-257`

The MCP return types likewise have no place to carry this field:

```python
class ContractField(TypedDict):
    normalized_name: str
    original_name: str
    python_type: str
    required: bool
    source: str
```

`/home/john/elspeth/src/elspeth/mcp/types.py:480-487`

So for a valid contract like `score: float | None`, MCP currently reports only `python_type="float", required=True`, which tells the caller the wrong thing about whether `None` is allowed.

## Root Cause Hypothesis

The MCP analyzer was written against an older contract shape and never updated when `FieldContract.nullable` became part of the runtime and audit contract. Because the target file hand-assembles response dicts instead of serializing from a shared contract-report DTO, the new field was omitted in both report paths.

## Suggested Fix

Include `nullable` in both serialized outputs from this file, and update the MCP TypedDicts/tests to match.

Helpful shape:

```python
{
    "normalized_name": f.normalized_name,
    "original_name": f.original_name,
    "python_type": f.python_type.__name__,
    "required": f.required,
    "source": f.source,
    "nullable": f.nullable,
}
```

and:

```python
{
    ...
    "source": field_contract.source,
    "nullable": field_contract.nullable,
    "contract_mode": contract.mode,
}
```

Also add regression tests in `tests/unit/mcp/analyzers/test_contracts.py` covering a required-nullable field so `get_run_contract()` and `explain_field()` prove that `nullable=True` survives to MCP responses.

## Impact

MCP’s schema-contract tools can give materially wrong answers for valid runs that use nullable fields. Operators and downstream tools may misdiagnose contract violations, incorrectly conclude that `None` values are illegal, and lose fidelity when explaining why a row did or did not violate a contract. This weakens the audit/explainability surface even though the underlying Landscape record is correct.
