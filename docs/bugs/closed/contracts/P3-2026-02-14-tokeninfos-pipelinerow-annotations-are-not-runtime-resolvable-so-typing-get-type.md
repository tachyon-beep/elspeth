## Summary

`TokenInfo`’s `PipelineRow` annotations are not runtime-resolvable, so `typing.get_type_hints()` crashes with `NameError` for both the class and `with_updated_data()`.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — nothing in production calls get_type_hints(TokenInfo); only affects introspection tooling)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/contracts/identity.py
- Line(s): 9-12, 32, 38
- Function/Method: `TokenInfo` (class annotations), `TokenInfo.with_updated_data`

## Evidence

`identity.py` only imports `PipelineRow` under `TYPE_CHECKING`:

```python
# /home/john/elspeth-rapid/src/elspeth/contracts/identity.py:9-12
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import PipelineRow
```

But `PipelineRow` is used in runtime annotations:

```python
# /home/john/elspeth-rapid/src/elspeth/contracts/identity.py:32,38
row_data: PipelineRow
def with_updated_data(self, new_data: PipelineRow) -> TokenInfo:
```

Repro (in this repo):

- `get_type_hints(TokenInfo)` -> `NameError: name 'PipelineRow' is not defined`
- `get_type_hints(TokenInfo.with_updated_data)` -> `NameError: name 'PipelineRow' is not defined`

This conflicts with established contract-testing practice that resolves annotations via `get_type_hints` (example: `/home/john/elspeth-rapid/tests/unit/contracts/test_field_contract.py:224-235`, `/home/john/elspeth-rapid/tests/unit/cli/test_execution_result.py:60-63`).

What it does now: leaves `PipelineRow` undefined in module globals at runtime.
What it should do: keep annotations resolvable for runtime introspection.

## Root Cause Hypothesis

`PipelineRow` was moved behind a `TYPE_CHECKING` guard (likely to reduce import coupling), but with postponed annotations (`from __future__ import annotations`), runtime hint resolution still needs the symbol present in module globals. Since it is absent, hint evaluation fails.

## Suggested Fix

In `identity.py`, make `PipelineRow` available at runtime (unconditional import), e.g.:

```python
from elspeth.contracts.schema_contract import PipelineRow
```

and remove the `TYPE_CHECKING`-gated import for this symbol.

This keeps annotations introspectable and aligns with existing `get_type_hints` contract checks.

## Impact

- Runtime reflection/introspection on `TokenInfo` type contracts fails immediately.
- Any future CI checks, schema tooling, or plugin/contract validators that call `get_type_hints(TokenInfo)` will break.
- This is a contract-surface fragility in a core identity type used widely across engine/executor paths.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/identity.py.md`
- Finding index in source report: 1
- Beads: pending
