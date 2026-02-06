# Quarantine Sink DAG Exclusion — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix quarantine sink routing by excluding non-DAG sinks from graph construction, unblocking `test_invalid_rows_routed_to_quarantine_sink`.

**Architecture:** ELSPETH's execution graph models the happy-path data flow (Source → Transforms → Sinks). Sinks that receive data via runtime routing — quarantine sinks (source `_on_validation_failure`), transform error sinks (`_on_error`), and export sinks — bypass the DAG entirely. Currently, quarantine sinks are added as graph nodes with no incoming edges, causing `GraphValidationError: unreachable node`. The fix extracts a helper function that filters non-DAG sinks before graph construction, applied at all 4 call sites in `cli.py`. The full sink set remains in `PipelineConfig.sinks` for runtime access.

**Tech Stack:** Python, NetworkX (DAG), Pydantic (config), pluggy (plugins)

**Beads Issue:** `elspeth-rapid-a3pu`

**Future Direction:** This is a tactical fix. When true multipath DAG support is added (error/quarantine edges as first-class graph edges with routing_events audit trail), this exclusion logic will be replaced by proper edge modeling. This fix is designed to be easy to remove when that happens.

**KNOWN ISSUE (discovered during planning):** The SinkExecutor needs `sink_id_map[SinkName(sink_name)]` to get node_ids for creating `node_states` and `token_outcomes` in the audit trail (orchestrator/core.py:281). If quarantine sinks are excluded from the graph, there's no node_id, and writing quarantine tokens crashes with `KeyError`. **This plan requires an additional task** to generate and register node_ids for excluded sinks outside the graph (or merge them into `sink_id_map` manually). See the alternative plan `2026-02-06-quarantine-sink-multipath-edges.md` which avoids this problem by keeping sinks in the graph with divert edges.

---

## Context for the Implementer

### Why this happens

The `ExecutionGraph.from_plugin_instances()` method (in `src/elspeth/core/dag.py:352`) receives a `sinks` dict and adds **every sink** as a graph node (lines 432-443). The graph validator then checks that all nodes are reachable from the source (lines 225-240). Quarantine sinks have no incoming edges because they receive data directly from the source iteration loop in the orchestrator (`src/elspeth/engine/orchestrator/core.py:1190-1246`), not through DAG traversal.

### Existing precedent

The `run` command already excludes export sinks from graph construction at `cli.py:416-419`:

```python
execution_sinks = plugins["sinks"]
if config.landscape.export.enabled and config.landscape.export.sink:
    export_sink_name = config.landscape.export.sink
    execution_sinks = {k: v for k, v in plugins["sinks"].items() if k != export_sink_name}
```

### Three categories of non-DAG sinks

| Sink Type | Config Source | Currently Excluded? |
|-----------|-------------|-------------------|
| Export sink | `config.landscape.export.sink` | Yes (run command only) |
| Quarantine sink | `source._on_validation_failure` | **No — this is the bug** |
| Transform error sink | `transform._on_error` | **No — latent bug** |

### Edge case: shared sinks

A sink could theoretically serve dual purposes (e.g., `on_validation_failure: "default"` where "default" is also the default output sink). In this case, the sink IS reachable through DAG edges and must NOT be excluded. The helper function must check whether a non-DAG sink is also DAG-reachable before excluding it.

---

## Task 1: Add `_get_dag_sinks` helper function

**Files:**
- Modify: `src/elspeth/cli_helpers.py` (add new function)
- Test: `tests/unit/test_cli_helpers.py` (or create if needed)

### Step 1: Write failing tests for the helper

Create tests in `tests/unit/test_cli_helpers.py`. If the file doesn't exist, create it.

