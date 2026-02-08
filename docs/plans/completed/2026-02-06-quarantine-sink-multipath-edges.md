# Quarantine/Error Sink Multipath Edges — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix quarantine sink routing by adding quarantine/error edges to the execution graph, making all data flows first-class graph edges with full audit trail coverage.

**Architecture:** Add a new `RoutingMode.DIVERT` to represent error/quarantine edges — data is diverted from the normal flow to a side-channel sink. The DAG builder (`from_plugin_instances()`) creates these edges based on source `_on_validation_failure` and transform `_on_error` configuration. These edges make quarantine/error sinks reachable in the graph, provide node_ids for the SinkExecutor, and enable future `routing_events` audit trail entries for quarantine/error writes. Note: `routing_events` recording is deferred (requires per-row source `node_states` — see Future Enhancements). Audit coverage via `token_outcomes` (QUARANTINED with error_hash) is sufficient for now.

**Tech Stack:** Python, NetworkX (DAG), SQLAlchemy (landscape schema), Pydantic (config)

**Beads Issue:** `elspeth-rapid-a3pu`

**Why not Option A (exclude from graph)?** The SinkExecutor needs `sink_id_map[SinkName(sink_name)]` to get node_ids for creating `node_states` and `token_outcomes`. Without a graph node, there's no node_id, and quarantine writes crash with `KeyError`. Option A would require a parallel node_id registration path outside the graph — messy and duplicates responsibility.

---

## Context for the Implementer

### Current state

1. `from_plugin_instances()` (dag.py:432-443) adds ALL sinks as graph nodes
2. Only DAG-flow edges are created (continue, gate routes, fork branches)
3. Quarantine sinks have no incoming edges → `GraphValidationError: unreachable node`
4. Source quarantine routing happens in orchestrator core.py:1190-1246, bypassing the graph
5. Transform error routing happens in processor.py:1775-1809, bypassing the graph
6. Neither quarantine nor error writes record `routing_events` (audit gap)

### What changes

| Component | Current | After |
|-----------|---------|-------|
| `RoutingMode` enum | `MOVE`, `COPY` | + `DIVERT` |
| `from_plugin_instances()` | No quarantine/error edges | Adds divert edges |
| Graph validation | All sinks must be reachable | Still true (divert edges provide reachability) |
| Orchestrator quarantine write | Direct sink lookup, no routing_event | Divert edge provides node_id for sink write |
| Processor error write | Direct sink lookup, no routing_event | Divert edge provides node_id for sink write |
| Audit trail | No routing_events for quarantine/error | `token_outcomes` records QUARANTINED/FAILED with error_hash. `routing_events` deferred (see Future Enhancements) |

### Key files

| File | Change |
|------|--------|
| `src/elspeth/contracts/enums.py` | Add `RoutingMode.DIVERT` |
| `src/elspeth/core/dag.py` | Add divert edges in `from_plugin_instances()` |
| `src/elspeth/engine/orchestrator/core.py` | Record routing_events for quarantine writes |
| `src/elspeth/engine/processor.py` | Record routing_events for error writes |
| `tests/unit/test_dag.py` | Test divert edges |
| `tests/integration/test_cli_integration.py` | Existing test should now pass |

### Edge label conventions

Divert edges use reserved labels to prevent collisions with user-defined gate route labels:

| Edge | Label | From | To |
|------|-------|------|----|
| Source quarantine | `__quarantine__` | source node | quarantine sink node |
| Transform error | `__error_N__` | transform node (seq N) | error sink node |

The `__` prefix makes these impossible to collide with user-defined route labels. **Enforcement:** Add a Pydantic validator on `GateSettings.routes` (in `core/config.py`) that rejects route labels starting with `__`:

```python
@field_validator("routes")
@classmethod
def validate_route_labels(cls, v: dict[str, str]) -> dict[str, str]:
    for label in v:
        if label.startswith("__"):
            raise ValueError(
                f"Route label '{label}' starts with '__', which is reserved "
                f"for system edges (__quarantine__, __error_N__)"
            )
    return v
```

