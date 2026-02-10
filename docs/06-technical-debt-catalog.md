# Phase 2 Technical Debt Catalog: Node-ID DAG Traversal Migration

**Scope:** Phase 2 commits on `explicit-sink-routing` branch (12 commits after `48c3c583`).
**Focus:** Dual-representation debt, translation-layer debt, preserved-API debt, dead code, abstraction debt.
**Date:** 2026-02-09

---

## Critical Priority (Immediate)

### DEBT-01: Positional Terminality in DAG Construction (5 locations)

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:134-144` (`_validate_on_success_routing`)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:198-205` (`_validate_aggregation_on_success_routing`)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:992-1003` (gate continue route terminal check)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:1075-1087` (coalesce terminal check)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:955` (`pipeline_index` local dict construction)

**Impact:** DAG construction uses positional indexing (`step + 1 == len(pipeline_nodes)`) to determine whether a node is terminal. This is Phase 1 thinking baked into Phase 2 code. The docstring at line 103-113 explicitly acknowledges this is a debt: "If DAG construction is ever extended to support non-linear topologies [...] this positional check MUST be replaced with a structural graph query." Phase 2 introduced the graph structure that makes structural terminality possible, but the code still uses positional checks.

**Effort:** M (2-3 days)

**Category:** Architecture

**Severity:** SHOULD_FIX

**Details:** The clean version would use `graph.get_next_node(node_id) is None` or equivalent structural query (no outgoing `continue`/MOVE edge to a non-sink node) instead of `step + 1 == len(pipeline_nodes)`. This works today because `from_plugin_instances()` only builds linear chains, but the abstraction leak means any future non-linear DAG extension will silently misclassify terminal nodes. The `pipeline_index` dict at line 955 is constructed solely to support these positional checks.

---

### DEBT-02: Sink Write Step Computed from Transform/Gate Count, Not Graph

**Evidence:** `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:282`

```python
step = len(config.transforms) + len(config.gates) + 1
```

**Impact:** `_write_pending_to_sinks()` computes the sink step number by counting transforms and gates and adding 1. This is a Phase 1 formula that happens to produce the right number for linear pipelines. In Phase 2, the step should come from the graph's `node_step_map` for the specific sink node. If the pipeline has coalesce nodes (which are in the step map but not in `config.transforms` or `config.gates`), this formula produces the wrong step number for sinks.

**Effort:** S (1 day)

**Category:** Architecture

**Severity:** MUST_FIX

**Details:** The step number is written to `node_states.step_index` in the audit trail via `SinkExecutor.write()`. Wrong step numbers corrupt the audit record. The fix: look up the sink node's step from the graph's step map (already available via `graph.build_step_map()` or `traversal.node_step_map`). The step map includes sink nodes (they are in the topological order). Pass the per-sink step to `sink_executor.write()` instead of a single flat `step` for all sinks.

---

### DEBT-03: `flush_aggregation_timeout` Accepts `step_in_pipeline: int` (Dead Method)

**Evidence:** `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:489-519`

**Impact:** The method `flush_aggregation_timeout()` accepts a `step_in_pipeline: int` parameter and forwards it to `execute_flush()`. However, grep shows NO callers of this method anywhere in the codebase. The orchestrator's aggregation module (`aggregation.py`) uses `handle_timeout_flush()` instead (line 210, 339), which internally resolves the step from the node ID. This method is dead code with a Phase 1 interface.

**Effort:** S (delete the method)

**Category:** Dead Code

**Severity:** SHOULD_FIX

**Details:** `handle_timeout_flush()` (line 521) is the replacement. It takes `node_id` and internally calls `self._resolve_audit_step_for_node(node_id)` to derive the step. `flush_aggregation_timeout()` should be deleted entirely.

---

## High Priority (Next Quarter)

### DEBT-04: `_transform_id_map` and `get_inverse_transform_id_map()` -- Phase 1 Index-Based Mapping

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:246` (`_transform_id_map: dict[int, NodeID]`)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:534-536` (`get_inverse_transform_id_map`)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:1145-1151` (`get_transform_id_map`)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:918` (usage in `_execute_run`)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:1069` (usage in resume)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:1847` (usage in resume)

**Impact:** The `_transform_id_map` maps transform *list position* (0, 1, 2...) to NodeID. This is a Phase 1 artifact -- the transform's position in the `transforms` list was its identity. In Phase 2, transforms have deterministic node IDs. The map is still used by the orchestrator to assign `node_id` to plugin instances via `_assign_plugin_node_ids()` (line 406-455) and to build `node_to_plugin` mappings (line 933-939).

**Effort:** M (2-3 days)

**Category:** Architecture (Translation Layer)

**Severity:** SHOULD_FIX

**Details:** The clean version would assign node IDs to transforms during `from_plugin_instances()` (the graph already knows the mapping) and store them directly on the plugin instances. The orchestrator would then use `transform.node_id` directly instead of looking up by sequence position. `get_inverse_transform_id_map()` -- which maps NodeID back to list index -- has zero callers in production code (only used internally in the graph). It is a pure Phase 1 translation method.

---

### DEBT-05: `_coalesce_gate_index` Maps Coalesce to Gate's Pipeline Position

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:253` (`_coalesce_gate_index: dict[CoalesceName, int]`)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:956-979` (computation)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:1186-1196` (`get_coalesce_gate_index`)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:489-491` (consumption)

**Impact:** This map stores the *pipeline list index* of the gate that produces each coalesce's branches. It is used for two things: (1) positional terminality checks in `from_plugin_instances()` (DEBT-01), and (2) assigning a step number to coalesce nodes in `_build_dag_traversal_context()` (line 491: `coalesce_gate_index[coalesce_name] + 1`). Both uses are positional -- they treat the DAG as a flat list.

**Effort:** M (2-3 days -- coupled with DEBT-01)

**Category:** Architecture (Dual Representation)

**Severity:** SHOULD_FIX

**Details:** Coalesce nodes are added to the DAG graph. Their step number should come from `build_step_map()` directly (counting their topological position), not from "gate_index + 1". The `_coalesce_gate_index` would be unnecessary if terminality checks used structural queries and coalesce step assignment used graph topology.

---

### DEBT-06: `_bind_runtime_transforms` -- Test Escape Hatch That Builds Phase 1 Structures

**Evidence:** `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:202-224`

**Impact:** `_bind_runtime_transforms()` is called at lines 1402, 1466, 1493 (every entry point: `process_row`, `process_existing_row`, `process_token`). It exists to handle tests that provide transforms without a fully-constructed `DAGTraversalContext`. It manually builds `_node_step_map`, `_node_to_plugin`, `_node_to_next`, and `_first_transform_node_id` by iterating over the transforms list using positional indexing.

**Effort:** M (2-3 days)

**Category:** Architecture (Preserved API / Test Coupling)

**Severity:** SHOULD_FIX

**Details:** This method violates CLAUDE.md's "Test Path Integrity" principle: "Never bypass production code paths in tests." Tests calling the processor with ad-hoc transforms bypass `ExecutionGraph.from_plugin_instances()` and get a synthetic traversal context that might not match production behavior. The fix: all tests that exercise `RowProcessor` should provide a complete `DAGTraversalContext` built from a real `ExecutionGraph`. The `_bind_runtime_transforms()` fallback should be deleted. The `getattr(transform, "node_id", None)` on line 209 is a defensive programming violation per CLAUDE.md rules.

---

### DEBT-07: `resolve_node_step` Public Method Leaks Step Abstraction

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:246-250` (definition)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/outcomes.py:131` (caller)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/outcomes.py:188` (caller)