```python
"""Tests for _get_dag_sinks helper function."""

from unittest.mock import MagicMock

import pytest

from elspeth.cli_helpers import _get_dag_sinks


def _make_source(on_validation_failure: str = "discard") -> MagicMock:
    """Create a mock source with _on_validation_failure."""
    source = MagicMock()
    source._on_validation_failure = on_validation_failure
    return source


def _make_transform(on_error: str | None = None, is_gate: bool = False) -> MagicMock:
    """Create a mock transform with _on_error."""
    if is_gate:
        # Gates don't have _on_error
        from elspeth.plugins.protocols import GateProtocol
        transform = MagicMock(spec=GateProtocol)
    else:
        from elspeth.plugins.protocols import TransformProtocol
        transform = MagicMock(spec=TransformProtocol)
        transform._on_error = on_error
    return transform


def _make_sink(name: str) -> MagicMock:
    """Create a mock sink."""
    sink = MagicMock()
    sink.name = name
    return sink


class TestGetDagSinks:
    """Tests for _get_dag_sinks: filtering non-DAG sinks from graph construction."""

    def test_no_exclusions_when_all_discard(self) -> None:
        """When source uses 'discard' and no error sinks, all sinks pass through."""
        sinks = {"default": _make_sink("default"), "extra": _make_sink("extra")}
        source = _make_source("discard")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[],
            default_sink="default",
            gate_route_targets=set(),
            export_sink=None,
        )
        assert set(result.keys()) == {"default", "extra"}

    def test_quarantine_sink_excluded(self) -> None:
        """Quarantine sink is excluded when it's not a DAG sink."""
        sinks = {
            "default": _make_sink("default"),
            "quarantine": _make_sink("quarantine"),
        }
        source = _make_source("quarantine")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[],
            default_sink="default",
            gate_route_targets=set(),
            export_sink=None,
        )
        assert set(result.keys()) == {"default"}

    def test_quarantine_sink_kept_when_also_default(self) -> None:
        """If quarantine destination is also the default sink, it stays in graph."""
        sinks = {"output": _make_sink("output")}
        source = _make_source("output")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[],
            default_sink="output",
            gate_route_targets=set(),
            export_sink=None,
        )
        assert set(result.keys()) == {"output"}

    def test_quarantine_sink_kept_when_gate_routes_to_it(self) -> None:
        """If quarantine sink is also a gate route target, it stays in graph."""
        sinks = {
            "default": _make_sink("default"),
            "quarantine": _make_sink("quarantine"),
        }
        source = _make_source("quarantine")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[],
            default_sink="default",
            gate_route_targets={"quarantine"},
            export_sink=None,
        )
        assert set(result.keys()) == {"default", "quarantine"}

    def test_transform_error_sink_excluded(self) -> None:
        """Transform on_error sink is excluded when not a DAG sink."""
        sinks = {
            "default": _make_sink("default"),
            "errors": _make_sink("errors"),
        }
        source = _make_source("discard")
        transform = _make_transform(on_error="errors")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[transform],
            default_sink="default",
            gate_route_targets=set(),
            export_sink=None,
        )
        assert set(result.keys()) == {"default"}

    def test_export_sink_excluded(self) -> None:
        """Export sink is excluded from graph."""
        sinks = {
            "default": _make_sink("default"),
            "audit_export": _make_sink("audit_export"),
        }
        source = _make_source("discard")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[],
            default_sink="default",
            gate_route_targets=set(),
            export_sink="audit_export",
        )
        assert set(result.keys()) == {"default"}

    def test_multiple_exclusions(self) -> None:
        """Multiple non-DAG sinks excluded simultaneously."""
        sinks = {
            "default": _make_sink("default"),
            "quarantine": _make_sink("quarantine"),
            "errors": _make_sink("errors"),
            "audit_export": _make_sink("audit_export"),
        }
        source = _make_source("quarantine")
        transform = _make_transform(on_error="errors")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[transform],
            default_sink="default",
            gate_route_targets=set(),
            export_sink="audit_export",
        )
        assert set(result.keys()) == {"default"}

    def test_gate_protocols_skipped_for_on_error(self) -> None:
        """GateProtocol transforms don't have _on_error and are skipped."""
        sinks = {"default": _make_sink("default")}
        source = _make_source("discard")
        gate = _make_transform(is_gate=True)
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[gate],
            default_sink="default",
            gate_route_targets=set(),
            export_sink=None,
        )
        assert set(result.keys()) == {"default"}

    def test_discard_on_error_does_not_exclude(self) -> None:
        """on_error='discard' is not a sink name and doesn't exclude anything."""
        sinks = {
            "default": _make_sink("default"),
            "discard": _make_sink("discard"),  # Unlikely but test the edge case
        }
        source = _make_source("discard")
        transform = _make_transform(on_error="discard")
        result = _get_dag_sinks(
            all_sinks=sinks,
            source=source,
            transforms=[transform],
            default_sink="default",
            gate_route_targets=set(),
            export_sink=None,
        )
        # "discard" is a special keyword, not a sink reference — both sinks stay
        assert set(result.keys()) == {"default", "discard"}
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/unit/test_cli_helpers.py -v`
Expected: FAIL with `ImportError: cannot import name '_get_dag_sinks'`