This validation must be added as part of Task 2 (not deferred).

---

## Task 1: Add `RoutingMode.DIVERT`

**Files:**
- Modify: `src/elspeth/contracts/enums.py:127-137`
- Test: `tests/unit/contracts/test_enums.py` (if exists, else `tests/unit/test_contracts.py`)

### Step 1: Write failing test

Find or create the test file for enums. Add:

```python
def test_routing_mode_divert_exists() -> None:
    """DIVERT mode exists for error/quarantine edges."""
    from elspeth.contracts.enums import RoutingMode
    assert RoutingMode.DIVERT == "divert"
    assert RoutingMode.DIVERT.value == "divert"
```

### Step 2: Run test to verify it fails

Run: `.venv/bin/python -m pytest tests/ -k "test_routing_mode_divert_exists" -v`
Expected: FAIL with `AttributeError: DIVERT`

### Step 3: Add DIVERT to RoutingMode

In `src/elspeth/contracts/enums.py`, add to the `RoutingMode` enum (after line 137):

```python
class RoutingMode(str, Enum):
    """Mode for routing edges.

    MOVE: Token exits current path, goes to destination only
    COPY: Token clones to destination AND continues on current path
    DIVERT: Token is diverted from normal flow to error/quarantine sink.
            Like MOVE, but semantically distinct: represents failure handling,
            not intentional routing. Used for source quarantine and transform
            on_error edges.

    Uses (str, Enum) for database serialization.
    """

    MOVE = "move"
    COPY = "copy"
    DIVERT = "divert"
```

### Step 4: Run test to verify it passes

Run: `.venv/bin/python -m pytest tests/ -k "test_routing_mode_divert_exists" -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/elspeth/contracts/enums.py tests/
git commit -m "feat: add RoutingMode.DIVERT for quarantine/error edges"
```

---

## Task 2: Add divert edges in `from_plugin_instances()`

This is the core change. After building all normal edges, add divert edges from source to quarantine sink and from transforms to their error sinks.

**Files:**
- Modify: `src/elspeth/core/dag.py:352-812` (inside `from_plugin_instances()`)
- Test: `tests/unit/test_dag.py`

### Step 1: Write failing tests

Add to `tests/core/test_dag.py` (the existing DAG test file). Use the production factory pattern (`instantiate_plugins_from_config`) following `TestExecutionGraphFromConfig`, per the Test Path Integrity rule.

**NOTE on test approach:** DAG unit tests that test graph algorithms (topo sort, cycle detection) may use manual construction. But these tests exercise `from_plugin_instances()` edge creation, so they MUST use the production factory path.

