# DIVERT Edge Audit Completeness — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the audit trail gaps left by the DIVERT edge structural fix (2026-02-06). Make quarantine and error routing fully auditable via `routing_events`, add per-row source `node_states`, improve DIVERT visibility in MCP tooling, and fix the fork/coalesce + `on_error` interaction risk.

**Architecture:** Seven tasks in three phases. Phase 1 (quick wins) adds transform error `routing_events` (recorded inside TransformExecutor, following GateExecutor pattern) and Mermaid styling with no schema changes. Phase 2 (audit completeness) adds per-row source `node_states` (processor-internal for valid rows, orchestrator for quarantine — no interface changes), enabling quarantine `routing_events`. Phase 3 (robustness) adds fork/coalesce branch-loss notification and MCP lineage improvements.

**Tech Stack:** Python, SQLAlchemy (landscape schema), NetworkX (DAG), Pydantic (config)

**Predecessor Plan:** `2026-02-06-quarantine-sink-multipath-edges.md` (DIVERT edges — completed)

---

## Design Decisions

### Decision 1: Full per-row source node_states (not quarantine-only)

Every source row gets a `begin_node_state()` → `complete_node_state()` cycle, matching the pattern used by transforms and sinks. The alternative — creating source states only for quarantined rows — would create an asymmetric model where the source is the only node that sometimes creates states and sometimes doesn't. Full per-row states also provide source-level timing data and a clean anchor for future enhancements (e.g., source-level `routing_events` for the `continue` edge).

**Volume impact:** For a pipeline with N transforms, current node_states per row = N (transforms) + 1 (sink) = N+1. Adding source states makes it N+2 — a ~1/(N+1) relative increase. For a 5-transform LLM pipeline, this is ~14%. The recorder currently has no bulk write primitives (each `begin_node_state` / `complete_node_state` is a separate connection), so the hot-loop overhead is real but bounded: 2 extra DB operations per row (begin + complete) where the source state is completed immediately for valid rows.

### Decision 2: Transform error routing_events recorded inside the TransformExecutor (following GateExecutor pattern)

The TransformExecutor records DIVERT routing_events inside its own execution lifecycle, following the same pattern the GateExecutor already uses for gate routing_events. The GateExecutor calls `begin_node_state()`, runs the gate, records routing_events with the in-scope `state_id`, then calls `complete_node_state()`. The TransformExecutor will do the same for error routing: after completing the node_state as FAILED, record the DIVERT routing_event before returning.

**Why not record at the orchestrator (Option 2-B):** The orchestrator receives `RowResult` from the processor, which contains the outcome and sink name but not the `state_id` of the transform that made the error-routing decision. Recording at the orchestrator would require threading `state_id` through `RowResult` — adding a field to a data contract purely to support audit wiring in a different component. This violates locality and couples `RowResult` to audit infrastructure.

**Why not record at the processor (Option 2-A):** Verification revealed that `execute_transform()` returns `(TransformResult, TokenInfo, error_sink)` — the `state_id` is NOT in the return tuple and is local to the executor. The processor cannot access it without interface changes. Rather than adding `state_id` to the return tuple (splitting audit lifecycle across executor and processor), we keep routing_event recording co-located with the node_state lifecycle inside the executor — exactly as the GateExecutor already does.

**Implementation:** The TransformExecutor needs access to the `edge_map` for DIVERT edge lookup. The processor already has `self._edge_map` and passes a subset to the GateExecutor at construction. The same pattern is used: pass an error-edge lookup function (or the edge_map itself) to the TransformExecutor.