### Step 3: Implement `_get_dag_sinks` in `cli_helpers.py`

Add to `src/elspeth/cli_helpers.py`:

```python
def _get_dag_sinks(
    all_sinks: dict[str, "SinkProtocol"],
    source: "SourceProtocol",
    transforms: list["TransformProtocol | GateProtocol"],
    default_sink: str,
    gate_route_targets: set[str],
    export_sink: str | None,
) -> dict[str, "SinkProtocol"]:
    """Filter sinks to only those participating in DAG execution.

    Non-DAG sinks receive data via runtime routing (not graph edges):
    - Quarantine sinks: source._on_validation_failure routes invalid rows directly
    - Error sinks: transform._on_error routes failed rows directly
    - Export sinks: receive audit data post-run, not pipeline data

    A sink is excluded ONLY if it's exclusively non-DAG. If it's also referenced
    as default_sink or a gate route target, it stays in the graph.

    Args:
        all_sinks: Complete sink dict from plugin instantiation
        source: Source plugin (for _on_validation_failure)
        transforms: Transform plugins (for _on_error)
        default_sink: Default sink name (always DAG-reachable)
        gate_route_targets: Sink names referenced by gate routes (DAG-reachable)
        export_sink: Export sink name if enabled, None otherwise

    Returns:
        Filtered sink dict containing only DAG-participating sinks
    """
    from elspeth.plugins.protocols import TransformProtocol

    # Sinks reachable through DAG edges — never exclude these
    dag_reachable = {default_sink} | gate_route_targets

    # Collect candidate exclusions
    exclude: set[str] = set()

    # Source quarantine sink
    quarantine_dest = source._on_validation_failure
    if quarantine_dest != "discard":
        exclude.add(quarantine_dest)

    # Transform error sinks
    for transform in transforms:
        if isinstance(transform, TransformProtocol) and transform._on_error:
            if transform._on_error != "discard":
                exclude.add(transform._on_error)

    # Export sink
    if export_sink:
        exclude.add(export_sink)

    # Only exclude sinks that are NOT also DAG-reachable
    final_exclude = exclude - dag_reachable

    return {k: v for k, v in all_sinks.items() if k not in final_exclude}
```

### Step 4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/unit/test_cli_helpers.py::TestGetDagSinks -v`
Expected: all 9 tests PASS

### Step 5: Commit

```bash
git add tests/unit/test_cli_helpers.py src/elspeth/cli_helpers.py
git commit -m "feat: add _get_dag_sinks helper to exclude non-DAG sinks from graph"
```

---

## Task 2: Compute `gate_route_targets` helper

The `_get_dag_sinks` helper needs `gate_route_targets` — the set of sink names referenced by gate routes. This information is available from both config-driven gates (`config.gates`) and plugin gates (GateProtocol instances in transforms list).

**Files:**
- Modify: `src/elspeth/cli_helpers.py` (add helper)
- Test: `tests/unit/test_cli_helpers.py` (add tests)

### Step 1: Write failing tests

Add to `tests/unit/test_cli_helpers.py`:

```python
from elspeth.cli_helpers import _collect_gate_route_targets


class TestCollectGateRouteTargets:
    """Tests for _collect_gate_route_targets."""

    def test_no_gates(self) -> None:
        """No gates means no route targets."""
        result = _collect_gate_route_targets(config_gates=[], transforms=[])
        assert result == set()

    def test_config_gate_routes(self) -> None:
        """Config gates contribute route targets."""
        gate = MagicMock()
        gate.routes = {"suspicious": "review", "clean": "continue"}
        gate.fork_to = None
        result = _collect_gate_route_targets(config_gates=[gate], transforms=[])
        assert result == {"review"}

    def test_config_gate_fork_to_sink(self) -> None:
        """Fork branches matching sink names are included."""
        gate = MagicMock()
        gate.routes = {"match": "fork"}
        gate.fork_to = ["branch_a", "branch_b"]
        # fork_to branches that match sink names are treated as sink targets
        # (actual matching happens in from_plugin_instances, here we just collect)
        result = _collect_gate_route_targets(config_gates=[gate], transforms=[])
        assert result == {"branch_a", "branch_b"}

    def test_plugin_gate_routes(self) -> None:
        """Plugin gates contribute route targets."""
        from elspeth.plugins.protocols import GateProtocol
        gate = MagicMock(spec=GateProtocol)
        gate.routes = {"high_risk": "escalation"}
        gate.fork_to = None
        result = _collect_gate_route_targets(config_gates=[], transforms=[gate])
        assert result == {"escalation"}

    def test_continue_and_fork_filtered(self) -> None:
        """'continue' and 'fork' are not sink names."""
        gate = MagicMock()
        gate.routes = {"true": "continue", "false": "reject", "maybe": "fork"}
        gate.fork_to = None
        result = _collect_gate_route_targets(config_gates=[gate], transforms=[])
        assert result == {"reject"}
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/unit/test_cli_helpers.py::TestCollectGateRouteTargets -v`
Expected: FAIL with `ImportError`

### Step 3: Implement

Add to `src/elspeth/cli_helpers.py`:

```python
def _collect_gate_route_targets(
    config_gates: list[Any],
    transforms: list[Any],
) -> set[str]:
    """Collect all sink names referenced by gate routes.

    These sinks are DAG-reachable (gates create edges to them) and must not
    be excluded from graph construction.

    Args:
        config_gates: Config-driven gate settings (GateSettings)
        transforms: Transform plugins (may include GateProtocol instances)

    Returns:
        Set of sink names that are gate route targets
    """
    from elspeth.plugins.protocols import GateProtocol

    targets: set[str] = set()

    # Config-driven gates
    for gate in config_gates:
        for target in gate.routes.values():
            if target not in ("continue", "fork"):
                targets.add(target)
        if gate.fork_to:
            targets.update(gate.fork_to)

    # Plugin gates (GateProtocol instances in transforms list)
    for transform in transforms:
        if isinstance(transform, GateProtocol):
            for target in transform.routes.values():
                if target not in ("continue", "fork"):
                    targets.add(target)
            if transform.fork_to:
                targets.update(transform.fork_to)

    return targets
```

### Step 4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/unit/test_cli_helpers.py::TestCollectGateRouteTargets -v`
Expected: all 5 tests PASS

### Step 5: Commit

```bash
git add tests/unit/test_cli_helpers.py src/elspeth/cli_helpers.py
git commit -m "feat: add _collect_gate_route_targets helper for DAG sink filtering"
```

---

## Task 3: Apply `_get_dag_sinks` at all 4 CLI call sites

Replace inline export sink filtering and add quarantine/error sink filtering at all `from_plugin_instances()` call sites.

**Files:**
- Modify: `src/elspeth/cli.py:412-430` (run command)
- Modify: `src/elspeth/cli.py:1111-1121` (validate command)
- Modify: `src/elspeth/cli.py:1580-1607` (`_build_validation_graph`)
- Modify: `src/elspeth/cli.py:1610-1639` (`_build_execution_graph`)

### Step 1: Update `run` command (cli.py:412-430)

Replace the existing export sink filtering with the unified helper.

**Before (lines 413-430):**
```python
    # NEW: Build and validate graph from plugin instances
    # Exclude export sink from graph - it's used post-run, not during pipeline execution.
    # The export sink receives audit records after the run completes, not pipeline data.
    execution_sinks = plugins["sinks"]
    if config.landscape.export.enabled and config.landscape.export.sink:
        export_sink_name = config.landscape.export.sink
        execution_sinks = {k: v for k, v in plugins["sinks"].items() if k != export_sink_name}

    try:
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=execution_sinks,
            ...
```

**After:**
```python
    # Filter sinks to DAG-participating only (excludes quarantine, error, export sinks)
    from elspeth.cli_helpers import _collect_gate_route_targets, _get_dag_sinks

    gate_route_targets = _collect_gate_route_targets(
        config_gates=list(config.gates),
        transforms=plugins["transforms"],
    )
    export_sink = config.landscape.export.sink if config.landscape.export.enabled else None
    dag_sinks = _get_dag_sinks(
        all_sinks=plugins["sinks"],
        source=plugins["source"],
        transforms=plugins["transforms"],
        default_sink=config.default_sink,
        gate_route_targets=gate_route_targets,
        export_sink=export_sink,
    )

    try:
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=dag_sinks,
            ...
```