```python
class TestDivertEdges:
    """Tests for quarantine and error divert edges in graph construction."""

    @pytest.fixture
    def plugin_manager(self) -> PluginManager:
        from elspeth.plugins.registry import create_plugin_manager
        return create_plugin_manager()

    def _build_graph(
        self, settings: ElspethSettings, plugin_manager: PluginManager
    ) -> ExecutionGraph:
        """Build ExecutionGraph via production factory path."""
        from elspeth.cli_helpers import instantiate_plugins_from_config
        plugins = instantiate_plugins_from_config(settings, plugin_manager)
        return ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins.get("aggregations", {}),
            gates=list(settings.gates),
            default_sink=settings.default_sink,
        )

    def test_source_quarantine_edge_created(self, plugin_manager) -> None:
        """Source with on_validation_failure creates a divert edge to quarantine sink."""
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={"path": "test.csv", "on_validation_failure": "quarantine",
                         "schema": {"mode": "observed"}},
            ),
            sinks={
                "default": SinkSettings(plugin="json", options={"path": "out.json", "schema": {"mode": "observed"}}),
                "quarantine": SinkSettings(plugin="json", options={"path": "quar.json", "schema": {"mode": "observed"}}),
            },
            default_sink="default",
        )
        graph = self._build_graph(settings, plugin_manager)
        graph.validate()

        edges = graph.get_edges()
        divert_edges = [e for e in edges if e.mode == RoutingMode.DIVERT]
        assert len(divert_edges) == 1
        assert divert_edges[0].label == "__quarantine__"

    def test_source_discard_no_divert_edge(self, plugin_manager) -> None:
        """Source with on_validation_failure='discard' creates no divert edge."""
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={"path": "test.csv", "on_validation_failure": "discard",
                         "schema": {"mode": "observed"}},
            ),
            sinks={"default": SinkSettings(plugin="json", options={"path": "out.json", "schema": {"mode": "observed"}})},
            default_sink="default",
        )
        graph = self._build_graph(settings, plugin_manager)
        graph.validate()

        edges = graph.get_edges()
        divert_edges = [e for e in edges if e.mode == RoutingMode.DIVERT]
        assert len(divert_edges) == 0

    def test_transform_error_edge_created(self, plugin_manager) -> None:
        """Transform with on_error creates a divert edge to error sink."""
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={"path": "test.csv", "on_validation_failure": "discard",
                         "schema": {"mode": "observed"}},
            ),
            transforms=[
                TransformSettings(plugin="passthrough", options={"on_error": "errors"}),
            ],
            sinks={
                "default": SinkSettings(plugin="json", options={"path": "out.json", "schema": {"mode": "observed"}}),
                "errors": SinkSettings(plugin="json", options={"path": "err.json", "schema": {"mode": "observed"}}),
            },
            default_sink="default",
        )
        graph = self._build_graph(settings, plugin_manager)
        graph.validate()

        edges = graph.get_edges()
        divert_edges = [e for e in edges if e.mode == RoutingMode.DIVERT]
        assert len(divert_edges) == 1
        assert divert_edges[0].label == "__error_0__"

    def test_quarantine_and_error_both_present(self, plugin_manager) -> None:
        """Both quarantine and error divert edges coexist."""
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={"path": "test.csv", "on_validation_failure": "quarantine",
                         "schema": {"mode": "observed"}},
            ),
            transforms=[
                TransformSettings(plugin="passthrough", options={"on_error": "errors"}),
            ],
            sinks={
                "default": SinkSettings(plugin="json", options={"path": "out.json", "schema": {"mode": "observed"}}),
                "quarantine": SinkSettings(plugin="json", options={"path": "quar.json", "schema": {"mode": "observed"}}),
                "errors": SinkSettings(plugin="json", options={"path": "err.json", "schema": {"mode": "observed"}}),
            },
            default_sink="default",
        )
        graph = self._build_graph(settings, plugin_manager)
        graph.validate()

        edges = graph.get_edges()
        divert_edges = [e for e in edges if e.mode == RoutingMode.DIVERT]
        assert len(divert_edges) == 2

    def test_quarantine_to_default_sink_creates_divert_edge(self, plugin_manager) -> None:
        """If quarantine destination is default sink, divert edge still created.

        Also verifies that schema validation still runs for the normal continue
        edge to default sink (the DIVERT skip must be per-edge, not per-node-pair).
        """
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={"path": "test.csv", "on_validation_failure": "default",
                         "schema": {"mode": "observed"}},
            ),
            sinks={"default": SinkSettings(plugin="json", options={"path": "out.json", "schema": {"mode": "observed"}})},
            default_sink="default",
        )
        graph = self._build_graph(settings, plugin_manager)
        graph.validate()

        # Should have both continue edge and divert edge to default sink
        edges = graph.get_edges()
        divert_edges = [e for e in edges if e.mode == RoutingMode.DIVERT]
        assert len(divert_edges) == 1
        # Normal continue edge should also exist
        normal_edges = [e for e in edges if e.mode != RoutingMode.DIVERT]
        assert any(e.label == "continue" for e in normal_edges)

    def test_multiple_transforms_share_error_sink(self, plugin_manager) -> None:
        """Multiple transforms can route errors to the same sink."""
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={"path": "test.csv", "on_validation_failure": "discard",
                         "schema": {"mode": "observed"}},
            ),
            transforms=[
                TransformSettings(plugin="passthrough", options={"on_error": "errors"}),
                TransformSettings(plugin="passthrough", options={"on_error": "errors"}),
            ],
            sinks={
                "default": SinkSettings(plugin="json", options={"path": "out.json", "schema": {"mode": "observed"}}),
                "errors": SinkSettings(plugin="json", options={"path": "err.json", "schema": {"mode": "observed"}}),
            },
            default_sink="default",
        )
        graph = self._build_graph(settings, plugin_manager)
        graph.validate()

        edges = graph.get_edges()
        divert_edges = [e for e in edges if e.mode == RoutingMode.DIVERT]
        error_edges = [e for e in divert_edges if e.label.startswith("__error_")]
        assert len(error_edges) == 2
        assert {e.label for e in error_edges} == {"__error_0__", "__error_1__"}
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/unit/test_dag.py::TestDivertEdges -v`
Expected: FAIL (quarantine sink unreachable, no DIVERT edges created)