**Impact:** `resolve_node_step()` is a public method that translates NodeID to step number. It is called by the outcomes module to provide `step_in_pipeline` to the `CoalesceExecutor`. The entire purpose of this method is step-number translation -- an audit-recording concern leaked into the processor's public API and consumed by the orchestrator.

**Effort:** S (1 day)

**Category:** Architecture (Translation Layer)

**Severity:** SHOULD_FIX

**Details:** The clean design: the `CoalesceExecutor` should receive the step map directly (or be given a callback that resolves steps). The processor should not expose step-number translation as a public method. Currently `outcomes.py` reaches into the processor to get step numbers for the coalesce executor -- this couples orchestrator outcome handling to the processor's internal step representation.

---

### DEBT-08: `node_step_map` Stored Both in `DAGTraversalContext` AND Copied to `RowProcessor._node_step_map`

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:57-58` (in `DAGTraversalContext`)
- `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:157` (`self._node_step_map = dict(traversal.node_step_map)`)
- `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:156` (`self._traversal = traversal`)

**Impact:** The processor stores the `DAGTraversalContext` as `self._traversal` AND copies `traversal.node_step_map` into `self._node_step_map`. It also copies `node_to_plugin`, `first_transform_node_id`, `node_to_next`, and `coalesce_node_map` individually. The `DAGTraversalContext` object is stored but never read again after the constructor. This is dual storage of the same data.

**Effort:** S (1 day)

**Category:** Code Quality (Dual Representation)

**Severity:** COSMETIC

**Details:** Either (a) the processor should use `self._traversal.node_step_map` directly and not copy fields, or (b) it should not store `self._traversal` at all. Currently it does both, which means changes to one are not reflected in the other (though in practice neither is mutated post-construction except by `_bind_runtime_transforms`, which mutates the copies).

---

### DEBT-09: `DAGTraversalContext.node_step_map` Exists Solely for Audit Step Numbers

**Evidence:** `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:55-63`

**Impact:** Of the 5 fields in `DAGTraversalContext`, `node_step_map` exists solely to provide step numbers for audit recording. The other 4 fields (`node_to_plugin`, `first_transform_node_id`, `node_to_next`, `coalesce_node_map`) are traversal concerns. Bundling audit step numbers into a "traversal context" is an abstraction mismatch -- step numbers are not traversal data, they are audit metadata.

**Effort:** S (1 day)

**Category:** Architecture (Abstraction Debt)

**Severity:** COSMETIC

**Details:** The clean version would separate concerns: a `DAGTraversalContext` for traversal (node_to_plugin, node_to_next, first_node, coalesce_map) and a separate `AuditStepMap` or similar for step number resolution. This separation would make it clear that step numbers are purely for recording, not for routing decisions.

---

### DEBT-10: `_resolve_audit_step_for_node` and `resolve_node_step` Are Nearly Identical

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:246-250` (`resolve_node_step` -- public)
- `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:262-268` (`_resolve_audit_step_for_node` -- private)

