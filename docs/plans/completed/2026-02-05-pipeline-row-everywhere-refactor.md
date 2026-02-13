# Pipeline Row Everywhere Refactor

**Status:** Planning
**Created:** 2026-02-05
**Priority:** P2 - Technical Debt / Type Safety

## Problem Statement

The codebase has type signature confusion around `dict | PipelineRow` unions. Runtime behavior shows PipelineRow is used everywhere in the engine, but type signatures suggest dicts are acceptable. This creates:

1. **False flexibility** - Type signatures allow dicts but they're immediately converted
2. **Responsibility confusion** - Engine wraps dicts instead of plugins owning their output
3. **Redundant code** - Contract fallback logic that's never actually used
4. **isinstance() checks** - Defensive programming that hides the true type flow
5. **Misleading contracts** - TransformResult.contract is redundant if row is PipelineRow

## Core Design Principle

**Plugins should return PipelineRow, not dicts.**

- Plugins construct `PipelineRow(dict, contract)` before returning
- Engine receives PipelineRow and uses it directly
- Dicts appear ONLY at trust boundaries (Landscape, sinks, checkpoints)

## Issues Identified

### Issue 1: TransformResult Accepts dict | PipelineRow

**Location:** `contracts/results.py:118, 121`

```python
# Current
row: dict[str, Any] | PipelineRow | None
rows: list[dict[str, Any] | PipelineRow] | None = None
```

**Problem:** Type signature suggests dicts are valid, but engine expects PipelineRow.

**Impact:** Misleading type hints, enables incorrect plugin implementations.

### Issue 2: TransformResult.contract Is Redundant

**Location:** `contracts/results.py:140`

```python
# Current
contract: SchemaContract | None = field(default=None, repr=False)
```

**Problem:** If `row` is PipelineRow, contract is already inside it (`row.contract`). The separate `contract` field is redundant.

**Impact:** Two sources of truth for schema, potential for mismatch.

### Issue 3: Transform Factory Methods Accept Dicts

**Location:** `contracts/results.py:202-209, 242-249`

```python
# Current
@classmethod
def success(cls, row: dict[str, Any] | PipelineRow, *, success_reason: ..., contract: SchemaContract | None = None):
    ...

@classmethod
def success_multi(cls, rows: list[dict[str, Any] | PipelineRow], *, success_reason: ..., contract: SchemaContract | None = None):
    ...
```

**Problem:** Accepts dicts with optional contract, enabling incomplete returns.

**Impact:** Plugins can return dicts without contracts, forcing engine fallback.

### Issue 4: TransformExecutor Has Dead Contract Fallback

**Location:** `engine/executors.py:436-443`

```python
# Current - never actually used
if result.contract is not None:
    output_contract = result.contract
else:
    # Create contract from transform's output_schema
    output_contract = create_output_contract_from_schema(transform.output_schema)
```

**Problem:** All transforms provide contracts already. This fallback is dead code.

**Verification:** Grepped all transforms - 100% provide `contract=` parameter.

**Impact:** Maintenance burden, suggests transforms can skip contracts.

### Issue 5: TransformExecutor Wraps Dicts in PipelineRow

**Location:** `engine/executors.py:446-447`

```python
# Current - engine does the wrapping
row_dict = result.row.to_dict() if isinstance(result.row, PipelineRow) else result.row
new_row = PipelineRow(row_dict, output_contract)
```

**Problem:** Wrapping should happen in plugins, not engine. Engine responsibility is routing, not construction.

**Impact:** Blurs boundary between plugin and engine responsibilities.

### Issue 6: isinstance() Check on TransformResult.row

**Location:** `engine/executors.py:446`

```python
# Current - defensive programming
row_dict = result.row.to_dict() if isinstance(result.row, PipelineRow) else result.row
```

**Problem:** Per CLAUDE.md, defensive programming hides bugs. If row is wrong type, that's a plugin bug.

**Impact:** Masks plugin contract violations instead of crashing immediately.

### Issue 7: RowResult.final_data Accepts dict | PipelineRow

**Location:** `contracts/results.py:376`