### Step 2: Update `validate` command (cli.py:1111-1121)

**Before:**
```python
    # Build and validate graph from plugin instances
    try:
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            ...
```

**After:**
```python
    # Filter sinks to DAG-participating only
    from elspeth.cli_helpers import _collect_gate_route_targets, _get_dag_sinks

    gate_route_targets = _collect_gate_route_targets(
        config_gates=list(config.gates),
        transforms=plugins["transforms"],
    )
    export_sink = config.landscape.export.sink if config.landscape.export.enabled else None
    dag_sinks = _get_dag_sinks(
        all_sinks=plugins["sinks"],
        source=plugins["source"],
        transforms=plugins["transforms"],
        default_sink=config.default_sink,
        gate_route_targets=gate_route_targets,
        export_sink=export_sink,
    )

    # Build and validate graph from plugin instances
    try:
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=dag_sinks,
            ...
```

### Step 3: Update `_build_validation_graph` (cli.py:1580-1607)

**Before:**
```python
def _build_validation_graph(settings_config: ElspethSettings) -> ExecutionGraph:
    ...
    plugins = instantiate_plugins_from_config(settings_config)

    graph = ExecutionGraph.from_plugin_instances(
        source=plugins["source"],
        transforms=plugins["transforms"],
        sinks=plugins["sinks"],
        ...
```

**After:**
```python
def _build_validation_graph(settings_config: ElspethSettings) -> ExecutionGraph:
    ...
    plugins = instantiate_plugins_from_config(settings_config)

    # Filter sinks to DAG-participating only
    gate_route_targets = _collect_gate_route_targets(
        config_gates=list(settings_config.gates),
        transforms=plugins["transforms"],
    )
    export_sink = settings_config.landscape.export.sink if settings_config.landscape.export.enabled else None
    dag_sinks = _get_dag_sinks(
        all_sinks=plugins["sinks"],
        source=plugins["source"],
        transforms=plugins["transforms"],
        default_sink=settings_config.default_sink,
        gate_route_targets=gate_route_targets,
        export_sink=export_sink,
    )

    graph = ExecutionGraph.from_plugin_instances(
        source=plugins["source"],
        transforms=plugins["transforms"],
        sinks=dag_sinks,
        ...
```

### Step 4: Update `_build_execution_graph` (cli.py:1610-1639)

Same pattern. Note: `resume_plugins["source"]` is `NullSource` which has `_on_validation_failure = "discard"`, so it won't exclude anything. But the pattern should be consistent.

**After:**
```python
def _build_execution_graph(settings_config: ElspethSettings) -> ExecutionGraph:
    ...
    plugins = instantiate_plugins_from_config(settings_config)
    null_source = NullSource({})
    resume_plugins = {**plugins, "source": null_source}

    # Filter sinks to DAG-participating only
    gate_route_targets = _collect_gate_route_targets(
        config_gates=list(settings_config.gates),
        transforms=resume_plugins["transforms"],
    )
    export_sink = settings_config.landscape.export.sink if settings_config.landscape.export.enabled else None
    dag_sinks = _get_dag_sinks(
        all_sinks=resume_plugins["sinks"],
        source=resume_plugins["source"],
        transforms=resume_plugins["transforms"],
        default_sink=settings_config.default_sink,
        gate_route_targets=gate_route_targets,
        export_sink=export_sink,
    )

    graph = ExecutionGraph.from_plugin_instances(
        source=resume_plugins["source"],
        transforms=resume_plugins["transforms"],
        sinks=dag_sinks,
        ...
```

### Step 5: Run the failing integration test

Run: `.venv/bin/python -m pytest tests/integration/test_cli_integration.py::TestSourceQuarantineRouting -v`
Expected: both tests PASS (quarantine routing and discard)

### Step 6: Run full test suite

Run: `.venv/bin/python -m pytest tests/ -x --timeout=60`
Expected: no regressions

### Step 7: Commit