For quarantine routing_events, the orchestrator IS the decision-maker (source validation failures are handled in the orchestrator's source loading loop), so recording there is natural and correct.

### Decision 3: Fork/coalesce — validation warning + branch-loss notification (Levels 1+2)

Level 1: DAG validation warns when a transform with `on_error` routing to a sink exists inside a fork branch whose downstream coalesce uses `require_all` policy. This catches guaranteed-failure configurations at pipeline creation time.

Level 2: Add `CoalesceExecutor.notify_branch_lost(row_id, branch_name, reason)`. The processor calls this when error-routing a forked token. The coalesce executor removes the branch from the expected set for that `row_id`, re-evaluates merge conditions immediately (no waiting for timeout), and records the loss reason in the merge audit trail. This also fixes the "true idle" starvation problem — the notification triggers evaluation rather than waiting for the next row.

Level 3 (proactive failure cascade) is deferred. Once the coalesce executor has branch-loss awareness (Level 2), adding early failure for `require_all` is a policy decision, not an architectural change.

### Decision 4: MCP explain_token — annotate inline (not filter)

DIVERT edges and routing_events are included in the standard lineage response with an `is_divert: true` annotation. Filtering hides information that debugging users need. The consumer (human or tool) can decide what to display.

---

## Phase 1: Quick Wins (no schema changes)

### Task 1: Transform error routing_events

Record a `routing_event` when a transform fails and routes a token to an error sink via `on_error`. The routing_event is recorded inside the TransformExecutor, following the GateExecutor pattern.

**Files:**
- Modify: `src/elspeth/engine/executors.py` (TransformExecutor — add error edge lookup and routing_event recording in return-error path)
- Modify: `src/elspeth/engine/processor.py` (pass error edge lookup to TransformExecutor at construction; add routing_event recording in retry-disabled exception catch blocks at lines 1220-1277)
- Test: `tests/engine/test_transform_error_routing.py` (new test file)

**Implementation:**

Step 1: **Extract error edge label helper.** The magic string `f"__error_{seq}__"` is used in both `dag.py` (edge creation) and now `executors.py` (edge lookup). Extract a shared helper to prevent drift:

```python
# In contracts/enums.py or core/dag.py (alongside __quarantine__)
def error_edge_label(transform_seq: int) -> str:
    """Canonical label for a transform error DIVERT edge."""
    return f"__error_{transform_seq}__"
```

Step 2: **Pass error edge lookup to TransformExecutor.** The processor already has `self._edge_map`. At construction, build a per-transform error edge lookup and pass it to the TransformExecutor:

```python
# In processor __init__ or where TransformExecutor is constructed
error_edge_ids: dict[NodeID, str] = {}
for i, transform in enumerate(transforms):
    key = (NodeID(transform.node_id), error_edge_label(i))
    if key in self._edge_map:
        error_edge_ids[NodeID(transform.node_id)] = self._edge_map[key]
```

Step 3: **Record routing_event inside TransformExecutor.** Following the GateExecutor pattern (`executors.py:656-700`), after completing the node_state as FAILED and before returning the error result:

```python
# Inside TransformExecutor, in the error path (after complete_node_state FAILED):
if error_sink and error_sink != "discard":
    error_edge_id = self._error_edge_ids.get(NodeID(transform.node_id))
    if error_edge_id is None:
        raise ValueError(
            f"DAG misconfiguration: no error edge for transform {transform.node_id}. "
            f"Transform has on_error={error_sink!r} but no __error_N__ DIVERT edge exists."
        )
    self._recorder.record_routing_event(
        state_id=state.state_id,  # In scope — same as GateExecutor pattern
        edge_id=error_edge_id,
        mode=RoutingMode.DIVERT,
        reason=error_reason,
    )
```

**Key detail:** The `state_id` is in scope inside the executor (from `begin_node_state()`). This is the same pattern the GateExecutor uses — the executor owns the full audit lifecycle: begin state → execute → record routing → complete state.

Step 4: **Handle the retry-disabled exception path in the processor.** There is a second error-routing path: when retry is disabled (`self._retry_manager is None`), the processor catches `LLMClientError`, `ConnectionError`, `TimeoutError`, and `OSError` exceptions from the executor (`processor.py:1220-1277`) and converts them to error results with `on_error` routing. The executor has already completed the node_state as FAILED and re-raised, but no routing_event was recorded (because the exception path might be retried — the routing decision hasn't been finalized).

In this path, the processor must record the routing_event using `ctx.state_id`, which the executor set at `executors.py:247` before the transform executed:

```python
# In processor, after catching retryable exception with retry disabled:
# ctx.state_id was set by executor before the exception propagated
if on_error != "discard":
    error_edge_id = self._error_edge_ids.get(NodeID(transform.node_id))
    if error_edge_id is None:
        raise ValueError(
            f"DAG misconfiguration: no error edge for transform {transform.node_id}. "
            f"Transform has on_error={on_error!r} but no __error_N__ DIVERT edge exists."
        )
    self._recorder.record_routing_event(
        state_id=ctx.state_id,  # Set by executor at executors.py:247
        edge_id=error_edge_id,
        mode=RoutingMode.DIVERT,
        reason=error_details,
    )
```

**Why two recording sites:** The executor records routing_events for the *return-error path* (transform returns `TransformResult.error()`). The processor records routing_events for the *exception path* (transform raises, retry disabled). We cannot record in the executor's exception handler (`executors.py:313`) because that exception may be retried by the RetryManager — the routing decision is only finalized when the processor decides to route. The `ctx.state_id` side-channel bridges the gap cleanly.

**Note:** The retry-exhaustion path (when all retries fail) should also be audited, but that's a separate concern — the RetryManager's final-failure handling needs its own analysis. Document as a follow-up.

**Tests:**
- Verify that processing a row through a transform with `on_error` creates a `routing_event` with `mode=DIVERT` (return-error path)
- Verify the routing_event references the correct `state_id` (the transform's node_state) and `edge_id` (the `__error_N__` edge)
- Verify the `reason_hash` captures the error detail
- Verify no routing_event is created for `on_error: discard` (discard has no edge)
- Verify missing error edge raises `ValueError` (crash, not silent skip)
- Verify that a retryable exception with retry disabled also creates a `routing_event` via `ctx.state_id` (exception path)
- Verify that the exception-path routing_event references the same `state_id` as the executor's `complete_node_state(FAILED)`

**Commit separately.**

---

### Task 2: Mermaid diagram DIVERT edge styling

Render DIVERT edges as dashed arrows in Mermaid diagrams generated by `get_dag_structure()`.

**Files:**
- Modify: `src/elspeth/mcp/server.py` (`get_dag_structure()`, ~lines 638-692)
- Test: `tests/mcp/test_mcp_divert.py` (or existing MCP test file)

**Implementation:**

Step 1: **Add RoutingMode import.** In `server.py`, line 27 currently imports `CallStatus` from `elspeth.contracts.enums`. Add `RoutingMode` to this import:

```python
from elspeth.contracts.enums import CallStatus, RoutingMode
```

Step 2: **Update the edge list response** (server.py:666-674). The current edge list structure is:

```python
edge_list = [
    {
        "from": e.from_node_id,
        "to": e.to_node_id,
        "label": e.label,
        "mode": e.default_mode.value,
    }
    for e in edges
]
```

Add `"flow_type"`:

```python
edge_list = [
    {
        "from": e.from_node_id,
        "to": e.to_node_id,
        "label": e.label,
        "mode": e.default_mode.value,
        "flow_type": "divert" if e.default_mode == RoutingMode.DIVERT else "normal",
    }
    for e in edges
]
```

Step 3: **Update the Mermaid generation loop** (server.py:681-683). The current loop is:

```python
for e in edges:
    arrow = "-->" if e.label == "continue" else f"-->|{e.label}|"
    lines.append(f"    {e.from_node_id[:8]} {arrow} {e.to_node_id[:8]}")
```

Replace with mode-aware rendering:

```python
for e in edges:
    if e.default_mode == RoutingMode.DIVERT:
        arrow = f"-.->|{e.label}|"
    elif e.label == "continue":
        arrow = "-->"
    else:
        arrow = f"-->|{e.label}|"
    lines.append(f"    {e.from_node_id[:8]} {arrow} {e.to_node_id[:8]}")
```

The `-.->` syntax is standard Mermaid for dashed arrows. The `Edge` dataclass (contracts/audit.py:98-115) already has `default_mode: RoutingMode` as a strict enum field, so the comparison works directly.

**Tests:**
- Verify DIVERT edges render with `-.->` syntax in Mermaid output
- Verify normal edges still use `-->` or `-->|label|`
- Verify edge list entries include `flow_type` field
- Verify the `mode` field is still present (backwards compatible)

**Commit separately.**

---

## Phase 2: Audit Completeness

### Task 3: Per-row source node_states

Create a `node_state` for each source row, representing "source processed this row." No interface changes to `process_row()`.

**Files:**
- Modify: `src/elspeth/engine/processor.py` (add source node_state in both `process_row()` and `process_existing_row()`)
- Modify: `src/elspeth/engine/orchestrator/core.py` (add source node_state for quarantine rows)
- Test: `tests/engine/test_orchestrator_routing.py`, `tests/integration/test_cli_integration.py`

**Verified safe (pre-implementation risk reduction):**
- **step_index=0 is free:** Transforms already use step_index=1+ (`step = start_step + step_offset + 1` in processor.py:1633). No code compares step_index to 0. No shift needed.
- **Resume is safe:** Resume creates new tokens with new token_ids via `create_token_for_existing_row()`. UNIQUE constraint is `(token_id, node_id, attempt)` — different token_id = no conflict.
- **edge_map has DIVERT edges:** Verified — no filtering excludes them at any stage.

**Implementation approach (no interface change):**

Source node_states are created at the point where token_id becomes available, which differs for valid and quarantined rows:

1. **Valid rows (processor-internal):** Inside `process_row()`, immediately after `create_initial_token()` creates the token (line 1338) and before transform processing begins:

   ```python
   # After token creation, before transform loop
   source_state = self._recorder.begin_node_state(
       token_id=token.token_id,
       node_id=self._source_node_id,  # Already a constructor param
       run_id=self._run_id,           # Already a constructor param
       step_index=0,
       input_data=source_row.row,
   )
   self._recorder.complete_node_state(
       state_id=source_state.state_id,
       status=NodeStateStatus.COMPLETED,
       output_data=source_row.row,
       duration_ms=0,  # Source "processing" already happened in plugin iterator
   )
   ```

   This preserves temporal ordering: source state (step 0) is recorded before any transform states (step 1+).

2. **Quarantined rows (orchestrator):** In the orchestrator's quarantine path (core.py:1190-1273), after `create_quarantine_token()` creates the token:

   ```python
   # After quarantine token creation
   source_state = recorder.begin_node_state(
       token_id=quarantine_token.token_id,
       node_id=source_node_id,
       run_id=run_id,
       step_index=0,
       input_data=quarantine_data,
   )
   recorder.complete_node_state(
       state_id=source_state.state_id,
       status=NodeStateStatus.FAILED,
       error={"reason": "source_validation_failure", "detail": quarantine_error},
   )
   # source_state.state_id is now available for Task 4's routing_event
   ```

3. **Resumed rows (processor-internal via `process_existing_row()`):** The resume path uses `process_existing_row()` (processor.py:1389), which creates a new token via `create_token_for_existing_row()` (line 1417) and starts the work queue at `start_step=0`. Add source state creation after token creation, same pattern as valid rows:

   ```python
   # After create_token_for_existing_row(), before transform loop
   source_state = self._recorder.begin_node_state(
       token_id=token.token_id,
       node_id=self._source_node_id,
       run_id=self._run_id,
       step_index=0,
       input_data=row_data.to_dict(),
   )
   self._recorder.complete_node_state(
       state_id=source_state.state_id,
       status=NodeStateStatus.COMPLETED,
       output_data=row_data.to_dict(),
       duration_ms=0,  # Source already processed in original run
   )
   ```

   **Why resumed rows need source states:** Resumed tokens have new token_ids (verified: `create_token_for_existing_row()` generates fresh IDs). Without a source state, the new token's lineage starts at step_index=1, breaking the root-token invariant and making the resumed token's lineage incomplete in `explain_token()`.

**Why no interface change:** The processor already has `self._run_id` and `self._source_node_id` from its constructor. Token creation happens inside both `process_row()` and `process_existing_row()`, so the token_id is available immediately. No need to move token creation to the orchestrator or add parameters.

**Volume impact:** 2 extra DB operations per row (begin + complete). For the current single-connection-per-operation recorder, this is the same pattern used by all node_states. For a 5-transform pipeline processing 10,000 rows, this adds 20,000 operations (~14% increase). This is a pre-existing performance characteristic of the recorder, not a new pattern — the batch_context optimization (connection reuse) would benefit ALL node_states equally and is tracked as a separate improvement.

**Invariant scope (fork/expand child tokens):** The audit trail completeness invariant is: **"every root token has exactly one node_state with step_index=0."** Root tokens are tokens with `parent_token_id IS NULL` — the initial token for a source row (from `process_row()` or `process_existing_row()`). Fork child tokens and expand child tokens are created mid-pipeline (`fork_token()` at tokens.py:204, `create_expand_token()`) and continue processing from a downstream step — they do NOT have source states and are excluded from this invariant. Their lineage is traced through `parent_token_id` back to the root token's source state.

**Tests:**
- Verify every source row (valid and quarantined) creates a source-level `node_state`
- Verify source state `step_index` is 0 (source is always step 0)
- Verify source state for valid rows has `status=COMPLETED`
- Verify source state for quarantined rows has `status=FAILED` with error detail
- Verify transform states have `step_index` starting at 1 (already the case — no shift)
- Verify total node_states count for root tokens = rows × (1 source + N transforms + 1 sink) for a complete run
- Verify audit trail completeness invariant: every root token (`parent_token_id IS NULL`) has exactly one node_state with step_index=0
- Verify fork child tokens do NOT have step_index=0 node_states (they inherit lineage via parent_token_id)
- Verify resumed rows create source node_states for the new token (no gap in lineage)
- Regression: existing integration tests still pass (quarantine routing, error routing, fork/coalesce)
- Regression: resume/checkpoint creates no duplicate source node_states (new token_id = no UNIQUE violation)

**Commit separately.**

---

### Task 4: Quarantine routing_events

Record a `routing_event` when a source row fails validation and gets quarantined.

**Depends on:** Task 3 (needs source state_id)

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py` (quarantine path, ~lines 1190-1273)
- Test: `tests/integration/test_cli_integration.py::TestSourceQuarantineRouting`

**Implementation:**

The quarantine handling path is at `orchestrator/core.py:1191` (`if source_item.is_quarantined:`). The following variables are in scope:

| Variable | Type | Source |
|----------|------|--------|
| `source_item` | `SourceRow` | Line 1161 (`enumerate(source_iterator)`) |
| `recorder` | `LandscapeRecorder` | Method param (line 768) |
| `source_id` | `NodeID` | Line 808 (`graph.get_source()`) |
| `edge_map` | `dict[tuple[NodeID, str], str]` | Line 907 (built from `graph.get_edges()`) |
| `quarantine_sink` | `str` | Line 1195 (`source_item.quarantine_destination`) |

Step 1: **After Task 3's source node_state creation** (which gives us `source_state.state_id`), look up the DIVERT edge and record the routing_event:

```python
quarantine_edge_key = (source_id, "__quarantine__")
quarantine_edge_id = edge_map.get(quarantine_edge_key)
if quarantine_edge_id is None:
    raise OrchestrationInvariantError(
        f"Quarantine row reached orchestrator but no __quarantine__ DIVERT edge exists "
        f"in DAG for source '{source_id}'. This is a DAG construction bug — "
        f"on_validation_failure={source._on_validation_failure!r} should have created "
        f"a DIVERT edge in from_plugin_instances()."
    )
error_detail = source_item.quarantine_error or "unknown_validation_error"
recorder.record_routing_event(
    state_id=source_state.state_id,  # From Task 3's begin_node_state()
    edge_id=quarantine_edge_id,
    mode=RoutingMode.DIVERT,
    reason={"quarantine_error": error_detail},
)
```

**Why crash, not skip:** If a quarantine row reaches the orchestrator (i.e., `source_item.is_quarantined == True`), then by definition `on_validation_failure != "discard"` — the source plugin only yields quarantined rows when the destination is a real sink. The `__quarantine__` DIVERT edge MUST exist because `from_plugin_instances()` creates it when `quarantine_dest != "discard"` (dag.py:798-806). A missing edge at this point is a DAG construction bug, not a configuration variant, and must crash per Tier 1 rules.

Step 2: **No routing_event for `on_validation_failure: discard` (rows never reach this path).** When `on_validation_failure` is `"discard"`, source plugins don't yield a `SourceRow` — the row is silently dropped at the source plugin level (e.g., `csv_source.py:199`: `if self._on_validation_failure != "discard": yield SourceRow.quarantined(...)`). Since no quarantine row reaches the orchestrator, this code path is never executed. No `__quarantine__` DIVERT edge exists in the DAG for discard-mode pipelines. The crash above is unreachable in the discard case.

**Tests:**
- Verify quarantined rows create a `routing_event` with `mode=DIVERT` and `edge_id` pointing to the `__quarantine__` edge
- Verify the routing_event's `state_id` is the source's node_state (not the sink's)
- Verify `reason_hash` captures the quarantine error detail
- Verify `on_validation_failure: discard` creates no quarantine token and no routing_event (row never reaches orchestrator)
- Verify `on_validation_failure: <sink_name>` creates both source node_state (FAILED) and routing_event (DIVERT)
- Verify the full lineage via `explain_token()` now includes the quarantine routing_event

**Commit separately.**

---

## Phase 3: Robustness

### Task 5: Fork/coalesce + on_error validation warning

Add DAG construction-time validation that warns about problematic `on_error` + coalesce configurations.

**Files:**
- Modify: `src/elspeth/core/dag.py` (new `_warn_divert_coalesce_interactions()` method, called from `from_plugin_instances()`)
- Test: `tests/core/test_dag.py`

**Design constraint:** `validate()` returns `None` (raises `GraphValidationError` on failure) and only checks structural correctness (cycles, reachability, unique labels). Changing its return type would be a larger refactor than needed. More importantly, the `_on_error` configuration is NOT stored in node_config — it's only accessible on transform instances during `from_plugin_instances()`, and it's consumed immediately to create DIVERT edges. However, the resulting DIVERT edges ARE in the graph, so the check can work from graph topology alone.

**Implementation:**

Step 1: **Add `GraphValidationWarning` dataclass** in `dag.py` (alongside `GraphValidationError` at line 36):

```python
@dataclass(frozen=True)
class GraphValidationWarning:
    """Non-fatal validation concern that doesn't prevent execution."""
    code: str          # e.g., "DIVERT_COALESCE_REQUIRE_ALL"
    message: str       # Human-readable description
    node_ids: tuple[str, ...]  # Affected nodes
```

Step 2: **Add `_warn_divert_coalesce_interactions()` method** on `ExecutionGraph`. This uses graph topology (not transform instances):

**Execution model context:** In the current DAG model, forked children have `start_step=coalesce_step` and the pre-loop coalesce check at `_process_single_token:1620` fires immediately (`step_completed=start_step=coalesce_at_step`). So forked children never process intermediate transforms — they go straight to `accept()`. This means in the current model, this warning should never fire for the "intermediate transform" scenario. However, the check remains valuable as:
1. A safety net if the execution model evolves
2. A validator for the pipeline topology itself (the fork gate and all transforms within its DAG scope that have DIVERT edges)

The algorithm walks the specific simple path from each fork gate to its coalesce (using `nx.shortest_path` on the `continue`-edges subgraph), not the entire descendant tree:

```python
def _warn_divert_coalesce_interactions(
    self,
    coalesce_settings: dict[str, CoalesceSettings],
) -> list[GraphValidationWarning]:
    """Check for DIVERT edges on paths between fork gates and require_all coalesces."""
    warnings: list[GraphValidationWarning] = []

    # 1. Find all transform node_ids that have outgoing DIVERT edges
    divert_transforms: set[str] = set()
    for edge_info in self.get_edges():
        if edge_info.default_mode == RoutingMode.DIVERT:
            node_info = self.get_node_info(edge_info.from_node_id)
            if node_info.node_type == "transform":
                divert_transforms.add(edge_info.from_node_id)

    if not divert_transforms:
        return warnings

    # 2. Build subgraph of only "continue" edges (the main pipeline spine)
    continue_edges = [
        (u, v) for u, v, d in self._graph.edges(data=True)
        if d.get("label") == "continue"
    ]
    spine = nx.DiGraph(continue_edges)

    # 3. For each require_all coalesce, find the fork gates feeding it
    #    and check for DIVERT transforms on the spine between them
    for coalesce_name, settings in coalesce_settings.items():
        if settings.policy != "require_all":
            continue

        coalesce_node_id = self._coalesce_id_map.get(CoalesceName(coalesce_name))
        if coalesce_node_id is None:
            continue

        # Find fork gates: predecessors of coalesce with branch labels
        # NOTE: self._graph is a MultiDiGraph (dag.py:99), so edges are keyed.
        # self._graph.edges[u, v] doesn't reliably return a single dict —
        # it returns a dict-of-dicts keyed by edge key. Iterate explicitly.
        fork_gate_ids: set[str] = set()
        for pred_id in self._graph.predecessors(coalesce_node_id):
            for u, v, edge_data in self._graph.edges(pred_id, data=True):
                if v == coalesce_node_id and edge_data.get("label") in settings.branches:
                    fork_gate_ids.add(pred_id)
                    break  # One matching edge is enough to identify this predecessor as a fork gate

        # For each fork gate, walk the continue-edge spine to coalesce
        for gate_id in fork_gate_ids:
            try:
                path = nx.shortest_path(spine, gate_id, coalesce_node_id)
            except nx.NetworkXNoPath:
                continue  # Gate not on spine to coalesce (different topology)

            # Check intermediate nodes (exclude gate and coalesce themselves)
            for node_id in path[1:-1]:
                if node_id in divert_transforms:
                    warnings.append(GraphValidationWarning(
                        code="DIVERT_COALESCE_REQUIRE_ALL",
                        message=(
                            f"Transform '{node_id}' between fork gate '{gate_id}' "
                            f"and coalesce '{coalesce_name}' has on_error routing to "
                            f"an error sink. If any row hits this error path, the "
                            f"downstream coalesce with require_all policy will lose "
                            f"a branch. Consider best_effort or quorum policy, "
                            f"or use on_error: discard."
                        ),
                        node_ids=(node_id, gate_id, coalesce_node_id),
                    ))

    return warnings
```

**Why `nx.shortest_path` on the spine, not `nx.descendants`:** `nx.descendants(gate)` returns ALL reachable nodes from the gate, including nodes on other branches and unrelated downstream paths. The spine subgraph (only `continue` edges) plus `nx.shortest_path` gives exactly the linear transform chain between the gate and the coalesce — no over-reporting.

Step 3: **Call from `from_plugin_instances()`** after all edges are built and coalesce nodes are wired (after line ~835), before returning the graph:

```python
# Emit warnings for dangerous divert+coalesce interactions
if coalesce_settings:
    divert_warnings = graph._warn_divert_coalesce_interactions(
        {cs.name: cs for cs in coalesce_settings}
    )
    for w in divert_warnings:
        slog.warning(
            "dag_validation_warning",
            code=w.code,
            message=w.message,
            node_ids=w.node_ids,
        )
```

**Why not modify `validate()`:** The `validate()` method (lines 199-268) returns `None` and focuses on structural graph correctness. It has 6+ call sites (CLI, orchestrator). Adding a return type would require updating all callers. The divert/coalesce interaction is a semantic concern (pipeline behavior), not a structural concern (graph shape). Keeping them separate is cleaner.

**Why graph topology works:** When `from_plugin_instances()` processes transforms, it creates `__error_N__` DIVERT edges for each transform with `on_error != "discard"` (dag.py:813-823). These edges persist in the graph even though `_on_error` is not stored in node_config. So the check identifies problematic transforms by their outgoing DIVERT edges.

**Tests:**
- Verify warning is emitted for require_all + DIVERT transform on spine between fork gate and coalesce
- Verify no warning for best_effort + on_error (valid combination)
- Verify no warning for on_error: discard (no DIVERT edge exists)
- Verify no warning for DIVERT transform outside the fork-to-coalesce spine (e.g., after coalesce)
- Verify source quarantine DIVERT edges don't trigger fork/coalesce warnings
- Verify `GraphValidationWarning` dataclass is exported from dag module
- Verify the algorithm uses spine (continue-edges) not full descendant tree (no over-reporting)
- **Note:** In the current execution model, forked children skip to coalesce_step immediately (pre-loop check at processor.py:1620). There are no intermediate transforms between fork and coalesce for forked tokens. The warning fires based on graph topology (transforms with DIVERT edges on the spine) as a safety net. If the execution model evolves to allow branch-specific transforms, this check becomes load-bearing.

**Commit separately.**

---

### Task 6: Coalesce branch-loss notification

Add `notify_branch_lost()` to `CoalesceExecutor` and wire it from the processor's error routing path.

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py` (new method)
- Modify: `src/elspeth/engine/processor.py` (call notify on error-routing forked tokens)
- Test: `tests/engine/test_coalesce_executor.py`, `tests/engine/test_audit_sweep.py`

**Implementation:**

**Critical semantic detail:** Error-routed tokens are diverted BEFORE reaching the coalesce point. They never call `accept()`. So the lost branch is NOT in `_PendingCoalesce.arrived` — it's a branch the coalesce is still *expecting* but will never receive. The notification reduces the effective expected count.

Step 1: **Add `lost_branches` field to `_PendingCoalesce`** (coalesce_executor.py:54-62):

```python
@dataclass
class _PendingCoalesce:
    """Tracks pending tokens for a single row_id at a coalesce point."""
    arrived: dict[str, TokenInfo]           # branch_name -> token
    arrival_times: dict[str, float]         # branch_name -> monotonic time
    first_arrival: float                    # For timeout calculation
    pending_state_ids: dict[str, str]       # branch_name -> state_id
    lost_branches: dict[str, str]           # NEW: branch_name -> loss reason
```

Initialize `lost_branches` as empty dict `{}` in `accept()` where `_PendingCoalesce` is constructed (line ~244).

Step 2: **Add `notify_branch_lost()` method** on CoalesceExecutor:

```python
def notify_branch_lost(
    self,
    coalesce_name: str,
    row_id: str,
    lost_branch: str,
    reason: str,
    step_in_pipeline: int,
) -> CoalesceOutcome | None:
    """Notify that a branch was error-routed and will never arrive.

    Called by the processor when a forked token is diverted to an error sink
    before reaching this coalesce point. Adjusts the expected branch count
    and re-evaluates merge conditions.

    Returns CoalesceOutcome if merge triggered, None if still waiting.
    """
    key = (coalesce_name, row_id)
    settings = self._settings[coalesce_name]

    # Case 1: No pending entry yet — this branch was lost before
    # ANY branch arrived. Create a minimal pending entry with the loss recorded.
    if key not in self._pending:
        self._pending[key] = _PendingCoalesce(
            arrived={},
            arrival_times={},
            first_arrival=self._clock.monotonic(),
            pending_state_ids={},
            lost_branches={lost_branch: reason},
        )
        # Cannot merge with no data — evaluate failure conditions
        return self._evaluate_after_loss(settings, key, step_in_pipeline)

    pending = self._pending[key]

    # Case 2: Already completed (race with normal merge) — ignore
    if key in self._completed_keys:
        return None

    # Case 3: Record the loss and re-evaluate
    pending.lost_branches[lost_branch] = reason
    return self._evaluate_after_loss(settings, key, step_in_pipeline)
```

Step 3: **Add `_evaluate_after_loss()` helper** to handle policy-specific consequences:

```python
def _evaluate_after_loss(
    self,
    settings: CoalesceSettings,
    key: tuple[str, str],
    step_in_pipeline: int,
) -> CoalesceOutcome | None:
    pending = self._pending[key]
    effective_expected = len(settings.branches) - len(pending.lost_branches)
    arrived_count = len(pending.arrived)

    if settings.policy == "require_all":
        # require_all: ANY lost branch = immediate failure
        # Fail all arrived branches and clean up
        return self._fail_pending(
            settings, key, step_in_pipeline,
            failure_reason=f"branch_lost:{','.join(pending.lost_branches.keys())}",
        )

    elif settings.policy == "quorum":
        # quorum: if max possible arrivals < quorum, fail
        max_possible = effective_expected  # branches that could still arrive
        if max_possible + arrived_count < settings.quorum_count:
            return self._fail_pending(
                settings, key, step_in_pipeline,
                failure_reason=f"quorum_impossible:need={settings.quorum_count},max_possible={max_possible + arrived_count}",
            )
        # Check if arrived count already meets quorum
        if arrived_count >= settings.quorum_count:
            return self._execute_merge(settings, self._node_ids[settings.name], pending, step_in_pipeline, key, settings.name)
        return None  # Still waiting

    elif settings.policy == "best_effort":
        # best_effort: if all remaining branches either arrived or lost, merge
        if arrived_count + len(pending.lost_branches) >= len(settings.branches):
            if arrived_count > 0:
                return self._execute_merge(settings, self._node_ids[settings.name], pending, step_in_pipeline, key, settings.name)
            return self._fail_pending(settings, key, step_in_pipeline, failure_reason="all_branches_lost")
        return None  # Still waiting for remaining branches

    elif settings.policy == "first":
        # first: should already have merged on first arrival
        # If no arrivals yet, nothing to merge
        return None

    return None
```

Step 4: **Add `_fail_pending()` helper** to handle failure cleanup (recording outcomes for arrived branches, cleaning up pending state). This mirrors the failure paths in `check_timeouts()` and `flush_pending()` — extract into a shared method to avoid duplication.

Step 5: **Update `_execute_merge()` audit metadata** (coalesce_executor.py:487-502) to include lost branch information:

```python
coalesce_metadata = {
    "policy": settings.policy,
    "merge_strategy": settings.merge,
    "expected_branches": settings.branches,
    "branches_arrived": list(pending.arrived.keys()),
    "branches_lost": pending.lost_branches,  # NEW: {branch: reason}
    "arrival_order": ...,
    "wait_duration_ms": ...,
}
```

Step 6: **Processor wiring.** In the processor's error-routing path inside `_process_single_token()` (around line 1797-1809), for forked tokens (where `branch_name is not None`), BEFORE the error-routing return statement:

**Return type context:** `_process_single_token()` returns `tuple[RowResult | list[RowResult] | None, list[_WorkItem]]`. It can return a list of RowResults, which callers (`process_row()`, `process_existing_row()`) handle by extending their results list.

```python
# BEFORE the error-routing return statement (processor.py:1801-1809):
notification_results: list[RowResult] = []

if current_token.branch_name is not None and self._coalesce_executor is not None:
    coalesce_name = self._branch_to_coalesce.get(BranchName(current_token.branch_name))
    if coalesce_name is not None:
        coalesce_step = self._coalesce_step_map[coalesce_name]
        outcome = self._coalesce_executor.notify_branch_lost(
            coalesce_name=coalesce_name,
            row_id=current_token.row_id,
            lost_branch=current_token.branch_name,
            reason=str(error_details),
            step_in_pipeline=coalesce_step,
        )
        if outcome is not None:
            if outcome.merged_token is not None:
                # Merge triggered — resume merged token at coalesce_step
                # (same as _maybe_coalesce_token at processor.py:1555)
                child_items.append(_WorkItem(
                    token=outcome.merged_token,
                    start_step=coalesce_step,
                    coalesce_at_step=None,
                    coalesce_name=None,
                ))
            elif outcome.failure_reason:
                # Merge failed — build RowResults for ALL consumed (held sibling) tokens.
                # DB outcomes are already recorded by the executor (outcomes_recorded=True).
                # These RowResults propagate to the orchestrator for counter accounting.
                #
                # NOTE: consumed_tokens are the HELD SIBLINGS, not the current token.
                # The current token is being error-routed (ROUTED outcome below).
                # The siblings were held via accept() and have no other path
                # to produce RowResults — without these, they vanish from counters.
                for consumed_token in outcome.consumed_tokens:
                    self._emit_token_completed(consumed_token, RowOutcome.FAILED)
                    notification_results.append(RowResult(
                        token=consumed_token,
                        final_data=consumed_token.row_data,
                        outcome=RowOutcome.FAILED,
                        error=FailureInfo(
                            exception_type="CoalesceFailure",
                            message=outcome.failure_reason,
                        ),
                    ))

# THEN the normal error-routing return:
current_result = RowResult(
    token=current_token,
    final_data=current_token.row_data,
    outcome=RowOutcome.ROUTED,
    sink_name=error_sink,
)
if notification_results:
    # Return list: current token's ROUTED result + sibling FAILED results
    return ([current_result] + notification_results, child_items)
return (current_result, child_items)
```

**Why RowResults for consumed_tokens:** When tokens are held by `accept()`, `_process_single_token()` returns `None` (no RowResult). The held tokens are "in limbo" — not counted by the orchestrator. They're only counted when the coalesce completes (merge or failure). For timeouts, `handle_coalesce_timeouts()` directly increments `counters.rows_coalesce_failed`. But for notification-triggered failures inside the processor, the only propagation path to the orchestrator is via RowResults. Each consumed_token needs its own RowResult so `accumulate_row_outcomes()` can count it.

**Processor lookups available:** `self._branch_to_coalesce: dict[BranchName, CoalesceName]` (line 123) and `self._coalesce_step_map: dict[CoalesceName, int]` — both populated from DAG construction.

**Threading/ordering:** CoalesceExecutor is single-threaded (called from processor's synchronous work queue loop). The processor processes one work item at a time. When processing a forked row, the fork creates child work items that are processed sequentially. If branch_b errors and notifies, and branch_a is already at the coalesce (held), the notification triggers immediate merge/failure. No concurrency within a single row's processing. Document this assumption in the CoalesceExecutor class docstring.

**Work queue integration:** `notify_branch_lost()` returns `CoalesceOutcome | None` — the same type as `accept()`. The processor's `_maybe_coalesce_token()` (lines 1513-1588) already handles `CoalesceOutcome` with `held`, `merged_token`, and `failure_reason` fields. The notification path uses the same return type and the processor handles it the same way.

**Tests:**
- Verify `notify_branch_lost()` records the lost branch in `_PendingCoalesce.lost_branches`
- Verify `require_all` + lost branch = immediate failure (arrived branches get FAILED outcomes)
- Verify `best_effort` + fork(a,b), a arrives, b lost → immediate merge with just a's data
- Verify `best_effort` + fork(a,b), b lost first, a arrives later → merge triggered by accept(), not notification
- Verify `quorum` + fork(a,b,c), quorum=2, one lost → still waits for remaining two; merge when second arrives
- Verify `quorum` + fork(a,b,c), quorum=2, two lost → immediate failure (quorum impossible)
- Verify the "true idle" scenario: fork(a,b), b error-routed → notification triggers merge for a immediately (no timeout wait)
- Verify branch lost BEFORE any branch arrives creates pending entry with loss recorded
- Verify merge audit metadata includes `branches_lost` with loss reasons
- Verify notification returns `CoalesceOutcome` that processor adds to work queue
- Verify merged token's work item uses `start_step=coalesce_step` (NOT +1, matching processor.py:1555)
- Verify failure outcome produces RowResult with FAILED + counter tracking (not silently dropped)
- Verify `outcomes_recorded` flag prevents double-recording of token outcomes
- Verify `_fail_pending()` reuses logic from `check_timeouts()`/`flush_pending()` (no duplication)
- Regression: normal fork/coalesce without errors still works (lost_branches empty)

**Commit separately.**

---

### Task 7: MCP explain_token DIVERT annotation

Add DIVERT awareness to the `explain_token()` lineage response.

**Files:**
- Modify: `src/elspeth/core/landscape/lineage.py` (lineage builder)
- Modify: `src/elspeth/mcp/server.py` (response formatting)
- Test: `tests/mcp/test_mcp_divert.py`

**Implementation:**

The `explain_token()` MCP tool calls `explain()` in `lineage.py`, which returns a `LineageResult` dataclass:

```python
@dataclass
class LineageResult:
    token: Token
    source_row: RowLineage
    node_states: list[NodeState]
    routing_events: list[RoutingEvent]    # Already contains mode field
    calls: list[Call]
    parent_tokens: list[Token]
    validation_errors: list[ValidationErrorRecord]
    transform_errors: list[TransformErrorRecord]
    outcome: TokenOutcome | None
```

The MCP handler (server.py:448-469) converts this to a dict via `_dataclass_to_dict()` (formatters.py:51-91), which converts `RoutingMode` enum → `.value` string. So routing_events already appear with `"mode": "divert"` in the response — no change needed for the raw mode field.

Step 1: **Add `flow_type` to routing_events in the MCP response.** Rather than modifying the `RoutingEvent` dataclass (which is a Tier 1 audit contract), compute `flow_type` during response formatting in the MCP handler:

```python
# In server.py explain_token handler, after _dataclass_to_dict()
result_dict = cast(dict[str, Any], _dataclass_to_dict(result))

# Annotate routing_events with flow_type
for event in result_dict.get("routing_events", []):
    event["flow_type"] = "divert" if event.get("mode") == "divert" else "normal"
```

This keeps the audit dataclass clean while giving MCP consumers a convenience field.

Step 2: **Add `divert_summary` to the top-level response** when the token was diverted:

```python
# After building result_dict
divert_events = [
    e for e in result_dict.get("routing_events", [])
    if e.get("mode") == "divert"
]

if divert_events:
    # Find the edge that diverted this token (lookup from edges table)
    divert_event = divert_events[-1]  # Last divert event is the terminal one
    edge = self._recorder.get_edge(divert_event["edge_id"])

    result_dict["divert_summary"] = {
        "diverted": True,
        "divert_type": "quarantine" if "__quarantine__" in edge.label else "error",
        "from_node": edge.from_node_id,
        "to_sink": edge.to_node_id,
        "edge_label": edge.label,
        "reason_hash": divert_event.get("reason_hash"),
    }
else:
    result_dict["divert_summary"] = None
```

Step 3: **Ensure `get_edge()` exists on recorder.** The recorder's `get_edges()` returns all edges for a run, but looking up a single edge by ID may need a simple query helper. If it doesn't exist, add:

```python
def get_edge(self, edge_id: str) -> Edge:
    """Retrieve a single edge by ID. Tier 1: crash on missing."""
    ...
```

Or use the existing `get_edges()` with a filter, though a direct lookup is more efficient.

**Tests:**
- Verify quarantined token lineage includes `divert_summary` with `divert_type: "quarantine"`
- Verify error-routed token lineage includes `divert_summary` with `divert_type: "error"`
- Verify normal completed token has `divert_summary: null`
- Verify routing_events in lineage response include `flow_type` annotation ("divert" or "normal")
- Verify `divert_summary.from_node` and `to_sink` reference correct node IDs
- Verify `divert_summary.edge_label` is the canonical label (e.g., `"__quarantine__"` or `"__error_2__"`)

**Commit separately.**

---

## Risk Assessment

| Risk | Likelihood | Mitigation | Status |
|------|-----------|------------|--------|
| Source node_states add DB writes in hot loop | Medium | Pre-existing pattern (same as all node_states). Profile before/after. batch_context optimization tracked separately | Active |
| notify_branch_lost triggers merge mid-processing | Medium | CoalesceExecutor is single-threaded (processor's synchronous loop). Merge produces work queue items via existing pattern (same as normal coalesce accept). Add test for merge-on-notification producing correct child_items | Active |
| Mermaid syntax for dashed arrows | Low | `-.->` is standard Mermaid syntax. Test with Mermaid renderer | Active |
| notify_branch_lost race with normal accept | Low | Single-threaded — no concurrency within a single row's processing. Document thread-safety assumption in CoalesceExecutor docstring | Active |
| Retry-exhaustion routing_event gap | Medium | When all retries fail, RetryManager's final-failure path may also need routing_event recording. Not addressed in Task 1 — requires separate analysis of RetryManager's exhaustion handling | Future |
| Token creation refactor breaks processor | ~~Medium~~ | **ELIMINATED.** Task 3 revised to create source states processor-internally. No interface change to `process_row()` | Eliminated |
| edge_map missing DIVERT edges | ~~Low~~ | **ELIMINATED.** Verified: no filtering at any stage. DIVERT edges present in edge_map | Eliminated |
| step_index shift when source gets step 0 | ~~Medium~~ | **ELIMINATED.** Verified: transforms already use step_index=1+ (`step = start_step + step_offset + 1`). No code compares to 0. No shift occurs | Eliminated |
| Resume creates duplicate source node_states | ~~Low~~ | **ELIMINATED.** Verified: resume creates new tokens with new token_ids. UNIQUE constraint keyed on token_id — no violations | Eliminated |

## Implementation Order

```
Phase 1 (no dependencies):
  Task 1: Transform error routing_events
  Task 2: Mermaid DIVERT styling
  (These can be done in parallel)

Phase 2 (sequential):
  Task 3: Per-row source node_states  ← largest change
  Task 4: Quarantine routing_events   ← depends on Task 3

Phase 3 (after Phase 1+2):
  Task 5: Fork/coalesce validation warning  ← independent
  Task 6: Coalesce branch-loss notification ← depends on Task 1 pattern
  Task 7: MCP explain_token DIVERT          ← benefits from Tasks 1+4
  (Tasks 5-7 can be done in parallel after their dependencies)
```

## Review Panel Findings

This plan was reviewed by a 4-perspective panel (Architecture, Python Engineering, QA, Systems Thinking). Key outcomes:

### Findings that changed the plan

1. **state_id accessibility gap (Architecture review):** `execute_transform()` returns `(TransformResult, TokenInfo, error_sink)` — no `state_id`. The processor cannot record routing_events. **Resolution:** Adopted Option C — record routing_events inside the TransformExecutor (following GateExecutor pattern), keeping audit lifecycle co-located with node_state lifecycle. Task 1 updated.

2. **Interface pollution concern (Python review) + hidden coupling (Systems review):** Moving token creation to orchestrator and adding `token` param to `process_row()` splits responsibilities and creates ordering invariants. **Resolution:** Task 3 revised to create source states processor-internally (valid rows) and orchestrator-internally (quarantine rows). No interface change needed.

3. **step_index "schema-breaking change" (Systems review):** Flagged as critical risk. **Resolution:** Verification proved transforms already use step_index=1+ (`step = start_step + step_offset + 1`). No code assumes step_index=0 means "first transform". No shift occurs. Risk eliminated.

### Findings incorporated as test requirements

4. **Audit trail completeness invariant (QA review):** Add test: "every root token (parent_token_id IS NULL) has exactly one node_state with step_index=0." Fork/expand child tokens are excluded — they are created mid-pipeline and trace lineage via parent_token_id. Added to Task 3 tests.

5. **Resume/checkpoint safety (Architecture + QA review):** Verify resumed rows don't create duplicate source node_states. **Verified safe:** resume creates new token_ids, so no UNIQUE constraint violations. Added as regression test in Task 3.

6. **Fork/coalesce error interactions (QA review):** Add tests for require_all + branch error, best_effort + all branches error, quorum + branch error. Added to Task 6 tests.

7. **notify_branch_lost must produce work queue items (Architecture review):** When notification triggers merge, the resulting merged token must enter the processor's work queue (same pattern as normal coalesce accept). Clarified in Task 6.

### Findings noted as future improvements

8. **DatabaseOps batch_context (Python review):** Connection reuse would benefit ALL recorder operations, not just source states. Tracked as separate optimization — pre-existing performance characteristic.

9. **Error edge label as shared constant (Python review):** `f"__error_{seq}__"` magic string extracted to helper in Task 1. Done.

10. **CoalesceExecutor thread-safety documentation (Python review):** Add docstring noting single-threaded assumption. Incorporated in Task 6.

## Post-Review Findings (Second Review Pass)

A second review pass identified 5 additional issues. All have been addressed:

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| 1 | High | Resume path (`process_existing_row()`) not covered for source node_states | Added as implementation path 3 in Task 3 |
| 2 | High | "Every token has step_index=0" invariant invalid for fork/expand child tokens | Scoped invariant to root tokens (`parent_token_id IS NULL`). Child tokens trace lineage via parent_token_id |
| 3 | High | Retry-disabled exception path in processor (lines 1220-1277) bypasses executor routing_event recording | Added Step 4 to Task 1: record routing_event in processor catch blocks using `ctx.state_id` |
| 4 | Medium | Task 5 underspecified — `validate()` is exception-based, no warning channel, `_on_error` not in node_config | Redesigned: new `_warn_divert_coalesce_interactions()` method uses DIVERT edges from graph topology; called from `from_plugin_instances()` not `validate()` |
| 5 | Medium | `tests/mcp/test_server.py` doesn't exist | Corrected to `tests/mcp/test_mcp_divert.py` (new file) |

## Post-Review Findings (Third Review Pass)

A third review pass identified 4 correctness issues. All have been addressed:

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| 1 | High | Task 6 `start_step=coalesce_step + 1` off-by-one — existing flow uses `coalesce_step` (processor.py:1555) | Fixed to `start_step=coalesce_step` |
| 2 | High | Task 6 failure outcomes dropped — no RowResult/counter integration for coalesce failures from notification | Added full RowResult handling for failure path (matching `_maybe_coalesce_token:1560-1586` pattern) |
| 3 | Medium | Task 4 quarantine edge lookup silently skips missing edge — should crash for non-discard flows | Changed to `OrchestrationInvariantError` crash. Quarantine rows reaching orchestrator MUST have a `__quarantine__` edge (Tier 1 rules) |
| 4 | Medium | Task 5 `nx.descendants()` walks all descendants, not branch-bounded — over-reports DIVERT transforms outside the specific fork-to-coalesce corridor | Replaced with `nx.shortest_path()` on continue-edge spine subgraph. Also noted that current execution model skips intermediate transforms (forked children go straight to coalesce) |

## Post-Review Findings (Fourth Review Pass)

A fourth review pass identified 4 issues (2 high, 2 medium). All have been addressed:

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| 1 | High | Task 6 Step 6 uses `results.append()` but `_process_single_token()` has no results accumulator — it returns `tuple[RowResult \| list[RowResult] \| None, list[_WorkItem]]` | Rewrote Step 6 processor wiring: uses `notification_results: list[RowResult]` and returns `([current_result] + notification_results, child_items)` when notification produces failures |
| 2 | High | Task 6 failure handling only emits RowResult for current_token — `outcome.consumed_tokens` (held sibling tokens) have no RowResult path to the orchestrator for counter accounting | Added explicit iteration over `outcome.consumed_tokens` with individual RowResult per held sibling (FAILED outcome, CoalesceFailure error) |
| 3 | Medium | Task 6 `notify_branch_lost()` Case 1 uses `time.monotonic()` — CoalesceExecutor uses injected `self._clock` throughout (lines 205, 322, 613, 664, 707, 810, 861) | Fixed to `self._clock.monotonic()` |
| 4 | Medium | Task 5 `self._graph.edges[pred_id, coalesce_node_id]` doesn't work for MultiDiGraph (keyed multiedges) — returns dict-of-dicts, not single edge dict | Replaced with explicit iteration: `for u, v, edge_data in self._graph.edges(pred_id, data=True): if v == coalesce_node_id` |

## Pre-Implementation Verification Results

| Investigation | Result | Impact |
|--------------|--------|--------|
| Transforms use step_index=1+ | **Confirmed.** `step = start_step + step_offset + 1`. No hardcoded `step_index == 0` comparisons anywhere | Eliminated step_index shift risk |
| state_id accessible to processor | **Gap confirmed.** `execute_transform()` doesn't return state_id. `PluginContext.state_id` is set but ctx not returned | Changed Task 1 to executor-internal recording (Option C) |
| edge_map contains DIVERT edges | **Confirmed.** No filtering at any stage. Both `__quarantine__` and `__error_N__` keys present | No changes needed for Tasks 1/4 |
| Resume creates new token_ids | **Confirmed.** `create_token_for_existing_row()` generates fresh token_id. UNIQUE constraint on `(token_id, node_id, attempt)` | Eliminated resume duplication risk |
| Task 3a feasible (no interface change) | **Confirmed.** Processor has `run_id`, `source_node_id`, and token_id after `create_initial_token()`. Source state created before transform loop | Eliminated interface change risk |

## Verification Checklist (run after all tasks)

1. `.venv/bin/python -m pytest tests/ --timeout=120` — full test suite
2. `.venv/bin/python -m mypy src/` — type checking
3. `.venv/bin/python -m ruff check src/` — linting
4. `.venv/bin/python -m scripts.check_contracts` — config contracts alignment
5. Manual: run example pipeline with quarantine + error sinks, verify `routing_events` table has DIVERT entries
6. Manual: run MCP server, call `get_dag_structure()`, verify dashed edges in Mermaid output
7. Manual: run MCP server, call `explain_token()` on quarantined row, verify `divert_summary` present