```python
# Current
final_data: dict[str, Any] | PipelineRow
```

**Problem:** Runtime always uses PipelineRow (token.row_data is PipelineRow).

**Verification:** Only one usage converts to dict before creating RowResult (processor.py:1010), rest use PipelineRow.

**Impact:** Type signature doesn't match runtime reality.

### Issue 8: Unnecessary to_dict() When Creating RowResult

**Location:** `engine/processor.py:1010`

```python
# Current
final_data=enriched_data.to_dict()
```

**Problem:** Extracts dict for no reason - RowResult should accept PipelineRow directly.

**Impact:** Extra conversion, inconsistent with other RowResult creation sites.

### Issue 9: Multi-Row isinstance() Check

**Location:** `engine/processor.py:1837-1839`

```python
# Current
expanded_rows = [
    dict(r._data) if isinstance(r, PipelineRow) else r
    for r in transform_result.rows
]
```

**Problem:** If TransformResult.rows is `list[PipelineRow]`, no isinstance() needed.

**Impact:** Defensive check that should be unnecessary.

### Issue 10: TransformResult Helper Methods Use Contract Field

**Location:** `contracts/results.py:161-199`

```python
# Current
def to_pipeline_row(self) -> PipelineRow:
    if self.contract is None:
        raise ValueError("TransformResult has no contract")
    return PipelineRow(self.row, self.contract)

def to_pipeline_rows(self) -> list[PipelineRow]:
    if self.contract is None:
        raise ValueError("TransformResult has no contract")
    return [PipelineRow(_extract_dict_from_row(row), self.contract) for row in self.rows]
```

**Problem:** These methods exist to wrap dicts in PipelineRow. If transforms return PipelineRow, these become pass-through or unnecessary.

**Impact:** Methods exist only to paper over dict-returning plugins.

## Solution Design

### Phase 1: Type Signature Updates (No Behavior Change)

**Goal:** Make type signatures match runtime reality.

#### 1.1: Update TransformResult Types

```python
# contracts/results.py
@dataclass
class TransformResult:
    status: Literal["success", "error"]
    row: PipelineRow | None  # Remove: dict[str, Any] |
    reason: TransformErrorReason | None
    retryable: bool = False
    rows: list[PipelineRow] | None = None  # Remove: dict[str, Any] |
    success_reason: TransformSuccessReason | None = None

    # Audit fields - set by executor, not by plugin
    input_hash: str | None = field(default=None, repr=False)
    output_hash: str | None = field(default=None, repr=False)
    duration_ms: float | None = field(default=None, repr=False)
    context_after: dict[str, Any] | None = field(default=None, repr=False)

    # DELETE: contract field (redundant - contract is in PipelineRow)
```

**Changes:**
- `row: PipelineRow | None` (remove dict union)
- `rows: list[PipelineRow] | None` (remove dict union)
- Delete `contract` field entirely

**Rationale:** If row/rows are PipelineRow, contract is inside them. Separate contract field creates two sources of truth.

#### 1.2: Update TransformResult Factory Methods

```python
# contracts/results.py
@classmethod
def success(
    cls,
    row: PipelineRow,  # Not dict!
    *,
    success_reason: TransformSuccessReason,
    context_after: dict[str, Any] | None = None,
) -> TransformResult:
    """Create successful result with single output row.

    Args:
        row: The transformed row as PipelineRow (plugin must wrap dict)
        success_reason: REQUIRED metadata about what the transform did
        context_after: Optional operational metadata for audit trail

    Returns:
        TransformResult with status="success" and the provided row

    Example:
        output = row.to_dict()
        output['new_field'] = value
        output_contract = narrow_contract_to_output(row.contract, output)

        return TransformResult.success(
            PipelineRow(output, output_contract),  # Plugin wraps dict
            success_reason={"action": "enriched", "fields_added": ["new_field"]}
        )
    """
    return cls(
        status="success",
        row=row,
        reason=None,
        rows=None,
        success_reason=success_reason,
        context_after=context_after,
    )

@classmethod
def success_multi(
    cls,
    rows: list[PipelineRow],  # Not dicts!
    *,
    success_reason: TransformSuccessReason,
    context_after: dict[str, Any] | None = None,
) -> TransformResult:
    """Create successful result with multiple output rows.

    Args:
        rows: List of output rows as PipelineRows (must not be empty)
        success_reason: REQUIRED metadata about what the transform did
        context_after: Optional operational metadata for audit trail

    Returns:
        TransformResult with status="success", row=None, rows=rows

    Raises:
        ValueError: If rows is empty

    Example:
        output_rows = [
            PipelineRow({"id": i, "value": v}, output_contract)
            for i, v in enumerate(values)
        ]

        return TransformResult.success_multi(
            output_rows,
            success_reason={"action": "split", "count": len(output_rows)}
        )
    """
    if not rows:
        raise ValueError("success_multi requires at least one row")
    return cls(
        status="success",
        row=None,
        reason=None,
        rows=rows,
        success_reason=success_reason,
        context_after=context_after,
    )
```

