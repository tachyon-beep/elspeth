# T17 Phase 4: Update Engine Layer

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update executors and orchestrator to pass protocol-typed context to plugins while keeping concrete `PluginContext` for mutation.

**Architecture:** Executors continue to accept and mutate `PluginContext` (the concrete class). When they call plugin methods, mypy verifies that `PluginContext` satisfies the expected protocol. No runtime changes — this phase updates type annotations in the engine layer.

**Tech Stack:** mypy strict mode, existing executor patterns

**Prerequisite:** Phase 2-3 complete (all plugin signatures narrowed)

**Key constraint:** Executors MUTATE ctx fields (`ctx.state_id = ...`, `ctx.token = ...`). They MUST keep accepting the concrete `PluginContext`, not a protocol type. The protocols are read-only views; mutation happens on the concrete class.

---

## Task 1: Verify executors already work with protocol-typed plugins

**Files:**
- Read-only: `src/elspeth/engine/executors/transform.py`
- Read-only: `src/elspeth/engine/executors/sink.py`
- Read-only: `src/elspeth/engine/executors/gate.py`
- Read-only: `src/elspeth/engine/executors/aggregation.py`

**Step 1: Run mypy on executors**

Run: `.venv/bin/python -m mypy src/elspeth/engine/executors/`
Expected: This may already pass because PluginContext satisfies all protocols, and executors pass PluginContext to plugin methods. If mypy is clean, minimal work needed here.

**Step 2: Identify any mypy errors**

If there are errors, they'll be of the form:
```
Argument 2 of "process" has incompatible type "PluginContext"; expected "TransformContext"
```

This should NOT happen because PluginContext satisfies TransformContext structurally. But if it does, it means a protocol definition is wrong — fix the protocol in `contracts/contexts.py`, not the executor.

---

## Task 2: Update executor type annotations (if needed)

**Files:**
- Modify: `src/elspeth/engine/executors/transform.py`
- Modify: `src/elspeth/engine/executors/sink.py`
- Modify: `src/elspeth/engine/executors/gate.py`
- Modify: `src/elspeth/engine/executors/aggregation.py`
- Modify: `src/elspeth/engine/executors/state_guard.py`

**Step 1: Review ctx mutation sites**

These are the mutation sites that MUST keep `PluginContext` (not protocol):

```python
# transform.py:247-260
ctx.state_id = guard.state_id       # Writes to ctx before calling transform
ctx.node_id = transform.node_id
ctx.contract = token.row_data.contract
ctx.token = token

# aggregation.py:363-371
ctx.state_id = guard.state_id
ctx.node_id = node_id
ctx.batch_token_ids = batch_token_ids

# aggregation.py:418,531,555,570 (cleanup assignments)
ctx.batch_token_ids = None  # 4 sites resetting batch state

# sink.py:199-205
ctx.contract = batch_contract
ctx.state_id = None

# gate.py:232
ctx.contract = token.row_data.contract

# state_guard.py:43
ctx.state_id = guard.state_id
```

All of these MUST accept `PluginContext` (concrete), not a protocol.

**Step 2: Update method signatures where ctx is passed to plugins**

In executor methods, the `ctx` parameter should be typed as `PluginContext`:
```python
def execute_transform(self, transform: TransformProtocol, token: ..., ctx: PluginContext) -> ...:
```

This is likely already the case. Verify and adjust if needed.

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/ tests/integration/ -v --timeout=120`
Expected: All pass

**Step 4: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/engine/`
Expected: Clean

---

## Task 3: Update orchestrator

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`
- Modify: `src/elspeth/engine/orchestrator/aggregation.py`
- Modify: `src/elspeth/engine/orchestrator/export.py`
- Modify: `src/elspeth/engine/orchestrator/outcomes.py`

**Step 1: Review PluginContext construction sites**

Construction sites that MUST keep PluginContext:

```python
# core.py:1205 — Main run construction
ctx = PluginContext(run_id=..., config=..., landscape=..., ...)

# core.py:2180 — Resume run construction
ctx = PluginContext(run_id=..., config=..., landscape=..., ...)

# export.py:92 — Export sink context
ctx = PluginContext(run_id=..., config={}, landscape=...)
```

These construct the concrete class — no change needed.

**Step 2: Review ctx mutation sites in orchestrator**

```python
# core.py:1218
ctx.node_id = source_id

# core.py:1514
ctx.operation_id = source_operation_id

# core.py:1546
ctx.contract = schema_contract

# core.py:1557
ctx.operation_id = None

# core.py:1646-1729 (resume path, similar mutations)
ctx.operation_id = source_operation_id
ctx.contract = schema_contract

# core.py:2191
ctx.contract = recorder.get_run_contract(run_id)
```

All of these operate on the concrete PluginContext — no change needed.

**Step 3: Update type annotations in orchestrator methods**

Methods in the orchestrator that accept `ctx` as a parameter should keep `PluginContext`:
```python
# These all keep PluginContext because they mutate ctx
def _execute_run(self, ctx: PluginContext, ...) -> ...:
def _process_single_token(self, ctx: PluginContext, ...) -> ...:
```

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/ tests/integration/ -v --timeout=120`
Expected: All pass

**Step 5: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/engine/`
Expected: Clean

---

## Task 4: Update `core/operations.py`

**Files:**
- Modify: `src/elspeth/core/operations.py`

**Step 1: Review `track_operation` signature**

```python
# Line 54-60
@contextmanager
def track_operation(
    recorder: LandscapeRecorder,
    run_id: str,
    node_id: str,
    operation_type: Literal["source_load", "sink_write"],
    ctx: PluginContext,
```

This function mutates `ctx.operation_id`. It MUST keep `PluginContext`.

**Step 2: Verify no changes needed**

Since `track_operation` mutates ctx, it keeps the concrete type. No change.

**Step 3: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/core/operations.py`
Expected: Clean

---

## Task 5: Update processor

**Files:**
- Modify: `src/elspeth/engine/processor.py`

**Step 1: Review RowProcessor methods**

The processor passes ctx to executors. Since executors accept `PluginContext`, the processor should too.

**Step 2: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/engine/processor.py`
Expected: Clean (or fix any new errors)

---

## Task 6: Commit Phase 4

**Step 1: Commit**

```bash
git add src/elspeth/engine/ src/elspeth/core/operations.py
git commit -m "refactor(T17): Phase 4 — verify engine layer compatibility with protocol-typed plugins

Executors and orchestrator keep PluginContext (concrete) for mutation.
mypy verifies PluginContext satisfies all protocols when passed to
narrowed plugin signatures. Minimal annotation changes in engine."
```

**Step 2: Full verification**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/ && .venv/bin/python -m ruff check src/ && .venv/bin/python -m scripts.check_contracts && .venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: All pass