**Impact:** Both methods look up `self._node_step_map[node_id]`. The private method has an extra fallback for source_node_id (returning 0). Two methods doing essentially the same lookup creates confusion about which to use and why.

**Effort:** S (merge into one)

**Category:** Code Quality

**Severity:** COSMETIC

**Details:** Consolidate into one method. The source fallback (returning 0) is always needed because the source is step 0 in the audit trail. The public method `resolve_node_step` should handle both cases.

---

### DEBT-11: `step_in_pipeline` Pervasive in Executor Interfaces

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/engine/executors.py:194,557,767,1211,2005` (5 executor methods accept `step_in_pipeline: int`)
- `/home/john/elspeth-rapid/src/elspeth/engine/coalesce_executor.py:173,321,390,688,891` (5 coalesce methods accept it)
- `/home/john/elspeth-rapid/src/elspeth/engine/tokens.py:208,262,314` (3 token methods accept it)
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py:170,259,315` (3 recording methods)

**Impact:** The `step_in_pipeline: int` parameter flows through ~16+ method signatures across 5 files. Every executor, the token manager, and the landscape recorder accept step numbers. This parameter is used exclusively for writing `step_index` to `node_states` and `tokens` tables. The step number is always derived from `_resolve_audit_step_for_node(node_id)` in the processor, then passed down the call stack.

**Effort:** L (5+ days, touches many interfaces)

**Category:** Architecture (Pervasive Translation)

**Severity:** SHOULD_FIX

**Details:** In the clean design, executors would resolve their own step numbers from a step map (or a callback), eliminating the need to thread `step_in_pipeline` through every call. Alternatively, the landscape recorder's `begin_node_state()` could accept a `NodeID` and resolve the step internally from a step map set during run initialization. This would eliminate 16+ parameters across the call stack. However, this is a large refactor touching foundational interfaces -- plan carefully.

---

### DEBT-12: `_node_step_map` Updated by `_bind_runtime_transforms` Using Positional Indexing

**Evidence:** `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:222`

```python
self._node_step_map.setdefault(node_id, idx + 1)
```

**Impact:** When `_bind_runtime_transforms` fills in missing traversal data for tests, it assigns step numbers using the transform's position in the list (idx + 1). This is Phase 1 semantics -- step == list position. In Phase 2, step numbers are computed by `build_step_map()` from DAG topology. If any test relies on `_bind_runtime_transforms`, its step numbers may diverge from production.

**Effort:** S (coupled with DEBT-06 deletion)

**Category:** Code Quality

**Severity:** SHOULD_FIX

---

## Medium Priority

### DEBT-13: `_pipeline_nodes` Stored as Flat List -- Encodes Linear Chain Assumption

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:254` (field)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:505-519` (`get_pipeline_node_sequence`)
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:1131` (populated)

**Impact:** The `_pipeline_nodes` field is a flat ordered list of processing node IDs. It represents the linear chain of transforms/aggregations/gates. Phase 2 introduces DAG traversal via `node_to_next`, but `_pipeline_nodes` persists as a parallel representation of the same ordering. It is consumed by: (1) `build_step_map()` to assign step numbers, (2) `get_pipeline_node_sequence()` for external queries, (3) positional terminality checks (DEBT-01).

**Effort:** S (1 day)

**Category:** Architecture (Dual Representation)

**Severity:** COSMETIC

**Details:** For linear pipelines, `_pipeline_nodes` is equivalent to following `get_next_node()` from the source. The `get_pipeline_node_sequence()` method already has a fallback that does exactly this (lines 510-519). The cached `_pipeline_nodes` is optimization, but it encodes the assumption that the pipeline is a linear chain. Once DEBT-01 is resolved (structural terminality), the cached list may become the only consumer of this field.

---

### DEBT-14: `getattr(transform, "node_id", None)` Defensive Access in `_bind_runtime_transforms`

**Evidence:** `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:209`

**Impact:** This violates CLAUDE.md's prohibition on defensive programming patterns. `TransformProtocol` defines `node_id: str | None` -- all transforms have this attribute. Using `getattr` with a default hides bugs where a non-conforming object is passed.

**Effort:** S (1-line fix)

**Category:** Code Quality

**Severity:** SHOULD_FIX

---

### DEBT-15: `config_gates` Parameter in `handle_coalesce_timeouts` and `flush_coalesce_pending`

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/outcomes.py:103` (`config_gates: Sequence[object]`)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/outcomes.py:163` (`config_gates: Sequence[object]`)

**Impact:** Both functions accept `config_gates` but never use it. The docstring at line 123 says "retained for interface compatibility." Per CLAUDE.md's no-legacy-code policy, unused parameters retained for compatibility are forbidden debt. There are no users -- this is pre-release code.

**Effort:** S (delete the parameter from both functions and callers)

**Category:** Code Quality (Preserved API)

**Severity:** SHOULD_FIX

---

## Low Priority

### DEBT-16: `get_transform_id_map` Returns `dict[int, NodeID]` -- Phase 1 Signature

**Evidence:** `/home/john/elspeth-rapid/src/elspeth/core/dag.py:1145-1151`

**Impact:** The return type `dict[int, NodeID]` maps sequence position to NodeID. This is purely a Phase 1 artifact. In Phase 2, transforms are identified by NodeID, not by sequence position. The method is used by the orchestrator's `_assign_plugin_node_ids()` to set `node_id` on transforms by their list index.

**Effort:** S (coupled with DEBT-04)

**Category:** Architecture (Translation Layer)

**Severity:** COSMETIC

---

### DEBT-17: `_route_label_map` and `_route_resolution_map` Could Be Derived from Graph Edges

**Evidence:**
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:251-252`
- `/home/john/elspeth-rapid/src/elspeth/core/dag.py:744-756` (population)