**Changes:**
- Remove `contract` parameter (redundant)
- Change `row` to `PipelineRow` (not union)
- Change `rows` to `list[PipelineRow]` (not union)
- Update docstrings with explicit PipelineRow wrapping examples

#### 1.3: Delete TransformResult Helper Methods

```python
# contracts/results.py - DELETE THESE

def to_pipeline_row(self) -> PipelineRow:
    # DELETE - row is already PipelineRow

def to_pipeline_rows(self) -> list[PipelineRow]:
    # DELETE - rows is already list[PipelineRow]
```

**Rationale:** If `row`/`rows` are already PipelineRow, these methods are pass-through or identity operations.

**Usage check required:** Verify no engine code calls these methods.

#### 1.4: Update RowResult Type

```python
# contracts/results.py
@dataclass
class RowResult:
    token: TokenInfo
    final_data: PipelineRow  # Remove: dict[str, Any] |
    outcome: RowOutcome
    sink_name: str | None = None
    error: FailureInfo | None = None
```

**Changes:**
- `final_data: PipelineRow` (remove dict union)

**Rationale:** `TokenInfo.row_data` is PipelineRow, so `final_data` should match.

### Phase 2: Update Transform Implementations

**Goal:** Make transforms wrap dicts in PipelineRow before returning.

**Pattern:**

```python
# Before
output = row.to_dict()
# ... modify output ...
output_contract = narrow_contract_to_output(row.contract, output)
return TransformResult.success(
    output,  # dict
    success_reason={...},
    contract=output_contract,
)

# After
output = row.to_dict()
# ... modify output ...
output_contract = narrow_contract_to_output(row.contract, output)
return TransformResult.success(
    PipelineRow(output, output_contract),  # Plugin wraps
    success_reason={...},
)
```

**Transforms to update (10 files):**

1. `plugins/transforms/field_mapper.py`
2. `plugins/transforms/json_explode.py`
3. `plugins/transforms/truncate.py`
4. `plugins/transforms/passthrough.py`
5. `plugins/transforms/web_scrape.py`
6. `plugins/transforms/keyword_filter.py`
7. `plugins/transforms/batch_replicate.py` (multi-row)
8. `plugins/transforms/batch_stats.py` (multi-row)
9. `plugins/transforms/azure/content_safety.py`
10. `plugins/transforms/azure/prompt_shield.py`

**Special cases:**

- **LLM transforms:** Check azure_multi_query_llm.py and similar
- **Multi-row transforms:** Use `success_multi(list[PipelineRow])`
- **Passthrough transforms:** Return `PipelineRow(row.to_dict(), row.contract)` (copy)

**Testing strategy:** Update one transform, run its tests, verify no regressions.

### Phase 3: Simplify TransformExecutor

**Goal:** Remove dict wrapping and contract fallback logic.

#### 3.1: Remove Contract Fallback (Dead Code)

```python
# engine/executors.py:436-443 - DELETE THIS BLOCK

if result.contract is not None:
    output_contract = result.contract
else:
    # Create contract from transform's output_schema
    from elspeth.contracts.transform_contract import create_output_contract_from_schema
    output_contract = create_output_contract_from_schema(transform.output_schema)
```

