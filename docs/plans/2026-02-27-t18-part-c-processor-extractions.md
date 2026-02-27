# T18 Part C: Processor Extractions

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract 3 methods from `_process_single_token()` and collapse it into a ~65-line flow control method.

**Architecture:** Pure extract-method refactoring on `RowProcessor`. Each extracted method returns the discriminated union types defined in Part A (`_TransformOutcome`, `_GateOutcome`). The caller dispatches with `isinstance`.

**Tech Stack:** No new dependencies. `isinstance`-based discriminated union dispatch.

**Parent plan:** [T18 Implementation Plan Index](2026-02-27-t18-implementation-plan-index.md)

**Pre-requisite:** [Part A](2026-02-27-t18-part-a-types-and-tests.md) and [Part B](2026-02-27-t18-part-b-orchestrator-extractions.md) must be complete.

---

## Verification command (run after every commit)

```bash
.venv/bin/python -m pytest tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ tests/property/engine/ -x --tb=short
```

---

## Commit #11: Extract `_handle_transform_node()`

**Risk:** Lower (well-bounded block, existing tests cover all branches)

### Task 11.1: Extract the TransformProtocol branch

**Files:**
- Modify: `src/elspeth/engine/processor.py`

**Step 1: Add the new method**

Extracts lines 1635-1784 from `_process_single_token()` — the `isinstance(plugin, TransformProtocol)` branch AFTER the batch-aware shortcut (lines 1620-1633 stay in the caller).

Signature:

```python
def _handle_transform_node(
    self,
    transform: TransformProtocol,
    current_token: TokenInfo,
    ctx: PluginContext,
    node_id: NodeID,
    child_items: list[WorkItem],
    coalesce_node_id: NodeID | None,
    coalesce_name: CoalesceName | None,
    current_on_success_sink: str,
) -> _TransformOutcome:
    """Handle a single transform node: execute with retry, route errors, handle multi-row.

    Args:
        transform: The transform plugin to execute.
        current_token: Token being processed through the DAG.
        ctx: Plugin context for the current run.
        node_id: Current DAG node ID (needed for deaggregation expand_token() and
            child work item creation via create_continuation_work_item()).
        child_items: Mutable list — deaggregation appends child work items here.
        coalesce_node_id: Coalesce barrier node for fork branches (or None).
        coalesce_name: Coalesce point name for fork branches (or None).
        current_on_success_sink: Current sink name, may be updated by transform.on_success.

    Returns:
        _TransformContinue: Token should advance to next node (updated token + updated sink).
        _TransformTerminal: Token reached terminal state (FAILED, QUARANTINED, ROUTED, or EXPANDED).
    """
```

**The method body contains (in order):**

1. `self._execute_transform_with_retry()` call (try block)
2. `self._emit_transform_completed()` call
3. `except MaxRetriesExceeded` → record FAILED outcome, notify coalesce, return `_TransformTerminal`
4. Error status check (`transform_result.status == "error"`):
   - `error_sink == "discard"` → record QUARANTINED, notify coalesce, return `_TransformTerminal`
   - else → ROUTED to error sink, notify coalesce, return `_TransformTerminal`
5. `on_success` tracking: update sink if `transform.on_success is not None`
6. Multi-row check (`transform_result.is_multi_row`):
   - Validate `creates_tokens` flag
   - `self._token_manager.expand_token()` with `node_id=node_id` (this is why `node_id` is a required parameter)
   - Create child work items via `self._nav.create_continuation_work_item()`
   - Return `_TransformTerminal` with EXPANDED outcome
7. Single row success: return `_TransformContinue(updated_token=current_token, updated_sink=updated_sink)`

**Critical detail — `updated_sink` logic:**

```python
# Inside the method, after error checks pass:
updated_sink = current_on_success_sink
if transform.on_success is not None:
    updated_sink = transform.on_success

# ... multi-row check returns _TransformTerminal if multi-row ...

# Single row:
return _TransformContinue(updated_token=current_token, updated_sink=updated_sink)
```

**Step 2: Replace the TransformProtocol branch in `_process_single_token()`**

The `isinstance(plugin, TransformProtocol)` block (after the batch-aware shortcut) becomes:

```python
if isinstance(plugin, TransformProtocol):
    row_transform = plugin
    # Batch-aware shortcut (unchanged — stays in caller)
    transform_node_id = row_transform.node_id
    if row_transform.is_batch_aware and transform_node_id is not None and transform_node_id in self._aggregation_settings:
        return self._process_batch_aggregation_node(
            transform=row_transform,
            current_token=current_token,
            ctx=ctx,
            child_items=child_items,
            coalesce_node_id=coalesce_node_id,
            coalesce_name=coalesce_name,
        )

    outcome = self._handle_transform_node(
        row_transform, current_token, ctx, node_id, child_items,
        coalesce_node_id, coalesce_name, last_on_success_sink,
    )
    if isinstance(outcome, _TransformTerminal):
        return outcome.result, child_items
    current_token = outcome.updated_token
    last_on_success_sink = outcome.updated_sink
```

**Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ -x --tb=short
```
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspeth/engine/processor.py
git commit -m "refactor(t18): extract _handle_transform_node() from _process_single_token()"
```

---

## Commit #12: Extract `_handle_gate_node()` ⚠️ MEDIUM-HIGH RISK

**Risk:** Medium-high — multiple branches (fork/route/continue/jump/error), `next_node_id` semantics, and a type fix required.

### Task 12.0: Fix `_GateContinue` — add missing `updated_token` field