### Step 3: Implement divert edges in `from_plugin_instances()`

Add a new section after the `CONNECT FINAL NODE TO OUTPUT` block (after line 774 in dag.py), before the coalesce connection section. The placement must be AFTER all normal edges are built but BEFORE `validate_edge_compatibility()`.

Insert this block:

```python
        # ===== ADD DIVERT EDGES (quarantine/error sinks) =====
        # Divert edges represent error/quarantine data flows that bypass the
        # normal DAG execution path. They make quarantine/error sinks reachable
        # in the graph (required for node_ids and audit trail).
        #
        # These are STRUCTURAL markers, not execution paths. Rows reach these
        # sinks via exception handling (processor.py) or source validation
        # failures (orchestrator.py), not by traversing the edge during
        # normal processing.

        # Source quarantine edge
        # _on_validation_failure is defined on SourceProtocol (protocols.py:78)
        quarantine_dest = source._on_validation_failure
        if quarantine_dest != "discard" and SinkName(quarantine_dest) in sink_ids:
            graph.add_edge(
                source_id,
                sink_ids[SinkName(quarantine_dest)],
                label="__quarantine__",
                mode=RoutingMode.DIVERT,
            )

        # Transform error edges
        # GateProtocol does NOT define _on_error, so skip gates.
        # The isinstance check is framework-boundary type narrowing (not
        # defensive programming) — the transforms list contains both
        # TransformProtocol and GateProtocol instances despite the type
        # annotation (see dag.py:456 where is_gate = isinstance(transform, GateProtocol)).
        for i, transform in enumerate(transforms):
            if isinstance(transform, GateProtocol):
                continue  # Gates don't have _on_error
            on_error = transform._on_error
            if on_error is not None and on_error != "discard" and SinkName(on_error) in sink_ids:
                transform_node_id = transform_ids[i]
                graph.add_edge(
                    transform_node_id,
                    sink_ids[SinkName(on_error)],
                    label=f"__error_{i}__",
                    mode=RoutingMode.DIVERT,
                )
```

**NOTE:** `GateProtocol` is already imported earlier in `from_plugin_instances()` (dag.py:386). No additional import needed.