**Impact:** These maps are populated during `from_plugin_instances()` and cached on the graph. They duplicate information already encoded in the graph's edges (a route from gate G with label L to sink S is stored as an edge AND in `_route_label_map`). This is optimization (O(1) lookup vs edge scan), not debt per se, but it is dual representation.

**Effort:** S

**Category:** Code Quality

**Severity:** COSMETIC

---

## Pending Analysis

The following areas were identified but not fully analyzed due to scope:

- **Checkpoint/resume path**: How checkpoint data stores step numbers vs node IDs. Checkpoint format may embed Phase 1 assumptions.
- **MCP server**: `/home/john/elspeth-rapid/src/elspeth/mcp/server.py` and `/home/john/elspeth-rapid/src/elspeth/mcp/types.py` expose `step_in_pipeline` in query results. This is read-only and reflects what the audit trail stores, so it is downstream of the core debt.
- **Landscape schema**: `node_states.step_index` column stores integer step numbers. This is the ultimate consumer of all the step-number machinery. Changing it to store `node_id` directly would eliminate most of the translation layer, but it is a schema migration.

---

## Limitations

This catalog analyzes **17 items** across the Phase 2 implementation.

**Scope covered:**
- `src/elspeth/core/dag.py` (full)
- `src/elspeth/engine/processor.py` (full)
- `src/elspeth/engine/orchestrator/core.py` (full)
- `src/elspeth/engine/orchestrator/aggregation.py` (full)
- `src/elspeth/engine/orchestrator/outcomes.py` (full)
- `src/elspeth/engine/coalesce_executor.py` (partial -- step_in_pipeline interface)
- `src/elspeth/engine/executors.py` (partial -- step_in_pipeline interface)
- `src/elspeth/engine/tokens.py` (step_in_pipeline interface only)
- `src/elspeth/contracts/types.py` (full)
- `src/elspeth/engine/orchestrator/types.py` (full)

**Not included:**
- Tests -- step-number assumptions in test assertions
- TUI / CLI -- `elspeth explain` uses step numbers for display
- Alembic migrations -- schema-level step_index column
- Plugin implementations -- individual plugins' use of step numbers

---

## Confidence Assessment

| Aspect | Confidence | Notes |
|--------|-----------|-------|
| DEBT-01 (positional terminality) | HIGH | Explicit docstring acknowledgment. 5 locations confirmed. |
| DEBT-02 (sink write step formula) | HIGH | Single-line formula with no graph lookup. Wrong for coalesce pipelines. |
| DEBT-03 (dead method) | HIGH | grep confirms zero callers of `flush_aggregation_timeout`. |
| DEBT-04 (transform_id_map) | HIGH | Clear Phase 1 index-based mapping, 3 callers in orchestrator. |
| DEBT-05 (coalesce_gate_index) | HIGH | Positional index, directly coupled to DEBT-01. |
| DEBT-06 (bind_runtime_transforms) | HIGH | Explicit fallback for sparse test contexts. Violates test path integrity. |
| DEBT-07-10 (step translation) | MEDIUM | Functional today, but the abstraction boundaries are wrong. |
| DEBT-11 (pervasive step_in_pipeline) | HIGH | 16+ method signatures confirmed via grep. |
| DEBT-15 (config_gates unused) | HIGH | Parameter accepted, never read, docstring says "retained for compatibility." |

## Risk Assessment

| Item | Risk if Unfixed | Risk if Fixed Incorrectly |
|------|----------------|--------------------------|
| DEBT-02 | **HIGH** -- wrong audit step for sink writes in coalesce pipelines | LOW -- localized change |
| DEBT-01 | MEDIUM -- blocks non-linear DAG extensions | MEDIUM -- 5 locations, regression possible |
| DEBT-06 | MEDIUM -- test/production divergence | HIGH -- many tests may break |
| DEBT-11 | LOW (works today) | HIGH -- large interface refactor |
| DEBT-03 | LOW (dead code, no incorrect behavior) | LOW -- just delete |

## Information Gaps

1. **Coalesce pipeline audit correctness**: DEBT-02 claims the sink step formula is wrong for coalesce pipelines. This needs verification: does any integration test with coalesce nodes check the `step_index` value written for sink node_states?
2. **Checkpoint format**: Do checkpoints store step numbers? If so, changing step-number computation affects checkpoint/resume compatibility.
3. **`step_index` column semantics**: Is `step_index` used by any downstream query for ordering or filtering? If it is only stored and displayed, incorrect values are cosmetic. If it is used to reconstruct execution order, incorrect values corrupt lineage.

## Caveats