```bash
git add src/elspeth/cli.py
git commit -m "fix: exclude quarantine/error sinks from DAG graph construction

Quarantine sinks (source on_validation_failure) and transform error sinks
(on_error) receive data via runtime routing, not DAG edges. They must be
in PipelineConfig.sinks for runtime access but excluded from the execution
graph to avoid unreachable-node validation failures.

Follows the existing pattern for export sinks but centralizes all non-DAG
sink filtering into _get_dag_sinks helper.

Fixes: elspeth-rapid-a3pu"
```

---

## Task 4: Add integration test for dedicated transform error sink

The quarantine sink bug also applies to dedicated transform `on_error` sinks — if a sink is ONLY used for transform error routing (not a gate route or default sink), it would also cause an unreachable node error. This is a latent bug. Add a test that exercises this path.

**Files:**
- Modify: `tests/integration/test_cli_integration.py` (add test class)

### Step 1: Add integration test

Add after the `TestSourceQuarantineRouting` class:

```python
class TestTransformErrorSinkRouting:
    """Integration test for dedicated transform error sinks.

    Verifies that a sink referenced ONLY by transform on_error (not by gates
    or as default_sink) does not break DAG validation.
    """

    @pytest.fixture
    def error_sink_pipeline_config(self, tmp_path: Path) -> Path:
        """Create pipeline with a dedicated error sink for transform failures."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,text\n1,hello\n2,world\n")

        config = {
            "source": {
                "plugin": "csv",
                "options": {
                    "path": str(csv_file),
                    "schema": {"mode": "observed"},
                },
            },
            "transforms": [
                {
                    "plugin": "truncate",
                    "options": {
                        "field": "text",
                        "max_length": 3,
                        "on_error": "errors",
                        "schema": {"mode": "observed"},
                    },
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
            "landscape": {"url": f"sqlite:///{tmp_path / 'landscape.db'}"},
        }
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(yaml.dump(config))
        return config_file

    def test_dedicated_error_sink_does_not_break_graph(
        self, error_sink_pipeline_config: Path, tmp_path: Path
    ) -> None:
        """A sink only referenced by on_error must not break DAG validation."""
        from elspeth.cli import app

        result = runner.invoke(app, ["run", "-s", str(error_sink_pipeline_config), "--execute"])
        assert result.exit_code == 0, f"Pipeline failed: {result.output}"

        # Valid rows should reach default output
        output_file = tmp_path / "output.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert len(data) == 2
```

### Step 2: Run the test

Run: `.venv/bin/python -m pytest tests/integration/test_cli_integration.py::TestTransformErrorSinkRouting -v`
Expected: PASS (because Task 3 already filters error sinks)

### Step 3: Commit

```bash
git add tests/integration/test_cli_integration.py
git commit -m "test: add integration test for dedicated transform error sink in graph"
```

---

## Task 5: Close beads issue and verify

### Step 1: Run full test suite

Run: `.venv/bin/python -m pytest tests/ --timeout=60`
Expected: all tests pass, including `test_invalid_rows_routed_to_quarantine_sink`

### Step 2: Close beads issue

```bash
bd close elspeth-rapid-a3pu --reason="Fixed by excluding non-DAG sinks from graph construction"
bd sync
```

### Step 3: Final commit (if any cleanup needed)

```bash
git status
# Stage and commit any remaining changes
```

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Shared sink excluded incorrectly (quarantine sink = default sink) | Low | `_get_dag_sinks` checks `dag_reachable` set before excluding |
| Resume path breaks (different source type) | Low | NullSource has `_on_validation_failure = "discard"`, no exclusion |
| Existing tests regress | Low | No tests use quarantine sinks in graph construction (they all use inline configs) |
| Transform `on_error` test uses a plugin that doesn't support `on_error` | Medium | Verify `truncate` transform supports `on_error` before test; adjust plugin if needed |

## Future Work

When true multipath DAG support is added:
- Remove `_get_dag_sinks` helper
- Add `RoutingMode.ERROR` and `RoutingMode.QUARANTINE` edge types
- Create edges from source → quarantine sink and transform → error sink in `from_plugin_instances()`
- Record `routing_events` for quarantine/error writes (audit trail improvement)
- Update graph validation to understand error/quarantine edges