**Justification:** All transforms provide contracts. This code is never executed.

**Verification:** Add assertion before deletion, run full test suite, confirm it never fires.

#### 3.2: Simplify PipelineRow Creation

```python
# engine/executors.py:445-457

# Before (current)
row_dict = result.row.to_dict() if isinstance(result.row, PipelineRow) else result.row
new_row = PipelineRow(row_dict, output_contract)
updated_token = token.with_updated_data(new_row)

# After (simplified)
updated_token = token.with_updated_data(result.row)  # Already PipelineRow!
```

**Changes:**
- Delete lines 446-447 (isinstance check + PipelineRow construction)
- Replace with direct token update (line 457)
- Remove `output_contract` variable (unused after contract fallback deleted)

**Testing:** Full test suite must pass - this is pure refactoring.

#### 3.3: Extract Dict Only for Landscape

Keep dict extraction where it's legitimate (trust boundaries):

```python
# engine/executors.py:388-395 - KEEP THIS (Tier 1 boundary)

def _to_dict(r: dict[str, Any] | PipelineRow) -> dict[str, Any]:
    return dict(r._data) if isinstance(r, PipelineRow) else r

if isinstance(output_data_with_pipe, list):
    output_data: dict[str, Any] | list[dict[str, Any]] = [_to_dict(r) for r in output_data_with_pipe]
else:
    output_data = _to_dict(output_data_with_pipe)
```

**Wait - this isinstance() is still needed for Landscape recording?**

**No!** After Phase 2, `result.row` is always PipelineRow, so simplify:

```python
# engine/executors.py:388-395 - SIMPLIFY

if result.row is not None:
    output_data = result.row.to_dict()  # Always PipelineRow
else:
    # Multi-row case
    assert result.rows is not None
    output_data = [r.to_dict() for r in result.rows]  # Always list[PipelineRow]
```

### Phase 4: Simplify RowProcessor

**Goal:** Remove isinstance() checks and unnecessary conversions.

#### 4.1: Remove isinstance() in Multi-Row Handling

```python
# engine/processor.py:1837-1839

# Before
expanded_rows = [
    dict(r._data) if isinstance(r, PipelineRow) else r
    for r in transform_result.rows
]

# After (transform_result.rows is always list[PipelineRow])
expanded_rows = [r.to_dict() for r in transform_result.rows]
```

**Justification:** `TransformResult.rows` is `list[PipelineRow]`, no isinstance() needed.

#### 4.2: Remove to_dict() When Creating RowResult

```python
# engine/processor.py:1010

# Before
final_data=enriched_data.to_dict()

# After
final_data=enriched_data  # Already PipelineRow, RowResult.final_data is PipelineRow
```

**Justification:** `RowResult.final_data` is now `PipelineRow`, matches `enriched_data` type.

#### 4.3: Update Other RowResult Creation Sites

Search for all `RowResult(` calls and verify `final_data` is PipelineRow:

```bash
rg "RowResult\(" src/elspeth/engine/ --type py -C 3
```

Likely locations:
- `processor.py` - multiple sites for different outcomes
- Check each uses `token.row_data` (PipelineRow) or `enriched_data` (PipelineRow)

### Phase 5: Update Type Annotations Ecosystem

**Goal:** Fix downstream type hints that reference old signatures.

#### 5.1: Update _extract_dict_from_row Helper

```python
# contracts/results.py:29-42 - DELETE OR SIMPLIFY

def _extract_dict_from_row(row: dict[str, Any] | PipelineRow) -> dict[str, Any]:
    # DELETE - no longer needed if row is always PipelineRow
    # Or simplify to:
    return row.to_dict()
```

**Usage check:** Used in `to_pipeline_rows()` which we're deleting anyway.

**Action:** Delete this helper entirely.

#### 5.2: Update GateResult (Boundary Case)