- This catalog focuses on the **Phase 2 refactoring debt** (step-number vs node-ID dual representation). It does not cover other categories of tech debt in the same files (e.g., the CLAUDE.md-documented P0 issues like non-atomic file writes).
- Severity classifications assume the no-legacy-code policy: "SHOULD_FIX" means the code is technically correct today but violates architectural intent. "MUST_FIX" means the code produces incorrect results under some conditions.
- DEBT-02 is classified MUST_FIX based on analysis, not testing. Verify with a coalesce-pipeline integration test before prioritizing.

---
---

# Technical Debt Catalog: ChaosWeb Duplication Analysis

**Date:** 2026-02-11
**Scope:** Proposed ChaosWeb system (~4,030 LOC) and its duplication relationship with existing ChaosLLM (3,953 LOC)
**Analyst:** Debt Cataloger Agent
**Branch:** RC2.5-sqlite-migration

---

## Executive Summary

The proposed ChaosWeb design will introduce approximately 1,700 LOC of near-duplicate code copied from ChaosLLM, bringing the combined Chaos testing infrastructure to ~8,000 LOC with ~43% structural overlap. This compounds an existing pattern: ELSPETH already carries documented duplication debt in LLM plugins (~6 files, CCP-04 in repair manifest) and CLI event formatters (~600 lines, CCP-05). Adding ChaosWeb without extraction creates a third major duplication cluster.

**Verdict:** The duplication is not acceptable as-is for go. A targeted extraction of shared modules (~400 LOC of shared code) into `elspeth.testing.chaos_base` should happen BEFORE ChaosWeb implementation, not after. The "extract later" approach has a documented failure mode in this codebase: the LLM plugin duplication (P2-04) was tagged for "later extraction" and remains unresolved after 6 variants ship.

---

## Critical Priority (Block ChaosWeb Go Until Resolved)

### DEBT-CW-01: Burst State Machine Duplication Creates Divergence Risk

**Evidence:** `src/elspeth/testing/chaosllm/error_injector.py:147-488` -- The `ErrorInjector` class (342 LOC) contains a thread-safe burst state machine (`_is_in_burst` at line 193, `_get_burst_rate_limit_pct` at line 212, `_get_burst_capacity_pct` at line 218), priority-based and weighted selection algorithms (`_decide_priority` at line 295, `_decide_weighted` at line 397), and an `ErrorDecision` frozen dataclass with factory methods (lines 28-110).

**Impact:** A bug in the burst state machine (e.g., timing edge case at interval boundaries, thread-safety issue in `_get_current_time` at line 185) would need to be found and fixed in both ChaosLLM and ChaosWeb independently. The burst state machine is the most algorithmically complex piece (~80 LOC) and has 5,412 LOC of existing tests across 13 test files. Duplicating it means those tests protect only one copy. The weighted selection algorithm (`_decide_weighted`, lines 397-477) implements a cumulative distribution function with success-weight balancing -- subtle probability bugs here would silently corrupt error injection rates in the second system.

**Effort:** M (3-5 days to extract shared `chaos_base.error_injection` module before ChaosWeb build)

**Category:** Architecture

**Details:** The `ErrorInjector` is protocol-agnostic already. It takes an `ErrorInjectionConfig` and returns an `ErrorDecision`. The ChaosWeb design adds web-specific error types (SSRF redirect, encoding mismatch, truncated HTML) but the core selection algorithm, burst state machine, and `ErrorDecision` dataclass are identical. The natural extraction boundary:

- **Shared:** `ErrorDecision` (83 LOC), `ErrorCategory` enum, `_should_trigger()`, `_is_in_burst()`, `_decide_weighted` algorithm skeleton, burst state management, RNG injection pattern, `reset()`
- **Protocol-specific:** Error type registries (`HTTP_ERRORS`, `CONNECTION_ERRORS`, `MALFORMED_TYPES`), the specific chain of `_should_trigger()` calls in `_decide_priority()`, config field names for error percentages

---

### DEBT-CW-02: Identical Latency Simulator Will Exist in Two Packages

**Evidence:** `src/elspeth/testing/chaosllm/latency_simulator.py` -- 78 LOC. The design states this will be "reused as-is" for ChaosWeb (0 adaptation, direct copy).

**Impact:** Two identical copies of a 78-line module with identical behavior. The `LatencySimulator` class (lines 13-78) depends only on `LatencyConfig` (a Pydantic model at `config.py:145-160` with `base_ms: int` and `jitter_ms: int` fields) and `random.Random`. When the ChaosWeb copy imports from `elspeth.testing.chaosweb.config` instead of the ChaosLLM version, the two `LatencyConfig` classes will also be duplicates. Any latency simulation bug fix must be applied twice.

**Effort:** S (< 1 day to relocate to `elspeth.testing.chaos_base.latency`)

**Category:** Architecture

**Details:** This is the clearest extraction candidate. Both the class and its config model are completely domain-agnostic -- they simulate network latency for any protocol. The existing test coverage is thorough: `tests/unit/testing/chaosllm/test_latency_simulator.py` (339 LOC) and `tests/property/testing/chaosllm/test_latency_properties.py` (155 LOC). After relocation, both ChaosLLM and ChaosWeb import from the shared location and these 494 LOC of tests cover both consumers.

---