**IMPORTANT:** The `_GateContinue` type defined in Part A (commit #2) is missing `updated_token`. The gate executor *always* updates the token (line 1794: `current_token = outcome.updated_token`). Without this field, the extraction would silently lose the updated token — subsequent nodes would process stale data.

**Files:**
- Modify: `src/elspeth/engine/processor.py` (type definition at line ~133)
- Modify: `tests/unit/engine/test_processor.py` (update `TestProcessorOutcomeTypes` tests)

**Step 1: Add `updated_token` to `_GateContinue`**

Change the type definition (around line 132-137):

```python
@dataclass(frozen=True, slots=True)
class _GateContinue:
    """Gate says advance to next node (or jump to a specific node)."""

    updated_token: TokenInfo
    updated_sink: str
    next_node_id: NodeID | None = None  # None = next structural node
```

Note: `updated_token` must come before `updated_sink` or both must come before `next_node_id` (which has a default). The order `updated_token, updated_sink, next_node_id=None` is cleanest — required fields first, optional last.

**Step 2: Update `TestProcessorOutcomeTypes` tests**

In `tests/unit/engine/test_processor.py`, update these tests:

`test_gate_continue_default_next_node` — add `updated_token`:
```python
def test_gate_continue_default_next_node(self) -> None:
    from elspeth.engine.processor import _GateContinue

    outcome = _GateContinue(updated_token=Mock(), updated_sink="output")
    assert outcome.next_node_id is None
```

`test_gate_continue_explicit_next_node` — add `updated_token`:
```python
def test_gate_continue_explicit_next_node(self) -> None:
    from elspeth.engine.processor import _GateContinue

    outcome = _GateContinue(updated_token=Mock(), updated_sink="output", next_node_id=NodeID("jump_target"))
    assert outcome.next_node_id == NodeID("jump_target")
```

`test_gate_outcome_isinstance_dispatch` — add `updated_token`:
```python
continue_outcome = _GateContinue(updated_token=Mock(), updated_sink="out")
```

`test_all_outcome_types_are_frozen` — update the `_GateContinue` kwargs:
```python
(_GateContinue, {"updated_token": Mock(), "updated_sink": "out"}),
```

**Step 3: Run tests to verify type fix**

```bash
.venv/bin/python -m pytest tests/unit/engine/test_processor.py::TestProcessorOutcomeTypes -v
```
Expected: All PASS

### Task 12.1: Extract the GateSettings branch

**Files:**
- Modify: `src/elspeth/engine/processor.py`

**Step 4: Add the new method**

Extracts lines 1785-1893 from `_process_single_token()`. Signature:

```python
def _handle_gate_node(
    self,
    gate: GateSettings,
    current_token: TokenInfo,
    ctx: PluginContext,
    node_id: NodeID,
    child_items: list[WorkItem],
    coalesce_node_id: NodeID | None,
    coalesce_name: CoalesceName | None,
    current_on_success_sink: str,
) -> _GateOutcome:
    """Handle a gate node: evaluate, then fork/route/divert/continue.

    Args:
        gate: Gate configuration to evaluate.
        current_token: Token being processed through the DAG.
        ctx: Plugin context for the current run.
        node_id: Current DAG node ID (passed to gate executor and used for
            fork child work item creation).
        child_items: Mutable list — fork paths append child work items here.
        coalesce_node_id: Coalesce barrier node for fork branches (or None).
        coalesce_name: Coalesce point name for fork branches (or None).
        current_on_success_sink: Current sink name, carried forward or overridden by jumps.

    Returns:
        _GateTerminal: Gate routed to sink, forked to paths, or diverted (contains result + child_items populated).
        _GateContinue: Gate says continue — updated_token, updated_sink, and optional next_node_id for jumps.
    """
```

**The method body contains (in order):**

1. `self._gate_executor.execute_config_gate()` call → produces `outcome` (GateOutcome)
2. `current_token = outcome.updated_token` — gate always updates token
3. `self._emit_gate_evaluated()` call
4. Route to sink check (`outcome.sink_name is not None`):
   - Notify coalesce of lost branch
   - Return `_GateTerminal` with ROUTED result
5. Fork check (`outcome.result.action.kind == RoutingKind.FORK_TO_PATHS`):
   - Iterate `outcome.child_tokens`, look up coalesce info per branch
   - Create child work items (branch→sink direct or continuation)
   - Return `_GateTerminal` with FORKED result
6. Jump check (`outcome.next_node_id is not None`):
   - `resolved_sink = self._nav.resolve_jump_target_sink(outcome.next_node_id)`
   - Update sink if resolved
   - **Coalesce ordering re-validation** (lines 1867-1879 in current code) — stays inside this method because it's gate-specific. Raises `OrchestrationInvariantError` if jump target is past coalesce node.
   - Return `_GateContinue(updated_token=current_token, updated_sink=resolved_or_current_sink, next_node_id=outcome.next_node_id)`
7. Continue (`RoutingKind.CONTINUE`):
   - Validate kind is CONTINUE (error if unexpected kind)
   - Return `_GateContinue(updated_token=current_token, updated_sink=current_on_success_sink)`

**Critical detail — sink resolution for jumps:**

```python
# Inside the method, for jump path:
updated_sink = current_on_success_sink
resolved_sink = self._nav.resolve_jump_target_sink(outcome.next_node_id)
if resolved_sink is not None:
    updated_sink = resolved_sink
return _GateContinue(
    updated_token=current_token,
    updated_sink=updated_sink,
    next_node_id=outcome.next_node_id,
)
```

**Step 5: Replace the GateSettings branch in `_process_single_token()`**

```python
elif isinstance(plugin, GateSettings):
    gate_outcome = self._handle_gate_node(
        plugin, current_token, ctx, node_id, child_items,
        coalesce_node_id, coalesce_name, last_on_success_sink,
    )
    if isinstance(gate_outcome, _GateTerminal):
        return gate_outcome.result, child_items
    current_token = gate_outcome.updated_token
    last_on_success_sink = gate_outcome.updated_sink
    if gate_outcome.next_node_id is not None:
        node_id = gate_outcome.next_node_id
        continue
```

Note the `current_token = gate_outcome.updated_token` line — this is the fix enabled by Task 12.0.

**Step 6: Run HIGH-RISK test suite**

```bash
.venv/bin/python -m pytest tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ tests/integration/pipeline/ tests/property/engine/ -x --tb=short
```
Expected: All PASS

**Step 7: Commit**

```bash
git add src/elspeth/engine/processor.py tests/unit/engine/test_processor.py
git commit -m "refactor(t18): extract _handle_gate_node() from _process_single_token()

Includes fix: added updated_token field to _GateContinue (was missing from
Part A type definition). Gate executor always updates the token — without
this field, the extraction would silently lose the updated token."
```

---

## Commit #13: Extract `_handle_terminal_token()`

**Risk:** Lower (post-loop terminal routing is straightforward)

### Task 13.1: Extract the terminal token handling

**Files:**
- Modify: `src/elspeth/engine/processor.py`

**Step 1: Add the new method**

Extracts lines 1897-1923 from `_process_single_token()` (the post-while-loop code). Signature:

```python
def _handle_terminal_token(
    self,
    current_token: TokenInfo,
    current_on_success_sink: str,
) -> RowResult:
    """Handle a token that has traversed all nodes: resolve final sink, return result.

    Determines the effective sink from:
    1. branch_to_sink mapping (for fork branches routing directly to sinks)
    2. last_on_success_sink (inherited from transforms or source)

    If the token has a branch_name that maps to a direct sink via _branch_to_sink,
    that takes precedence. Otherwise, the accumulated on_success sink is used.

    Raises:
        OrchestrationInvariantError: If no effective sink can be determined (indicates
            a DAG construction or on_success configuration bug).

    Returns:
        RowResult with COMPLETED outcome and resolved sink_name.
    """
```

Note: Return type is `RowResult` (not `RowResult | list[RowResult]`). The terminal path only ever produces a single result — lists are only produced by fork/deagg paths which return earlier.

**The method body contains:**

```python
def _handle_terminal_token(
    self,
    current_token: TokenInfo,
    current_on_success_sink: str,
) -> RowResult:
    # Determine sink name from explicit routing maps. Fork children
    # targeting direct sinks are resolved via _branch_to_sink (built from
    # DAG COPY edges at construction time). Non-fork tokens use the last
    # transform's on_success or the source's on_success.
    effective_sink = current_on_success_sink
    if current_token.branch_name is not None:
        branch = BranchName(current_token.branch_name)
        if branch in self._branch_to_sink:
            effective_sink = self._branch_to_sink[branch]

    if not effective_sink or not effective_sink.strip():
        raise OrchestrationInvariantError(
            f"No effective sink for token {current_token.token_id}: "
            f"last_on_success_sink={current_on_success_sink!r}, "
            f"branch_name={current_token.branch_name!r}. "
            f"This indicates a DAG construction or on_success configuration bug."
        )

    return RowResult(
        token=current_token,
        final_data=current_token.row_data,
        outcome=RowOutcome.COMPLETED,
        sink_name=effective_sink,
    )
```

**Step 2: Replace in `_process_single_token()`**

The post-loop code (lines 1897-1923) becomes:

```python
result = self._handle_terminal_token(current_token, last_on_success_sink)
return result, child_items
```

**Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ -x --tb=short
```
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspeth/engine/processor.py
git commit -m "refactor(t18): extract _handle_terminal_token() from _process_single_token()"
```

---

## Commit #14: Collapse `_process_single_token()` — FINAL COMMIT

**Risk:** Lower (all extraction done, this just verifies the collapsed form)

### Task 14.1: Verify and clean up `_process_single_token()`

**Files:**
- Modify: `src/elspeth/engine/processor.py`

**Step 1: Verify the collapsed method is ~65 lines**

After commits #11-#13, `_process_single_token()` should already be approximately:

```python
def _process_single_token(
    self,
    token: TokenInfo,
    ctx: PluginContext,
    current_node_id: NodeID | None,
    coalesce_node_id: NodeID | None = None,
    coalesce_name: CoalesceName | None = None,
    on_success_sink: str | None = None,
) -> tuple[RowResult | list[RowResult] | None, list[WorkItem]]:
    current_token = token
    child_items: list[WorkItem] = []

    # current_node_id=None validation (unchanged, ~7 lines)
    if current_node_id is None:
        has_branch_sink = current_token.branch_name is not None and BranchName(current_token.branch_name) in self._branch_to_sink
        if on_success_sink is None and not has_branch_sink:
            raise OrchestrationInvariantError(...)

    last_on_success_sink: str = on_success_sink if on_success_sink is not None else self._source_on_success

    # Coalesce sink pre-resolution (unchanged, ~5 lines)
    if coalesce_name is not None and current_node_id is not None:
        coalesce_node_id_for_name = self._coalesce_node_ids[coalesce_name]
        if coalesce_node_id_for_name == current_node_id and self._nav.resolve_next_node(current_node_id) is None:
            last_on_success_sink = self._nav.resolve_coalesce_sink(...)

    # Coalesce ordering invariant (unchanged, ~10 lines)
    if coalesce_node_id is not None and current_node_id is not None and ...:
        ...

    node_id: NodeID | None = current_node_id
    max_inner_iterations = len(self._node_to_next) + 1
    inner_iterations = 0
    while node_id is not None:
        inner_iterations += 1
        if inner_iterations > max_inner_iterations:
            raise OrchestrationInvariantError(...)

        # Coalesce check
        handled, result = self._maybe_coalesce_token(...)
        if handled:
            return result, child_items

        next_node_id = self._nav.resolve_next_node(node_id)
        plugin = self._nav.resolve_plugin_for_node(node_id)
        if plugin is None:
            node_id = next_node_id
            continue

        if isinstance(plugin, TransformProtocol):
            row_transform = plugin
            # Batch-aware shortcut (unchanged)
            transform_node_id = row_transform.node_id
            if row_transform.is_batch_aware and transform_node_id is not None and transform_node_id in self._aggregation_settings:
                return self._process_batch_aggregation_node(...)

            outcome = self._handle_transform_node(
                row_transform, current_token, ctx, node_id, child_items,
                coalesce_node_id, coalesce_name, last_on_success_sink,
            )
            if isinstance(outcome, _TransformTerminal):
                return outcome.result, child_items
            current_token = outcome.updated_token
            last_on_success_sink = outcome.updated_sink

        elif isinstance(plugin, GateSettings):
            gate_outcome = self._handle_gate_node(
                plugin, current_token, ctx, node_id, child_items,
                coalesce_node_id, coalesce_name, last_on_success_sink,
            )
            if isinstance(gate_outcome, _GateTerminal):
                return gate_outcome.result, child_items
            current_token = gate_outcome.updated_token
            last_on_success_sink = gate_outcome.updated_sink
            if gate_outcome.next_node_id is not None:
                node_id = gate_outcome.next_node_id
                continue

        else:
            raise TypeError(f"Unknown transform type: {type(plugin).__name__}. Expected TransformProtocol or GateSettings.")

        node_id = next_node_id

    result = self._handle_terminal_token(current_token, last_on_success_sink)
    return result, child_items
```

If there's any leftover code that wasn't already refactored in commits #11-13, clean it up now.

**Step 2: Run FULL test suite**

```bash
.venv/bin/python -m pytest tests/ -x --tb=short
```
Expected: All PASS (8,000+ tests)

**Step 3: Run mypy**

```bash
.venv/bin/python -m mypy src/
```
Expected: Clean

**Step 4: Run ruff**

```bash
.venv/bin/python -m ruff check src/
```
Expected: Clean

**Step 5: Run config contracts checker**

```bash
.venv/bin/python -m scripts.check_contracts
```
Expected: Clean

**Step 6: Verify method sizes**

```bash
# Quick line count verification
grep -n "def _execute_run\|def _process_resumed_rows\|def _process_single_token\|def _handle_transform_node\|def _handle_gate_node\|def _handle_terminal_token\|def _register_graph\|def _initialize_run\|def _setup_resume\|def _handle_quarantine\|def _flush_and_write\|def _run_main_processing\|def _run_resume_processing" src/elspeth/engine/orchestrator/core.py src/elspeth/engine/processor.py
```

Verify no extracted method exceeds 150 lines.

**Step 7: Run characterization test one final time**

```bash
.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/test_t18_characterization.py -v
```
Expected: All PASS

**Step 8: Commit**

```bash
git add src/elspeth/engine/processor.py
git commit -m "refactor(t18): collapse _process_single_token() — T18 extraction complete"
```

---

## Part C Complete — T18 DONE

### Final State

| File | Before (current) | After | Delta |
|------|-------------------|-------|-------|
| `orchestrator/core.py` | ~2,270 (post-Part B) | ~2,270 | ~0 |
| `orchestrator/types.py` | ~200 (post-Part A) | ~200 | ~0 |
| `processor.py` | 1,923 | ~1,960 | +37 (method signatures + return type wrapping) |

### Methods Created (Part C only)

| Method | Class | Est. Lines | Returns |
|--------|-------|------------|---------|
| `_handle_transform_node` | RowProcessor | ~150 | `_TransformOutcome` |
| `_handle_gate_node` | RowProcessor | ~110 | `_GateOutcome` |
| `_handle_terminal_token` | RowProcessor | ~25 | `RowResult` |

### Methods Simplified

| Method | Before | After |
|--------|--------|-------|
| `_process_single_token()` | ~400 lines | ~70 lines |

### Full T18 Summary (Parts A+B+C)

| Method | Before | After |
|--------|--------|-------|
| `_execute_run()` | ~830 lines | ~90 lines |
| `_process_resumed_rows()` | ~290 lines | ~60 lines |
| `_process_single_token()` | ~400 lines | ~70 lines |

### Close the filigree issue

```bash
filigree close elspeth-rapid-cfcbcd --reason="T18 complete: 15 commits, 10 extracted methods, all tests pass"
```