```python
# contracts/results.py:327

@dataclass
class GateResult:
    row: dict[str, Any]  # Keep as dict - gates work in dict space
    action: RoutingAction
    contract: SchemaContract | None = field(default=None, repr=False)
    # ... audit fields
```

**NO CHANGE NEEDED.**

**Rationale:** Gates receive PipelineRow, extract dict, evaluate, return dict. The GateExecutor wraps result in PipelineRow. This is a legitimate boundary.

**Verification:** Confirm GateExecutor wraps GateResult.row in PipelineRow before updating token.

#### 5.3: Update SourceRow Type

```python
# contracts/results.py:506-573

@dataclass
class SourceRow:
    row: Any  # Keep as Any - external data can be malformed
    is_quarantined: bool
    quarantine_error: str | None = None
    quarantine_destination: str | None = None
    contract: SchemaContract | None = None

    def to_pipeline_row(self) -> PipelineRow:
        # KEEP - sources return SourceRow, engine converts to PipelineRow
        ...
```

**NO CHANGE NEEDED.**

**Rationale:** Sources deal with external data (Tier 3), may be malformed. SourceRow is the boundary object.

### Phase 6: Verification and Testing

#### 6.1: Type Check with mypy

```bash
.venv/bin/python -m mypy src/elspeth/
```

**Expected:** Zero errors related to TransformResult/RowResult types.

**Fix any:** Type errors that surface from the refactor.

#### 6.2: Run Full Test Suite

```bash
.venv/bin/python -m pytest tests/ -v
```

**Expected:** All tests pass.

**Fix any:** Test failures (should be minimal - this is mostly type refactoring).

#### 6.3: Run Contracts Checker

```bash
.venv/bin/python -m scripts.check_contracts
```

**Expected:** No issues (contracts alignment should be unaffected).

#### 6.4: Manual Smoke Test

Run a real pipeline with multiple transform types:
- Passthrough (field_mapper)
- Schema-changing (json_explode)
- Multi-row (batch_replicate)
- LLM transform (if available)

**Verify:** Pipeline completes, audit trail is correct, no exceptions.

### Phase 7: Documentation Updates

#### 7.1: Update CLAUDE.md

Add section on PipelineRow ownership:

```markdown
## Transform Output: PipelineRow Construction

Transforms must return PipelineRow objects, not dicts:

```python
def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
    output = row.to_dict()  # Work in dict space for flexibility
    output['new_field'] = compute_value()

    # Compute output contract
    output_contract = narrow_contract_to_output(row.contract, output)

    # Plugin wraps dict in PipelineRow before returning
    return TransformResult.success(
        PipelineRow(output, output_contract),
        success_reason={"action": "enriched", "fields_added": ["new_field"]}
    )
\```

**Why plugins wrap dicts:**
- Plugins own their output contracts (responsibility at correct level)
- Engine receives PipelineRow and routes it (no conversion)
- Clear boundary: plugins construct, engine consumes
```

#### 7.2: Update Plugin Development Guide

If `docs/guides/plugin-development.md` exists, update examples to show PipelineRow construction.

#### 7.3: Update Architecture Docs

Update `docs/architecture/pipeline-flow.md` (if exists) to clarify:
- Transforms receive PipelineRow
- Transforms return TransformResult(row=PipelineRow)
- Engine uses PipelineRow directly (no wrapping)
- Dicts extracted only at boundaries (Landscape, sinks, checkpoints)

## Risk Assessment

### Low Risk Changes
- Type signature updates (Phase 1) - compile-time only
- Adding PipelineRow wrapping in transforms (Phase 2) - incremental
- Documentation updates (Phase 7) - non-code

### Medium Risk Changes
- Removing contract fallback (Phase 3.1) - assumes all transforms provide contracts
- Removing isinstance() checks (Phase 3.2, 4.1) - assumes type signatures are correct
- Simplifying TransformExecutor (Phase 3.2) - central execution path

### High Risk Changes
- Deleting TransformResult helper methods (Phase 1.3) - must verify no usage first
- Changing RowResult.final_data type (Phase 1.4) - affects multiple call sites

## Mitigation Strategies