### DEBT-CW-03: Config Loading Pattern Duplication (load_config + _deep_merge)

**Evidence:** `src/elspeth/testing/chaosllm/config.py:485-553` -- The `_deep_merge()` function (17 LOC, lines 485-501) and `load_config()` function (50 LOC, lines 504-553) implement 3-layer configuration precedence (preset -> config file -> CLI overrides) with YAML loading and Pydantic validation.

**Impact:** The deep merge algorithm is a correctness-sensitive utility. If a merge edge case is discovered (e.g., list-vs-dict collision, None handling), it must be patched in both locations. The `load_config()` pattern is structurally identical between ChaosLLM and proposed ChaosWeb -- only the top-level config type differs (`ChaosLLMConfig` vs `ChaosWebConfig`).

**Effort:** S (1-2 days to extract `chaos_base.config` with shared utilities and a `load_config` factory)

**Category:** Code Quality

**Details:** The shared config infrastructure includes:

| Component | Location | LOC | Shared? |
|-----------|----------|-----|---------|
| `ServerConfig` | config.py:18-37 | 20 | Identical |
| `MetricsConfig` | config.py:40-53 | 14 | Identical |
| `LatencyConfig` | config.py:145-160 | 16 | Identical |
| `BurstConfig` | config.py:162-192 | 31 | Identical |
| `_deep_merge()` | config.py:485-501 | 17 | Identical |
| `load_config()` pattern | config.py:504-553 | 50 | Structurally identical |
| `_get_presets_dir()` | config.py:444-446 | 3 | Same pattern |
| `list_presets()` | config.py:449-454 | 6 | Identical |
| `load_preset()` | config.py:457-482 | 26 | Identical |
| **Total shared** | | **~183** | |

---

## High Priority (Address Within ChaosWeb Implementation Sprint)

### DEBT-CW-04: Metrics Recorder SQLite Pattern Duplication

**Evidence:** `src/elspeth/testing/chaosllm/metrics.py:1-849` -- The `MetricsRecorder` class implements thread-safe SQLite with per-thread connections (`_get_connection()` at lines 239-273), WAL journaling, time-series bucketing (`_get_bucket_utc()` at lines 110-139), percentile calculation (`_update_bucket_latency_stats()` at lines 450-495), and UPSERT-based aggregation. The design indicates ~270 LOC will be "adapted" for ChaosWeb.

**Impact:** The SQLite connection management pattern (thread-local storage via `threading.local()`, `AttributeError` catch for first-access initialization, connection registry for cleanup) at lines 239-273 is a non-trivial concurrency pattern (35 LOC). The `_get_bucket_utc()` function (30 LOC), `_classify_outcome()` (33 LOC), and percentile calculation logic (40 LOC) are reusable utilities. Bugs in thread-local connection cleanup, WAL configuration, or shared-cache URI detection would need dual fixes.

**Effort:** M (3-5 days -- extract base recorder with pluggable schema and classification)

**Category:** Architecture

**Details:** Natural extraction: a `ChaosMetricsBase` class handles connection lifecycle, time-series bucketing infrastructure, export, reset, and stats aggregation. Protocol-specific subclasses define the SQL schema (`_SCHEMA`), `RequestRecord` dataclass fields, and `_classify_outcome()` logic. The ChaosLLM schema has LLM-specific columns (`deployment`, `model`, `prompt_tokens_approx`, `response_tokens`, `response_mode`); ChaosWeb would have web-specific columns (`url_path`, `content_type`, `response_size_bytes`, `encoding`). The aggregation infrastructure and connection management are identical.

---

### DEBT-CW-05: CLI Typer Structure Duplication

**Evidence:** `src/elspeth/testing/chaosllm/cli.py:1-565` -- The CLI defines `serve`, `presets`, `show_config` commands with Typer annotations, version callback (`_version_callback` at lines 46-56), startup info printing (lines 328-360), and uvicorn launch (lines 362-383). The design indicates ~350 LOC adapted for ChaosWeb.

**Impact:** This compounds the existing CLI duplication problem documented as P1-06 in the repair manifest (event formatters duplicated 3x, ~600 lines) and CCP-05 (CLI duplication cross-cutting pattern). Adding a ChaosWeb CLI variant means three `_version_callback()` implementations, three `presets()` commands, three `show_config()` commands, and three MCP server launch patterns. The serve command's CLI-override-to-dict conversion logic (lines 258-312, 55 LOC) is structural boilerplate that differs only in which error-injection flags exist.

**Effort:** M (2-3 days -- extract shared CLI base with protocol-specific options)

**Category:** Code Quality

**Details:** Shared CLI infrastructure:
- `_version_callback()` (lines 46-56) -- identical
- `presets()` command (lines 386-404) -- identical
- `show_config()` command (lines 407-467) -- identical except config type
- MCP server launch pattern (lines 469-551) -- identical except module path
- Startup info printing pattern (lines 328-360) -- structurally identical

Protocol-specific: the `serve` command's error-injection CLI flags differ (LLM: `--capacity-529-pct`, `--rate-limit-pct`; Web: `--ssrf-redirect-pct`, `--encoding-mismatch-pct`).

---

### DEBT-CW-06: Admin Route Handler Duplication in Server

