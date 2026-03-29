## Summary

`OutputValidationResult` is declared as a frozen value object, but direct construction accepts mutable `list` values for its field collections, so validation evidence can be mutated after creation.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/sink.py`
- Line(s): 29-40
- Function/Method: `OutputValidationResult.__post_init__`

## Evidence

`OutputValidationResult` stores collection fields that are intended to be immutable evidence:

- `target_fields`, `schema_fields`, `missing_fields`, and `extra_fields` are annotated as `tuple[str, ...]` in [`/home/john/elspeth/src/elspeth/contracts/sink.py`](file:///home/john/elspeth/src/elspeth/contracts/sink.py), lines 29-35.
- Its `__post_init__` only checks `valid=False` requires an `error_message`; it does not freeze or normalize container inputs, lines 37-40.

This violates the project’s frozen-dataclass pattern used elsewhere:

- [`/home/john/elspeth/src/elspeth/contracts/freeze.py`](file:///home/john/elspeth/src/elspeth/contracts/freeze.py), lines 80-102 defines `freeze_fields()` as the standard guard for frozen dataclasses with container fields.
- [`/home/john/elspeth/src/elspeth/contracts/audit.py`](file:///home/john/elspeth/src/elspeth/contracts/audit.py), lines 95-102 shows a comparable contract dataclass calling `freeze_fields(self, "schema_fields")`.

Observed reproduction in this repo:

```python
from elspeth.contracts.sink import OutputValidationResult
r = OutputValidationResult(valid=True, target_fields=['id'])
print(type(r.target_fields).__name__, r.target_fields)
r.target_fields.append('name')
print(type(r.target_fields).__name__, r.target_fields)
```

Result:

```python
list ['id']
list ['id', 'name']
```

What the code does:
- Allows mutable lists inside a `frozen=True` dataclass.

What it should do:
- Normalize or deep-freeze those fields so a validation result cannot be changed after creation.

## Root Cause Hypothesis

The class relies on its `success()`/`failure()` factories to convert lists to tuples, but the public dataclass constructor remains available and `__post_init__` does not enforce the same immutability guarantees. That leaves the contract object inconsistent with the repository’s deep-freeze rule for frozen dataclasses.

## Suggested Fix

Freeze or normalize the collection fields inside `__post_init__`, not only in the factories. For example:

```python
from elspeth.contracts.freeze import freeze_fields

def __post_init__(self) -> None:
    freeze_fields(self, "target_fields", "schema_fields", "missing_fields", "extra_fields")
    if not self.valid and not self.error_message:
        raise ValueError("OutputValidationResult with valid=False must have error_message")
```

It would also help to widen factory parameters from `list[str] | None` to `Sequence[str] | None`, since the stored representation is tuple-like anyway.

## Impact

The object is supposed to be immutable validation evidence for resume/append safety checks. In its current form, callers can mutate the reported schema mismatch details after creation, which undermines the reliability of diagnostics and any later logic that trusts this result object as a stable value.
---
## Summary

`OutputValidationResult` permits contradictory “successful but mismatched” states, and the CLI resume path trusts only `valid`, so schema-mismatch diagnostics can be silently ignored if a sink returns an inconsistent result object.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/sink.py`
- Line(s): 37-40
- Function/Method: `OutputValidationResult.__post_init__`

## Evidence

The contract only enforces one half of its invariant:

- [`/home/john/elspeth/src/elspeth/contracts/sink.py`](file:///home/john/elspeth/src/elspeth/contracts/sink.py), lines 37-40 rejects `valid=False` without an `error_message`.
- It does not reject `valid=True` with `error_message`, `missing_fields`, `extra_fields`, or `order_mismatch=True`.

Observed reproduction:

```python
from elspeth.contracts.sink import OutputValidationResult
r = OutputValidationResult(valid=True, error_message='schema mismatch', missing_fields=('id',))
print(r.valid, r.error_message, r.missing_fields)
```

Result:

```python
True schema mismatch ('id',)
```

That inconsistent state is dangerous because the resume gate checks only `valid`:

- [`/home/john/elspeth/src/elspeth/cli.py`](file:///home/john/elspeth/src/elspeth/cli.py), lines 1856-1867:
  - `validation = sink.validate_output_target()`
  - `if not validation.valid:` then print `error_message`, `missing_fields`, `extra_fields`, `order_mismatch`
- If `valid` is `True`, the CLI proceeds and ignores all diagnostic fields.

The protocol explicitly makes this object the sink-validation contract:

- [`/home/john/elspeth/src/elspeth/contracts/plugin_protocols.py`](file:///home/john/elspeth/src/elspeth/contracts/plugin_protocols.py), lines 530-540 defines `validate_output_target()` as returning `OutputValidationResult` to represent compatibility.

What the code does:
- Accepts internally contradictory validation results.

What it should do:
- Enforce that success states contain no mismatch diagnostics and failure states contain the required failure metadata.

## Root Cause Hypothesis

`OutputValidationResult` was given a minimal invariant around `error_message` for failures, but the class was not treated as a full state machine. As a result, impossible mixed states are accepted even though downstream code uses `valid` as the single source of truth.

## Suggested Fix

Strengthen `__post_init__` to enforce mutually exclusive success/failure states. For example:

```python
def __post_init__(self) -> None:
    freeze_fields(self, "target_fields", "schema_fields", "missing_fields", "extra_fields")

    if self.valid:
        if self.error_message is not None:
            raise ValueError("valid=True must not have error_message")
        if self.missing_fields or self.extra_fields or self.order_mismatch:
            raise ValueError("valid=True must not carry mismatch diagnostics")
    else:
        if not self.error_message:
            raise ValueError("valid=False must have error_message")
```

Add unit tests for contradictory-success cases.

## Impact

This is a contract bug at the resume safety boundary. A sink implementation that accidentally returns `valid=True` while also reporting mismatch diagnostics would bypass the CLI’s schema-compatibility stop condition and allow resume/append to continue against an incompatible target. That risks appending rows into the wrong shape while suppressing the only warning the validation object contains.
