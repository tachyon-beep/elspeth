# Bug Report: Duplicate Row Wrapper Classes (PipelineRow and ContractAwareRow)

## Summary

- Two nearly identical row wrapper classes exist with ~80% overlapping functionality: `PipelineRow` in `contracts/schema_contract.py` and `ContractAwareRow` in `plugins/llm/contract_aware_row.py`. They have already drifted out of sync on `__contains__` behavior, requiring the same fix to be applied twice.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Claude Opus 4.5
- Date: 2026-02-03
- Related run/issue ID: N/A (discovered during P2 fix for `__contains__` and optional field validation)

## Environment

- Commit/branch: RC2.1
- OS: Linux
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Fix schema contract bugs (optional field None validation, `__contains__` checking contract instead of data)
- Model/version: Claude Opus 4.5
- Tooling and permissions: Full code access
- Determinism details: N/A
- Notable tool calls: During investigation, found that `ContractAwareRow` already had the correct `__contains__` fix with a P2 comment, while `PipelineRow` had the bug

## Steps To Reproduce

1. Compare `PipelineRow` in `src/elspeth/contracts/schema_contract.py:462-580`
2. Compare `ContractAwareRow` in `src/elspeth/plugins/llm/contract_aware_row.py:28-160`
3. Note the significant overlap in methods: `__init__`, `__getitem__`, `__getattr__`, `__contains__`

## Expected Behavior

- Single source of truth for row wrapper behavior
- Changes to row access patterns only need to be made once
- Consistent behavior across all pipeline contexts

## Actual Behavior

- Two classes with overlapping functionality
- `__contains__` behavior drifted (ContractAwareRow was fixed, PipelineRow was not)
- Risk of future drift on other methods

## Evidence

**PipelineRow (schema_contract.py):**
```python
class PipelineRow:
    __slots__ = ("_contract", "_data")

    def __init__(self, data: dict[str, Any], contract: SchemaContract) -> None:
        self._data = types.MappingProxyType(dict(data))  # Immutable
        self._contract = contract

    def __getitem__(self, key: str) -> Any:
        normalized = self._contract.resolve_name(key)
        return self._data[normalized]

    # ... similar methods ...
```

**ContractAwareRow (contract_aware_row.py):**
```python
class ContractAwareRow:
    __slots__ = ("_contract", "_data")

    def __init__(self, data: dict[str, Any], contract: SchemaContract) -> None:
        self._data = data  # Mutable
        self._contract = contract

    def __getitem__(self, key: str) -> Any:
        normalized = self._contract.resolve_name(key)
        return self._data[normalized]

    # ... similar methods ...
```

**Key differences:**
1. `PipelineRow` uses `MappingProxyType` for immutability (audit integrity)
2. `ContractAwareRow` has additional methods: `get()`, `keys()`, `__iter__` (for Jinja2)
3. `ContractAwareRow` had the `__contains__` fix first (P2 comment at line 103-106)

## Impact

- User-facing impact: None directly, but increases maintenance burden
- Data integrity / security impact: Risk of inconsistent behavior if fixes are applied to one class but not the other
- Performance or cost impact: Minimal (slight code bloat)

## Root Cause Hypothesis

- `ContractAwareRow` was created specifically for LLM template rendering, which needed `get()`, `keys()`, and iteration support for Jinja2
- `PipelineRow` was created later for the broader schema contract system with stricter immutability requirements
- The two classes were not consolidated because of the immutability difference

## Proposed Fix

- Code changes (modules/files):
  1. Add missing methods to `PipelineRow`: `get()`, `keys()`, `__iter__`
  2. Deprecate `ContractAwareRow` and update LLM plugins to use `PipelineRow`
  3. Alternatively: Make `ContractAwareRow` a thin wrapper that delegates to `PipelineRow` if mutability is truly needed

- Config or schema changes: None

- Tests to add/update:
  - Add `get()`, `keys()`, `__iter__` tests to `test_pipeline_row.py`
  - Verify LLM template rendering works with `PipelineRow`

- Risks or migration steps:
  - Check all usages of `ContractAwareRow` to ensure `PipelineRow` works as a drop-in
  - The immutability of `PipelineRow` should be fine for Jinja2 (read-only access)

## Architectural Deviations

- Spec or doc reference: docs/plans/2026-02-02-unified-schema-contracts-design.md (if exists)
- Observed divergence: Two implementations of row wrapper instead of one
- Reason: Different contexts (audit integrity vs template rendering) led to separate implementations
- Alignment plan: Consolidate into `PipelineRow` with all required methods

## Acceptance Criteria

- [ ] Single row wrapper class used throughout the codebase
- [ ] All Jinja2 template rendering works with the unified class
- [ ] `ContractAwareRow` is removed or clearly marked as deprecated
- [ ] No duplicate logic to maintain

## Tests

- Suggested tests to run:
  - `pytest tests/contracts/test_pipeline_row.py -v`
  - `pytest tests/plugins/llm/ -v`
- New tests required: Yes - tests for `get()`, `keys()`, `__iter__` on `PipelineRow`

## Notes / Links

- Related issues/PRs: **elspeth-rapid-61se** (bead tracking this work)
- Related design docs: N/A
- The `__contains__` fix applied in this session (2026-02-03) shows the risk of having duplicate classes - the fix had already been applied to `ContractAwareRow` but was missing from `PipelineRow`