**Evidence:** `src/elspeth/testing/chaosllm/server.py:103-254` -- The server class defines `/health` (lines 209-218), `/admin/config` (lines 233-241), `/admin/stats` (lines 243-245), `/admin/reset` (lines 247-250), `/admin/export` (lines 252-254) endpoints plus runtime config update (`update_config()` at lines 159-182) and run info persistence (`_record_run_info()` at lines 192-205). The design indicates ~200 LOC adapted for ChaosWeb's admin routes.

**Impact:** The admin endpoints implement a standard operational API contract: health check with burst status, runtime config hot-reload via POST, stats retrieval, metrics reset, data export. This contract is protocol-agnostic. Duplicating `update_config()` (24 LOC) means two implementations of the config-section-merge-and-rebuild pattern, which currently accesses private attributes (`self._error_injector._config`) -- a pattern that is fragile even once, let alone duplicated.

**Effort:** M (2-3 days -- extract `ChaosServerBase` with admin routes)

**Category:** Architecture

**Details:** The `ChaosLLMServer.__init__()` (lines 87-101) shows the composition pattern: `error_injector` + `response_generator` + `latency_simulator` + `metrics_recorder`. ChaosWeb would have the same composition with a different generator (`content_generator` vs `response_generator`) and different request-specific endpoints (multi-path routing vs LLM endpoint). The admin layer and health endpoint are identical.

---

## Medium Priority (Address Before Third Chaos Variant)

### DEBT-CW-07: Test Suite Duplication Risk (~2,500 LOC)

**Evidence:** ChaosLLM tests total 5,412 LOC across 13 files:

| Test File | LOC | Tests Shared Behavior? |
|-----------|-----|----------------------|
| `test_error_injector.py` | 803 | YES -- burst, selection, RNG |
| `test_metrics.py` | 1,151 | PARTIAL -- connection mgmt shared, schema specific |
| `test_response_generator.py` | 867 | NO -- LLM-specific |
| `test_server.py` | 694 | PARTIAL -- admin routes shared, endpoints specific |
| `test_latency_simulator.py` | 339 | YES -- entirely shared |
| `test_fixture.py` | 230 | NO -- LLM-specific |
| `test_error_injector_properties.py` | 404 | YES -- burst, selection properties |
| `test_metrics_config_properties.py` | 386 | PARTIAL |
| `test_response_generator_properties.py` | 379 | NO -- LLM-specific |
| `test_latency_properties.py` | 155 | YES -- entirely shared |

**Impact:** Without shared base modules, ChaosWeb requires redundant test coverage for shared behavior: error injection (~1,207 LOC), latency simulation (~494 LOC), metrics infrastructure (~500 LOC estimated), and config loading. Estimated duplicated test LOC: ~2,200-2,500.

**Effort:** L (5-8 days of redundant test writing if not extracted first; 0 days if shared modules are extracted and existing tests relocated)

**Category:** Code Quality

---

### DEBT-CW-08: Compounding Existing Duplication Pattern (CCP-04 + CCP-05)

**Evidence:** `/home/john/elspeth-rapid/docs/code_analysis/_repair_manifest.md` documents:
- **CCP-04** (line 628): LLM plugin duplication across 6 files -- "config classes, JSON schema builders, response parsers, Langfuse tracing, error classification"
- **CCP-05** (line 634): CLI event formatters defined 3 times (~600 lines), run/resume finalization duplicated (~800 lines)
- **P1-06** (line 190): CLI duplication tagged as NEEDS_REFACTOR
- **P1-07** (line 202): Orchestrator run/resume duplication (~800 lines)

**Impact:** ChaosWeb adds a third duplication cluster to a codebase already carrying two unresolved duplication debts identified on 2026-02-06 (5 days ago). Current unresolved duplication inventory:

| Cluster | LOC Duplicated | Status |
|---------|---------------|--------|
| LLM plugins (CCP-04) | ~2,000 | Unresolved (5+ days) |
| CLI formatters (CCP-05) | ~600 | Unresolved (5+ days) |
| Orchestrator run/resume (P1-07) | ~800 | Unresolved (5+ days) |
| **ChaosWeb (proposed)** | **~1,700** | **Not yet created** |
| **Total after ChaosWeb** | **~5,100** | |

Adding ChaosWeb would increase total duplication debt by 33%.

**Effort:** N/A (meta-observation)

**Category:** Architecture

---

## Recommendation: Extract Before Build

### Proposed chaos_base Module Structure

```
src/elspeth/testing/chaos_base/
    __init__.py
    config.py          # ServerConfig, MetricsConfig, LatencyConfig, BurstConfig,
                       #   _deep_merge(), load_config() factory, preset utilities
                       #   (~183 LOC extracted from chaosllm/config.py)
    error_injection.py # ErrorDecision, ErrorCategory, BaseErrorInjector
                       #   (burst state machine, selection algorithms, RNG management)
                       #   (~120 LOC of shared algorithm core)
    latency.py         # LatencySimulator (moved verbatim from chaosllm)
                       #   (78 LOC)
    metrics.py         # BaseMetricsRecorder (connection lifecycle, bucketing,
                       #   percentile calculation, export/reset/stats framework)
                       #   (~150 LOC of shared infrastructure)
    cli.py             # Shared CLI utilities (version callback, presets command,
                       #   show_config command, startup printing pattern)
                       #   (~80 LOC)
```