**CRITICAL:** This must be placed before `graph.validate_edge_compatibility()` (line 810) so the edges exist when schema validation runs. But divert edges should skip schema validation (quarantine data doesn't conform to the source output schema). See Step 4.

### Step 4: Skip schema validation for divert edges

**IMPORTANT:** Do NOT modify `_validate_single_edge()`. Instead, filter DIVERT edges in the caller — `validate_edge_compatibility()` (dag.py:908-928).

**Why not modify `_validate_single_edge`?** On a MultiDiGraph, the same `(from, to)` node pair can have BOTH a normal edge AND a divert edge (e.g., source → default sink has a `continue` edge and a `__quarantine__` divert edge). If we add a DIVERT check inside `_validate_single_edge(from, to)`, it would call `get_edge_data(from, to)` which returns ALL edges between the pair. Finding a DIVERT edge would skip validation for the normal edge too — a subtle correctness bug.

Instead, filter at the iteration level where we have per-edge data:

```python
    def validate_edge_compatibility(self) -> None:
        """Validate schema compatibility for all edges in the graph."""
        # Validate each edge (skip divert edges — quarantine/error data doesn't
        # conform to producer schemas because it failed validation or errored)
        for from_id, to_id, edge_data in self._graph.edges(data=True):
            if edge_data["mode"] == RoutingMode.DIVERT:
                continue  # Structural marker, not a data flow edge
            self._validate_single_edge(from_id, to_id)

        # Validate all coalesce nodes ...
```

**NOTE:** `edge_data["mode"]` uses direct access (not `.get()`) because `mode` is always set by our `add_edge()` calls — this is system-owned data per the Three-Tier Trust Model.

### Step 5: Exclude divert edge labels from uniqueness check

In `validate()` (dag.py:242-256), the edge label uniqueness check iterates all outgoing edges. Divert labels (`__quarantine__`, `__error_N__`) use the `__` prefix convention and won't collide with user labels, but verify the uniqueness check still passes. No code change expected — the `__quarantine__` label is unique per source node.

### Step 6: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/unit/test_dag.py::TestDivertEdges -v`
Expected: all 5 tests PASS

### Step 7: Run existing DAG tests for regressions

Run: `.venv/bin/python -m pytest tests/unit/test_dag.py -v`
Expected: no regressions

### Step 8: Commit

```bash
git add src/elspeth/core/dag.py tests/unit/test_dag.py
git commit -m "feat: add divert edges for quarantine/error sinks in DAG

Source on_validation_failure creates __quarantine__ divert edge from
source to quarantine sink. Transform on_error creates __error_N__
divert edge from transform to error sink. Schema validation is
skipped for divert edges (quarantine/error data doesn't conform to
producer schemas).

Part of: elspeth-rapid-a3pu"
```

---

## Task 3: Wire quarantine routing through edge_map

Currently, orchestrator core.py:1190-1246 routes quarantine tokens directly to sinks by name. Update it to use `edge_map` and record `routing_events` for auditability.

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py:1190-1246`
- Test: existing `test_invalid_rows_routed_to_quarantine_sink` should pass after this

### Step 1: Run the failing integration test to confirm it still fails

Run: `.venv/bin/python -m pytest tests/integration/test_cli_integration.py::TestSourceQuarantineRouting::test_invalid_rows_routed_to_quarantine_sink -v`
Expected: FAIL (still fails because CLI doesn't exclude sinks — but now with divert edges, it should pass if Task 2 worked correctly)

**WAIT:** Actually, after Task 2, the quarantine sink IS now reachable via the divert edge. The graph validation should pass! Run the test and check.

If the test PASSES: the basic fix is done (quarantine sink has a divert edge, graph validates, sink write works). Skip to Step 3 to add routing_events.

If the test still FAILS: investigate the error. The most likely issues are:
- Export sink also needs filtering (check if the test config has export enabled — it doesn't, so this should be fine)
- `validate_edge_compatibility()` rejects the divert edge (if Step 4 of Task 2 wasn't applied correctly)

### Step 2: Verify the test passes

Run: `.venv/bin/python -m pytest tests/integration/test_cli_integration.py::TestSourceQuarantineRouting -v`
Expected: PASS (both quarantine routing and discard tests)

### Step 3: Verify audit trail coverage (no code change)

Recording `routing_events` for quarantine writes requires a `state_id` (FK to `node_states`). The `routing_events.state_id` column is `NOT NULL` (schema.py:323), so partial implementation is structurally impossible without schema changes. The source node doesn't create per-row `node_states` — adding them is a larger architectural change tracked in Future Enhancements.

**Current audit coverage (sufficient):**
- `token_outcomes` records QUARANTINED status with `error_hash` for every quarantined row
- The divert edge is registered in `edge_map` (orchestrator/core.py:907-918), providing the infrastructure for future `routing_events` wiring
- Quarantine sink writes create `node_states` and `token_outcomes` via SinkExecutor (uses the node_id from the divert edge)

**Do NOT add a dead `pass` block or TODO comment.** The gap is documented in Future Enhancements below and should be tracked as a beads follow-up issue.

### Step 4: Commit

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "fix: quarantine sink routing works with divert edges in DAG

The quarantine sink now has an incoming __quarantine__ divert edge from
the source, making it reachable in the graph. This provides the node_id
required by SinkExecutor for audit trail entries.

Routing_events recording for quarantine writes deferred (requires
per-row source node_states — tracked as follow-up).

Fixes: elspeth-rapid-a3pu"
```

---

## Task 4: Remove now-unnecessary CLI export sink filtering

With the divert edge approach, the export sink exclusion at cli.py:416-419 is now the remaining case of a sink without incoming edges. The export sink does NOT need a divert edge (it doesn't receive pipeline data at all — it receives audit exports post-run). The export sink should continue to be excluded from the graph.

**Files:**
- Verify: `src/elspeth/cli.py:416-419` — export sink exclusion stays as-is

No changes needed. The export sink remains excluded because it truly doesn't participate in any data flow (not even error/quarantine). This is correct.

### Step 1: Verify no changes needed

Read cli.py:416-419 and confirm the export sink exclusion is still present and correct.

### Step 2: Run the full test suite

Run: `.venv/bin/python -m pytest tests/ -x --timeout=60`
Expected: no regressions

### Step 3: Commit (only if any cleanup was needed)

---

## Task 5: Add integration test for dedicated transform error sink

Verify that a sink only referenced by `on_error` doesn't break graph validation. The divert edge makes it reachable.

**Files:**
- Modify: `tests/integration/test_cli_integration.py`

### Step 1: Add test fixture and config

Add `TestTransformErrorSinkRouting` class with full inline fixture (do NOT cross-reference the Option A plan):

```python
class TestTransformErrorSinkRouting:
    """Tests for sinks only reachable via transform on_error divert edges."""

    @pytest.fixture
    def error_sink_pipeline_config(self, tmp_path: Path) -> Path:
        """Pipeline config with a dedicated error sink only referenced by on_error."""
        input_csv = tmp_path / "input.csv"
        input_csv.write_text("id,value\n1,good\n2,bad\n3,ok\n")

        config = {
            "source": {
                "plugin": "csv",
                "options": {
                    "path": str(input_csv),
                    "on_validation_failure": "discard",
                    "schema": {"mode": "observed"},
                },
            },
            "transforms": [
                {
                    "plugin": "passthrough",
                    "options": {"on_error": "errors"},
                },
            ],
            "sinks": {
                "default": {
                    "plugin": "json",
                    "options": {
                        "path": str(tmp_path / "output.json"),
                        "schema": {"mode": "observed"},
                    },
                },
                "errors": {
                    "plugin": "json",
                    "options": {
                        "path": str(tmp_path / "errors.json"),
                        "schema": {"mode": "observed"},
                    },
                },
            },
            "default_sink": "default",
        }

        config_path = tmp_path / "settings.yaml"
        import yaml
        config_path.write_text(yaml.dump(config))
        return config_path

    def test_dedicated_error_sink_does_not_break_graph(
        self, error_sink_pipeline_config: Path, tmp_path: Path
    ) -> None:
        """A sink only referenced by on_error must not break DAG validation."""
        from elspeth.cli import app

        result = runner.invoke(app, ["run", "-s", str(error_sink_pipeline_config), "--execute"])
        assert result.exit_code == 0, f"Pipeline failed: {result.output}"
```

### Step 2: Run the test

Run: `.venv/bin/python -m pytest tests/integration/test_cli_integration.py::TestTransformErrorSinkRouting -v`
Expected: PASS (divert edge makes error sink reachable)

### Step 3: Commit

```bash
git add tests/integration/test_cli_integration.py
git commit -m "test: add integration test for dedicated transform error sink"
```

---

## Task 6: Close beads issue and verify

### Step 1: Run full test suite

Run: `.venv/bin/python -m pytest tests/ --timeout=60`
Expected: all tests pass

### Step 2: Close beads issue

```bash
bd close elspeth-rapid-a3pu --reason="Fixed by adding DIVERT edges for quarantine/error sinks in DAG"
bd sync
```

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Divert edge confuses gate routing | Low | `__` prefix labels enforced by Pydantic validator on GateSettings.routes; RoutingMode.DIVERT is distinct from MOVE/COPY |
| Schema validation skips normal edge when divert edge exists to same sink | **Eliminated** | Fixed: filter DIVERT edges in `validate_edge_compatibility()` loop, not in `_validate_single_edge()`. Per-edge check, not per-node-pair |
| Existing tests break due to extra edges | Medium | Grep for `edge_count` assertions in test suite. Known locations: `TestExecutionGraphFromConfig` lines 668, 749, 812, 1164. Currently all use `on_validation_failure: "discard"`, so likely safe — but verify |
| DB migration needed for "divert" mode string | Low | `default_mode` column is String(16), "divert" fits; no schema migration needed |
| Resume path breaks (edge_map mismatch) | Low | Divert edges are deterministic from config; resume rebuilds same graph |
| Export sink still excluded separately | None | Export is truly non-pipeline; stays excluded as before |
| Fork/coalesce starvation when on_error diverts inside fork branch | Medium | **Pre-existing behavior** — not introduced by this plan. Coalesce with `require_all` and no timeout will hang if a branch token gets error-routed. Mitigated by best_effort/quorum policies and timeouts. Document as known limitation |
| Invalid sink name in on_error/on_validation_failure | Low | `validate_transform_error_sinks()` in orchestrator/validation.py already catches misconfigured sink names at pipeline init with clear error messages |

## Future Enhancements (not in this plan)

1. **routing_events for quarantine writes**: Requires per-row source `node_states` (larger architectural change). The `routing_events.state_id` FK is NOT NULL, so this is structurally impossible without schema changes. The `edge_map` infrastructure is already in place — once per-row source states exist, wiring routing_events is straightforward. **Create a beads follow-up issue for this.**
2. **routing_events for transform error writes**: Requires capturing `state_id` at error time in processor. Similar constraint to (1).
3. **Graph visualization**: Display divert edges as dashed/red lines in Mermaid diagrams
4. **MCP server**: Include divert edges in `explain_token()` lineage results — currently they'll appear in `get_dag_structure()` but may confuse lineage views. Consider filtering or visually distinguishing them.
5. **Fork/coalesce + on_error interaction**: Document that `on_error` routing inside a fork branch can starve coalesce barriers with `require_all` policy and no timeout. Consider validation warning or prohibition in a future plan.

## Review Panel Notes

This plan was reviewed by a 4-perspective panel (Architecture, Python Engineering, QA, Systems Thinking) across three rounds. Key outcomes:

- **Unanimous**: DIVERT is the correct approach; `isinstance(transform, GateProtocol)` check is needed (GateProtocol lacks `_on_error`)
- **Critical bug fixed**: Original `_validate_single_edge` approach would skip schema validation for normal edges when a divert edge existed to the same sink. Fixed by filtering in `validate_edge_compatibility()` caller.
- **Test strategy**: Production factory path (`instantiate_plugins_from_config`) for all tests, per Test Path Integrity rule.
- **Deferred routing_events**: Acceptable — structurally impossible without schema changes. `token_outcomes` provides sufficient audit coverage.