1. **Contract fallback removal:** Add assertion before deletion, run full test suite to confirm it's dead code
2. **Helper method deletion:** Search codebase for `to_pipeline_row()` usage before deleting
3. **Incremental transform updates:** Update one transform per commit, test individually
4. **Type checking:** Run mypy after each phase to catch type errors early
5. **Full test coverage:** Ensure test suite covers all transform types before starting

## Success Criteria

### Completion Checklist

- [ ] No `dict | PipelineRow` unions in engine types
- [ ] All transforms return PipelineRow objects
- [ ] No isinstance() checks in engine code
- [ ] TransformExecutor has no dict wrapping logic
- [ ] All tests pass
- [ ] mypy reports zero type errors
- [ ] Smoke test with real pipeline succeeds
- [ ] Documentation updated

### Performance Impact

**Expected:** Negligible or positive.
- **Removed:** isinstance() checks (minor CPU saving)
- **Removed:** Redundant dict → PipelineRow conversions
- **Added:** PipelineRow construction in plugins (same work, different location)

**Net:** Neutral or slight improvement (fewer operations in hot path).

### Code Quality Impact

**Positive changes:**
- Type signatures match runtime reality
- Clearer responsibility boundaries
- Less defensive programming
- Simpler engine logic
- Explicit contract ownership

**Metrics:**
- **Lines removed:** ~100 (isinstance checks, helper methods, fallback logic)
- **Lines added:** ~50 (PipelineRow wrapping in transforms)
- **Net:** -50 lines, higher clarity

## Implementation Timeline

### Phase-by-Phase Estimate

| Phase | Description | Estimated Effort | Risk |
|-------|-------------|------------------|------|
| 1 | Type signature updates | 2 hours | Low |
| 2 | Transform updates (10 files) | 4 hours | Medium |
| 3 | TransformExecutor simplification | 2 hours | Medium |
| 4 | RowProcessor simplification | 1 hour | Low |
| 5 | Type annotations ecosystem | 1 hour | Low |
| 6 | Verification and testing | 2 hours | Low |
| 7 | Documentation updates | 1 hour | Low |
| **Total** | | **13 hours** | |

### Recommended Approach

**Single PR with incremental commits:**
1. Commit 1: Type signature updates (Phase 1)
2. Commits 2-11: One transform per commit (Phase 2)
3. Commit 12: TransformExecutor simplification (Phase 3)
4. Commit 13: RowProcessor simplification (Phase 4)
5. Commit 14: Type annotations cleanup (Phase 5)
6. Commit 15: Documentation updates (Phase 7)

**Testing between commits:** Run tests after each commit to catch regressions early.

**Rollback strategy:** If issues arise, individual commits can be reverted without losing entire refactor.

## Dependencies

### Prerequisites
- No blocking dependencies
- Can start immediately

### Blocks
- None (this is internal refactoring, no external API changes)

### Related Work
- Unified Schema Contracts (already complete) - provides PipelineRow abstraction
- Contract Propagation (already complete) - provides narrow_contract_to_output()

## Open Questions

1. **Should GateResult return PipelineRow too?**
   - Current: Gates return dict, executor wraps
   - Alternative: Gates return PipelineRow directly
   - **Recommendation:** Keep as dict - gates are evaluators, not constructors

2. **Delete TransformResult.contract field or deprecate?**
   - Delete: Cleaner, enforces new pattern immediately
   - Deprecate: Allows gradual migration
   - **Recommendation:** Delete - we're updating all transforms anyway

3. **Should to_pipeline_row() helpers raise clear errors or be deleted?**
   - Delete: Enforces correct usage
   - Keep with error: Helps catch bugs during migration
   - **Recommendation:** Delete after verifying no usage

## Approval

- [ ] Technical lead review
- [ ] Architecture review (if needed)
- [ ] User (John) approval to proceed

## Next Steps

1. **User approval:** Get confirmation to proceed with this plan
2. **Create branch:** `feature/pipeline-row-everywhere-refactor`
3. **Start Phase 1:** Update type signatures
4. **Iterate:** Follow phase-by-phase plan with testing between each commit