**Estimated extraction effort:** 5-8 days (including test relocation)

**Estimated LOC in chaos_base:** ~400 LOC of genuinely shared code, plus ~500 LOC of relocated tests

**ChaosWeb savings:**
- Eliminates ~1,700 LOC of copied code
- Eliminates ~2,200 LOC of duplicated tests
- ChaosWeb reduces to ~2,330 LOC of genuinely new code (content_generator, web error types, multi-path routing, web-specific config fields, web-specific tests)
- Existing ChaosLLM test suite continues to cover all shared behavior

### When to Extract

**Now. Before ChaosWeb implementation begins.**

The design's argument for deferred extraction ("follows ELSPETH's no-premature-abstraction policy") misapplies the principle. No-premature-abstraction means "don't abstract before you see the second use case." ChaosWeb IS the second use case. The abstraction boundary is visible, well-defined, and backed by concrete evidence from two fully specified designs.

The extraction threshold question ("at what LOC?") is the wrong frame. The threshold is not LOC -- it is "do we have two concrete consumers with a clear shared interface?" That condition is met now.

The "extract later" approach has failed in this codebase already: LLM plugin duplication (CCP-04, 6 files, ~2,000 LOC) was identified for extraction and remains unresolved. Adding ChaosWeb under the same "later" promise adds a second instance of deferred-extraction debt on top of the first.

---

## Confidence Assessment

| Aspect | Confidence | Basis |
|--------|------------|-------|
| ChaosLLM code structure | HIGH | Read all 7 source files (3,953 LOC total), all 13 test files (5,412 LOC total) |
| Duplication quantification | HIGH | Line-by-line comparison of ChaosLLM source against design specification |
| Extraction boundary identification | HIGH | Based on actual dependency analysis of ChaosLLM module imports and class interfaces |
| Effort estimates | MEDIUM | Based on code complexity and ELSPETH development velocity from git log (5 commits in 3 days on current branch) |
| ChaosWeb design accuracy | MEDIUM | Based on user-provided design summary; no design document exists in the repository |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Extraction delays ChaosWeb start by ~1 week | HIGH | LOW | Extraction reduces ChaosWeb implementation by ~1 week (net neutral to schedule) |
| Shared base introduces tight coupling | LOW | MEDIUM | Use composition over inheritance; protocol-specific behavior stays in concrete classes |
| Extraction proves over-engineered | LOW | LOW | Worst case: shared module used by only 2 consumers, which is still better than copy-paste |
| Future Chaos variant (ChaosDB, ChaosQueue) leverages shared base | MEDIUM | POSITIVE | Third consumer confirms extraction value with zero incremental cost |
| "Extract later" never happens | HIGH | HIGH | Documented precedent: LLM plugins (CCP-04), CLI (CCP-05) both tagged for extraction, both unresolved |

## Information Gaps

1. **No ChaosWeb design document exists in the repository.** Analysis is based entirely on the user-provided specification in the prompt. Actual implementation may diverge from the described adaptation percentages. The 1,700 LOC duplication figure comes from the design's own estimate and has not been independently verified against a prototype.

2. **No ChaosWeb prototype code exists.** The extraction boundary is inferred from ChaosLLM structure and the design description. A prototype might reveal additional shared surface area or unforeseen protocol-specific requirements that change the extraction calculus.

3. **Third variant probability is unknown.** If ChaosDB, ChaosQueue, or ChaosAPI is planned, the extraction ROI increases significantly. If ChaosWeb is definitively the last variant, the ROI is still positive but the urgency is lower. The design document does not mention future variants.

4. **Jinja2 SSTI surface.** ChaosLLM's `response_generator.py` uses `jinja2.sandbox.SandboxedEnvironment` (line 416). The repair manifest flags this as P1-15 (Jinja2 SSTI Surface in Blob Sink and ChaosLLM). If ChaosWeb's content_generator also uses Jinja2 templates for HTML generation, this security concern is duplicated rather than addressed once in a shared location.

## Caveats

1. **Effort estimates assume familiarity with ChaosLLM internals.** The 5-8 day extraction estimate assumes a developer who has worked with the ChaosLLM codebase. A developer new to the system would need additional ramp time.

2. **Test migration complexity not fully estimated.** Moving shared tests from `tests/*/testing/chaosllm/` to `tests/*/testing/chaos_base/` while maintaining ChaosLLM-specific tests requires careful fixture management. The conftest.py (4 LOC) is trivial, but test files that mix shared and protocol-specific assertions need splitting.

3. **The "no premature abstraction" argument has legitimate force.** The counter-argument (extract now) depends on the design specification being accurate about the shared surface area. If ChaosWeb's actual implementation reveals the shared surface is smaller than the design projects (e.g., the burst state machine needs different timing semantics for web scraping), the extraction may be over-engineered. However, the risk is asymmetric: extracting a module that turns out slightly over-general costs ~1 day of unnecessary abstraction; NOT extracting and maintaining 1,700 LOC of duplicates costs ongoing maintenance indefinitely.

4. **This analysis does not assess whether ChaosWeb itself is needed.** The catalog assumes ChaosWeb will be built and focuses solely on the duplication implications. The business case for web scraping resilience testing is taken as given.
