# Sink Failsink Part 2: Engine & Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the failsink infrastructure from Part 1 into the engine: SinkExecutor handles diversions, config validation enforces failsink rules, DAG builder creates DIVERT edges, orchestrator injects `_on_write_failure` and resolves failsink references, and ChromaSink migrates its inline filtering to `_divert_row()`.

**Architecture:** SinkExecutor reads `SinkWriteResult.diversions` after `write()`, writes diverted rows to the failsink (or records discard), and records per-token `DIVERTED` outcomes. The orchestrator resolves failsink references at graph-build time and passes them to the executor. ChromaSink's inline metadata filtering is replaced with `_divert_row()` calls.

**Tech Stack:** Python, SQLAlchemy Core (audit trail), pytest, Hypothesis (property tests).

**Spec:** `docs/superpowers/specs/2026-03-26-sink-failsink-design.md`

**Depends on:** Part 1 (contracts & infrastructure) — all types, enums, config fields, BaseSink plumbing, and sink return type migration must be complete.

---

### Task 1: Config validation — validate_sink_failsink_destinations()

**Files:**
- Modify: `src/elspeth/engine/orchestrator/validation.py`
- Create: `tests/unit/engine/test_failsink_validation.py`

- [ ] **Step 1: Write tests for failsink config validation**

```python
# tests/unit/engine/test_failsink_validation.py
"""Tests for sink failsink destination validation."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from elspeth.engine.orchestrator.types import RouteValidationError
from elspeth.engine.orchestrator.validation import validate_sink_failsink_destinations


def _stub(on_write_failure: str) -> SimpleNamespace:
    """Minimal stub with on_write_failure attribute."""
    return SimpleNamespace(on_write_failure=on_write_failure)


class TestValidateSinkFailsinkDestinations:
    def test_discard_always_valid(self) -> None:
        """on_write_failure='discard' needs no target sink."""
        validate_sink_failsink_destinations(
            sink_configs={"output": _stub("discard")},
            available_sinks={"output"},
            sink_plugins={"output": "chroma_sink"},
        )  # No error raised

    def test_valid_failsink_reference(self) -> None:
        validate_sink_failsink_destinations(
            sink_configs={
                "output": _stub("csv_failsink"),
                "csv_failsink": _stub("discard"),
            },
            available_sinks={"output", "csv_failsink"},
            sink_plugins={"output": "chroma_sink", "csv_failsink": "csv"},
        )  # No error raised

    def test_json_failsink_valid(self) -> None:
        validate_sink_failsink_destinations(
            sink_configs={
                "output": _stub("json_failsink"),
                "json_failsink": _stub("discard"),
            },
            available_sinks={"output", "json_failsink"},
            sink_plugins={"output": "database", "json_failsink": "json"},
        )  # No error raised

    def test_xml_failsink_valid(self) -> None:
        validate_sink_failsink_destinations(
            sink_configs={
                "output": _stub("xml_failsink"),
                "xml_failsink": _stub("discard"),
            },
            available_sinks={"output", "xml_failsink"},
            sink_plugins={"output": "database", "xml_failsink": "xml"},
        )  # No error raised

    def test_unknown_failsink_raises(self) -> None:
        with pytest.raises(RouteValidationError, match="nonexistent"):
            validate_sink_failsink_destinations(
                sink_configs={"output": _stub("nonexistent")},
                available_sinks={"output"},
                sink_plugins={"output": "chroma_sink"},
            )

    def test_non_file_failsink_raises(self) -> None:
        """Failsink must be csv, json, or xml."""
        with pytest.raises(RouteValidationError, match="csv, json, or xml"):
            validate_sink_failsink_destinations(
                sink_configs={
                    "output": _stub("db_sink"),
                    "db_sink": _stub("discard"),
                },
                available_sinks={"output", "db_sink"},
                sink_plugins={"output": "chroma_sink", "db_sink": "database"},
            )

    def test_chroma_as_failsink_raises(self) -> None:
        """ChromaSink is not a valid failsink plugin type."""
        with pytest.raises(RouteValidationError, match="csv, json, or xml"):
            validate_sink_failsink_destinations(
                sink_configs={
                    "output": _stub("chroma_backup"),
                    "chroma_backup": _stub("discard"),
                },
                available_sinks={"output", "chroma_backup"},
                sink_plugins={"output": "csv", "chroma_backup": "chroma_sink"},
            )

    def test_failsink_chaining_raises(self) -> None:
        """Failsink targets must have on_write_failure='discard' (no chains)."""
        with pytest.raises(RouteValidationError, match="discard"):
            validate_sink_failsink_destinations(
                sink_configs={
                    "output": _stub("failsink1"),
                    "failsink1": _stub("failsink2"),
                    "failsink2": _stub("discard"),
                },
                available_sinks={"output", "failsink1", "failsink2"},
                sink_plugins={"output": "chroma_sink", "failsink1": "csv", "failsink2": "csv"},
            )

    def test_self_reference_raises(self) -> None:
        """A sink cannot reference itself as failsink."""
        with pytest.raises(RouteValidationError, match="itself"):
            validate_sink_failsink_destinations(
                sink_configs={"output": _stub("output")},
                available_sinks={"output"},
                sink_plugins={"output": "csv"},
            )

    def test_multiple_sinks_mixed_valid(self) -> None:
        """Multiple sinks: some with failsink, some with discard."""
        validate_sink_failsink_destinations(
            sink_configs={
                "chroma_out": _stub("csv_fail"),
                "db_out": _stub("discard"),
                "csv_fail": _stub("discard"),
            },
            available_sinks={"chroma_out", "db_out", "csv_fail"},
            sink_plugins={"chroma_out": "chroma_sink", "db_out": "database", "csv_fail": "csv"},
        )  # No error raised

    def test_all_discard(self) -> None:
        """All sinks using discard — valid."""
        validate_sink_failsink_destinations(
            sink_configs={
                "sink_a": _stub("discard"),
                "sink_b": _stub("discard"),
            },
            available_sinks={"sink_a", "sink_b"},
            sink_plugins={"sink_a": "csv", "sink_b": "json"},
        )  # No error raised
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_failsink_validation.py -v`
Expected: `ImportError: cannot import name 'validate_sink_failsink_destinations'`

- [ ] **Step 3: Implement validate_sink_failsink_destinations()**

In `src/elspeth/engine/orchestrator/validation.py`, add after the existing `validate_source_quarantine_destination()` function:

```python
_ALLOWED_FAILSINK_PLUGINS = frozenset({"csv", "json", "xml"})


def validate_sink_failsink_destinations(
    sink_configs: Mapping[str, Any],
    available_sinks: set[str],
    sink_plugins: Mapping[str, str],
    allowed_failsink_plugins: frozenset[str] = _ALLOWED_FAILSINK_PLUGINS,
) -> None:
    """Validate all sink on_write_failure destinations.

    Called at pipeline initialization, before any rows are processed.
    Parallel to validate_transform_error_sinks() for transform on_error.

    Rules:
    1. 'discard' is always valid
    2. Sink name must exist in available_sinks
    3. Sink cannot reference itself
    4. Target sink must use csv, json, or xml plugin type
    5. Target sink must have on_write_failure='discard' (no chains)

    Args:
        sink_configs: Dict of sink_name -> config object with on_write_failure attr.
        available_sinks: Set of all sink names in the pipeline.
        sink_plugins: Dict of sink_name -> plugin type name (e.g., "csv", "chroma_sink").
        allowed_failsink_plugins: Set of plugin types allowed as failsinks.

    Raises:
        RouteValidationError: If any sink's on_write_failure is invalid.
    """
    for sink_name, config in sink_configs.items():
        dest = config.on_write_failure
        if dest == "discard":
            continue

        # Rule 2: must exist
        if dest not in available_sinks:
            raise RouteValidationError(
                f"Sink '{sink_name}' on_write_failure references unknown sink '{dest}'. "
                f"Available sinks: {sorted(available_sinks)}."
            )

        # Rule 3: no self-reference
        if dest == sink_name:
            raise RouteValidationError(
                f"Sink '{sink_name}' on_write_failure references itself. "
                f"A sink cannot be its own failsink."
            )

        # Rule 4: must be a file sink
        if dest in sink_plugins:
            plugin_type = sink_plugins[dest]
            if plugin_type not in allowed_failsink_plugins:
                raise RouteValidationError(
                    f"Sink '{sink_name}' on_write_failure references '{dest}' "
                    f"(plugin='{plugin_type}'), but failsinks must use csv, json, or xml plugins."
                )

        # Rule 5: no chains — target must use 'discard'
        if dest in sink_configs:
            target_dest = sink_configs[dest].on_write_failure
            if target_dest != "discard":
                raise RouteValidationError(
                    f"Sink '{sink_name}' on_write_failure references '{dest}', "
                    f"but '{dest}' has on_write_failure='{target_dest}'. "
                    f"Failsink targets must have on_write_failure='discard' (no chains)."
                )
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_failsink_validation.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/engine/orchestrator/validation.py tests/unit/engine/test_failsink_validation.py
git commit -m "feat(validation): add validate_sink_failsink_destinations()"
```

---

### Task 2: DAG builder __failsink__ DIVERT edges

**Files:**
- Modify: `src/elspeth/core/dag/builder.py:725-763`

- [ ] **Step 1: Write test for __failsink__ edge creation**

```python
# tests/unit/core/dag/test_failsink_edges.py
"""Test __failsink__ DIVERT edge creation in DAG builder."""
from __future__ import annotations

from elspeth.contracts.enums import RoutingMode
from elspeth.core.dag.graph import ExecutionGraph


class TestFailsinkEdges:
    def test_failsink_divert_edge_created(self, dag_with_failsink: ExecutionGraph) -> None:
        """A sink with on_write_failure creates a __failsink__ DIVERT edge."""
        edges = dag_with_failsink.get_edges()
        failsink_edges = [e for e in edges if e.label == "__failsink__"]
        assert len(failsink_edges) == 1
        assert failsink_edges[0].mode == RoutingMode.DIVERT

    def test_discard_no_failsink_edge(self, dag_with_discard: ExecutionGraph) -> None:
        """A sink with on_write_failure='discard' creates no __failsink__ edge."""
        edges = dag_with_discard.get_edges()
        failsink_edges = [e for e in edges if e.label == "__failsink__"]
        assert len(failsink_edges) == 0
```

Note: These tests require DAG construction fixtures. Use the existing `from_plugin_instances()` test patterns in `tests/unit/core/dag/`. The fixtures need a pipeline config with two sinks where one references the other via `on_write_failure`. Check existing DAG test fixtures for the pattern and create similar ones.

- [ ] **Step 2: Add __failsink__ edge creation to DAG builder**

In `src/elspeth/core/dag/builder.py`, find the end of the DIVERT edges section (around line 763, after transform error edges). The function `from_plugin_instances()` needs access to sink settings to know which sinks have `on_write_failure` configured.

Check the current signature of `from_plugin_instances()` — it receives `sinks: Mapping[SinkName, SinkProtocol]`. It needs a way to get `on_write_failure` for each sink. Options:
- Pass the sink_settings separately: `sink_settings: Mapping[str, SinkSettings]`
- Read `_on_write_failure` from the sink instance (already injected by cli_helpers in Task 3)

The simpler approach: read from the sink instance. After the transform error edges block, add:

```python
    # Sink failsink edges
    for sink_name_key, sink_node_id in sink_ids.items():
        sink_instance = sinks[sink_name_key]
        on_write_failure = getattr(sink_instance, '_on_write_failure', None)
        if on_write_failure is not None and on_write_failure != "discard":
            failsink_name = SinkName(on_write_failure)
            if failsink_name in sink_ids:
                graph.add_edge(
                    sink_node_id,
                    sink_ids[failsink_name],
                    label="__failsink__",
                    mode=RoutingMode.DIVERT,
                )
```

Note: `getattr` is used here because `_on_write_failure` may not be set yet during testing with mock sinks. This is the Tier 1 boundary where the attribute was injected by cli_helpers — `getattr` with a default is appropriate here since this code runs at graph construction time, before `_on_write_failure` is guaranteed to be present on all sink instances (test fixtures may not set it).

- [ ] **Step 3: Run tests — expect PASS**

Run: `.venv/bin/python -m pytest tests/unit/core/dag/test_failsink_edges.py -v`
Expected: All PASS.

- [ ] **Step 4: Run existing DAG tests for regression**

Run: `.venv/bin/python -m pytest tests/unit/core/dag/ -v --tb=short -q`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/core/dag/builder.py tests/unit/core/dag/test_failsink_edges.py
git commit -m "feat(dag): add __failsink__ DIVERT edges for sink failsink routing"
```

---

### Task 3: Orchestrator wiring — inject _on_write_failure + resolve failsink

**Files:**
- Modify: `src/elspeth/cli_helpers.py:107-119`
- Modify: `src/elspeth/engine/orchestrator/core.py:514-585`

- [ ] **Step 1: Inject _on_write_failure in cli_helpers.py**

In `src/elspeth/cli_helpers.py`, find the sink instantiation loop (lines 107-111):

```python
    # Instantiate sinks
    sinks = {}
    for sink_name, sink_config in config.sinks.items():
        sink_cls = manager.get_sink_by_name(sink_config.plugin)
        sinks[sink_name] = sink_cls(dict(sink_config.options))
```

Add after `sinks[sink_name] = sink_cls(dict(sink_config.options))`:

```python
        # Bridge: inject on_write_failure from settings level
        sinks[sink_name]._on_write_failure = sink_config.on_write_failure
```

- [ ] **Step 2: Pass failsink to SinkExecutor.write() in _drain_pending_tokens_to_sinks()**

In `src/elspeth/engine/orchestrator/core.py`, find `_drain_pending_tokens_to_sinks()` (line 514). Inside the loop that calls `sink_executor.write()` (around line 577), resolve the failsink before calling write:

Find:
```python
            for pending_outcome, group in groupby(sorted_pairs, key=lambda x: x[1]):
                group_tokens = [token for token, _ in group]
                sink_executor.write(
                    sink=sink,
                    tokens=group_tokens,
                    ctx=ctx,
                    step_in_pipeline=step,
                    sink_name=sink_name,
                    pending_outcome=pending_outcome,
                    on_token_written=on_token_written,
                )
```

Replace with:

```python
            # Resolve failsink reference (if configured and not 'discard')
            failsink: SinkProtocol | None = None
            on_write_failure = getattr(sink, '_on_write_failure', None)
            if on_write_failure is not None and on_write_failure != "discard":
                if on_write_failure in config.sinks:
                    failsink = config.sinks[on_write_failure]

            for pending_outcome, group in groupby(sorted_pairs, key=lambda x: x[1]):
                group_tokens = [token for token, _ in group]
                sink_executor.write(
                    sink=sink,
                    tokens=group_tokens,
                    ctx=ctx,
                    step_in_pipeline=step,
                    sink_name=sink_name,
                    pending_outcome=pending_outcome,
                    failsink=failsink,
                    on_token_written=on_token_written,
                )
```

Add `SinkProtocol` to the TYPE_CHECKING imports if not already present.

- [ ] **Step 3: Call validate_sink_failsink_destinations() at pipeline init**

Find where `validate_transform_error_sinks()` is called in the orchestrator (search for it in `core.py`). Add `validate_sink_failsink_destinations()` immediately after, with the same pattern.

You'll need to build the `sink_plugins` mapping from `config.sinks` — each sink's `.name` attribute gives the plugin type.

```python
from elspeth.engine.orchestrator.validation import validate_sink_failsink_destinations

# Build sink_plugins map for failsink validation
sink_plugins = {name: sink.name for name, sink in config.sinks.items()}
validate_sink_failsink_destinations(
    sink_configs=config_settings.sinks,  # SinkSettings objects
    available_sinks=set(config.sinks.keys()),
    sink_plugins=sink_plugins,
)
```

Note: The exact location depends on where `validate_transform_error_sinks()` is called. Search the orchestrator for that call and add alongside it.

- [ ] **Step 4: Run integration tests**

Run: `.venv/bin/python -m pytest tests/integration/ -v --tb=short -q`
Expected: All PASS (or existing failures only — integration tests may need `on_write_failure` added to their YAML fixtures).

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/cli_helpers.py src/elspeth/engine/orchestrator/core.py
git commit -m "feat(orchestrator): wire on_write_failure injection and failsink resolution"
```

---

### Task 4: SinkExecutor failsink routing

**Files:**
- Modify: `src/elspeth/engine/executors/sink.py:94-401`
- Create: `tests/unit/engine/test_sink_executor_diversion.py`

This is the most critical task. The SinkExecutor must handle per-token outcomes based on `SinkWriteResult.diversions`.

- [ ] **Step 1: Write comprehensive tests**

```python
# tests/unit/engine/test_sink_executor_diversion.py
"""Tests for SinkExecutor failsink routing.

Tests the critical path: after sink.write() returns a SinkWriteResult with
diversions, the executor must record correct per-token outcomes and write
diverted rows to the failsink (or record discard).
"""
from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.contracts.diversion import RowDiversion, SinkWriteResult
from elspeth.contracts.enums import NodeStateStatus
from elspeth.contracts.results import ArtifactDescriptor
from elspeth.engine.executors.sink import SinkExecutor


def _make_token(token_id: str = "tok-1", row_data: dict | None = None) -> MagicMock:
    """Create a minimal TokenInfo mock."""
    token = MagicMock(spec=TokenInfo)
    token.token_id = token_id
    token.row_id = f"row-{token_id}"
    mock_row = MagicMock()
    mock_row.to_dict.return_value = row_data or {"field": "value"}
    mock_row.contract = MagicMock()
    mock_row.contract.merge.return_value = mock_row.contract
    token.row_data = mock_row
    return token


def _make_artifact(path: str = "/tmp/test") -> ArtifactDescriptor:
    return ArtifactDescriptor.for_file(path=path, content_hash="a" * 64, size_bytes=100)


def _make_sink(
    name: str = "primary",
    node_id: str = "node-primary",
    diversions: tuple[RowDiversion, ...] = (),
    on_write_failure: str = "discard",
) -> MagicMock:
    sink = MagicMock()
    sink.name = name
    sink.node_id = node_id
    sink.validate_input = False
    sink.declared_required_fields = frozenset()
    sink.write.return_value = SinkWriteResult(
        artifact=_make_artifact(),
        diversions=diversions,
    )
    sink._on_write_failure = on_write_failure
    sink._reset_diversion_log = MagicMock()
    return sink


def _make_failsink(name: str = "csv_failsink", node_id: str = "node-failsink") -> MagicMock:
    failsink = MagicMock()
    failsink.name = name
    failsink.node_id = node_id
    failsink.write.return_value = SinkWriteResult(artifact=_make_artifact("/tmp/failsink"))
    return failsink


def _make_executor() -> tuple[SinkExecutor, MagicMock]:
    recorder = MagicMock()
    state_counter = [0]

    def _begin_state(**kwargs: Any) -> MagicMock:
        state_counter[0] += 1
        state = MagicMock()
        state.state_id = f"state-{state_counter[0]}"
        return state

    recorder.begin_node_state.side_effect = _begin_state
    recorder.allocate_operation_call_index = MagicMock(return_value=0)
    spans = MagicMock()
    spans.sink_span.return_value.__enter__ = MagicMock(return_value=None)
    spans.sink_span.return_value.__exit__ = MagicMock(return_value=False)
    executor = SinkExecutor(recorder, spans, "run-1")
    return executor, recorder


class TestNoDiversions:
    """Existing behavior preserved when no diversions occur."""

    def test_all_tokens_get_completed_outcome(self) -> None:
        executor, recorder = _make_executor()
        sink = _make_sink()
        tokens = [_make_token("t0"), _make_token("t1"), _make_token("t2")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert len(outcome_calls) == 3
        for c in outcome_calls:
            assert c.kwargs["outcome"] == RowOutcome.COMPLETED
            assert c.kwargs["sink_name"] == "primary"

    def test_no_failsink_write_called(self) -> None:
        executor, recorder = _make_executor()
        sink = _make_sink()
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
        )
        failsink.write.assert_not_called()


class TestDiscardMode:
    """on_write_failure='discard' — diverted rows are dropped with audit record."""

    def test_diverted_tokens_get_diverted_outcome(self) -> None:
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=1, reason="bad metadata", row_data={"x": 1}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="discard")
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert len(outcome_calls) == 2
        # t0 (index 0) → COMPLETED
        assert outcome_calls[0].kwargs["outcome"] == RowOutcome.COMPLETED
        assert outcome_calls[0].kwargs["sink_name"] == "primary"
        # t1 (index 1) → DIVERTED
        assert outcome_calls[1].kwargs["outcome"] == RowOutcome.DIVERTED
        assert outcome_calls[1].kwargs["error_hash"] is not None

    def test_all_diverted_all_get_diverted(self) -> None:
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),
            RowDiversion(row_index=1, reason="bad", row_data={"x": 2}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="discard")
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert all(c.kwargs["outcome"] == RowOutcome.DIVERTED for c in outcome_calls)


class TestFailsinkMode:
    """on_write_failure=<sink_name> — diverted rows are written to failsink."""

    def test_failsink_write_called_with_enriched_rows(self) -> None:
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=1, reason="invalid metadata", row_data={"doc": "hello"}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
        )
        # Failsink should have been called with the diverted row
        failsink.write.assert_called_once()
        failsink_rows = failsink.write.call_args[0][0]
        assert len(failsink_rows) == 1
        assert "__diversion_reason" in failsink_rows[0]
        assert failsink_rows[0]["__diversion_reason"] == "invalid metadata"
        assert failsink_rows[0]["__diverted_from"] == "primary"

    def test_failsink_flush_called(self) -> None:
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
        )
        failsink.flush.assert_called_once()

    def test_no_diversions_no_failsink_call(self) -> None:
        executor, recorder = _make_executor()
        sink = _make_sink(diversions=(), on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
        )
        failsink.write.assert_not_called()

    def test_diverted_tokens_get_failsink_sink_name(self) -> None:
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert outcome_calls[0].kwargs["sink_name"] == "csv_failsink"


class TestFailsinkErrorHandling:
    def test_failsink_write_failure_crashes(self) -> None:
        """If failsink write fails, crash — it's the last resort."""
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        failsink.write.side_effect = OSError("disk full")
        tokens = [_make_token("t0")]
        with pytest.raises(OSError, match="disk full"):
            executor.write(
                sink=sink,
                tokens=tokens,
                ctx=MagicMock(run_id="run-1"),
                step_in_pipeline=5,
                sink_name="primary",
                pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
                failsink=failsink,
            )
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_sink_executor_diversion.py -v`
Expected: FAIL — SinkExecutor doesn't handle SinkWriteResult diversions yet.

- [ ] **Step 3: Modify SinkExecutor.write() to handle diversions**

In `src/elspeth/engine/executors/sink.py`:

Add imports at top:
```python
from datetime import UTC, datetime
from elspeth.contracts.diversion import RowDiversion, SinkWriteResult
from elspeth.contracts.enums import RowOutcome
```

Add `failsink` parameter to `write()` signature (line 94):
```python
    def write(
        self,
        sink: SinkProtocol,
        tokens: list[TokenInfo],
        ctx: PluginContext,
        step_in_pipeline: int,
        *,
        sink_name: str,
        pending_outcome: PendingOutcome,
        failsink: SinkProtocol | None = None,
        on_token_written: Callable[[TokenInfo], None] | None = None,
    ) -> Artifact | None:
```

After `sink.write(rows, ctx)` (line 278), extract the SinkWriteResult:
```python
                    write_result = sink.write(rows, ctx)
                    # Handle both SinkWriteResult and legacy ArtifactDescriptor
                    if isinstance(write_result, SinkWriteResult):
                        artifact_info = write_result.artifact
                        diversions = write_result.diversions
                    else:
                        artifact_info = write_result
                        diversions = ()
                    duration_ms = (time.perf_counter() - start) * 1000
```

Build the diverted index set after flush:
```python
            diverted_indices: set[int] = {d.row_index for d in diversions}
```

In the token state completion loop (line 329), check per-token:
```python
            per_token_ms = duration_ms / len(tokens)
            for idx, (token, state) in enumerate(states):
                if idx in diverted_indices:
                    # Diverted tokens: complete state but don't record artifact
                    self._recorder.complete_node_state(
                        state_id=state.state_id,
                        status=NodeStateStatus.COMPLETED,
                        output_data={"diverted": True, "reason": next(d.reason for d in diversions if d.row_index == idx)},
                        duration_ms=per_token_ms,
                    )
                else:
                    # Normal tokens: complete with artifact reference
                    output_dict = token.row_data.to_dict()
                    sink_output = {
                        "row": output_dict,
                        "artifact_path": artifact_info.path_or_uri,
                        "content_hash": artifact_info.content_hash,
                    }
                    self._recorder.complete_node_state(
                        state_id=state.state_id,
                        status=NodeStateStatus.COMPLETED,
                        output_data=sink_output,
                        duration_ms=per_token_ms,
                    )
```

After artifact registration, handle failsink writes and outcomes:
```python
        # Handle diversions: write to failsink or record discard
        if diversions:
            on_write_failure = getattr(sink, '_on_write_failure', 'discard')

            if on_write_failure != "discard" and failsink is not None:
                # Build enriched rows for failsink
                failsink_rows = []
                for d in diversions:
                    enriched = {
                        **d.row_data,
                        "__diversion_reason": d.reason,
                        "__diverted_from": sink_name,
                        "__diversion_timestamp": datetime.now(UTC).isoformat(),
                    }
                    failsink_rows.append(enriched)

                # Write to failsink — if this fails, crash (last resort)
                failsink_result = failsink.write(failsink_rows, ctx)
                failsink.flush()

                failsink_sink_name = failsink.name
            else:
                failsink_sink_name = "__discard__"

        # Record per-token outcomes
        for idx, (token, _) in enumerate(states):
            if idx in diverted_indices:
                # Find the reason for this specific diversion
                reason = next(d.reason for d in diversions if d.row_index == idx)
                error_hash = hashlib.sha256(reason.encode()).hexdigest()[:16]
                self._recorder.record_token_outcome(
                    run_id=self._run_id,
                    token_id=token.token_id,
                    outcome=RowOutcome.DIVERTED,
                    error_hash=error_hash,
                    sink_name=failsink_sink_name if diversions else sink_name,
                )
            else:
                self._recorder.record_token_outcome(
                    run_id=self._run_id,
                    token_id=token.token_id,
                    outcome=pending_outcome.outcome,
                    error_hash=pending_outcome.error_hash,
                    sink_name=sink_name,
                )
```

**Critical:** Read the full existing `write()` method before modifying. The changes must integrate into the existing error handling structure without breaking the `_complete_states_failed()` invariant. Each new code path that can raise must have a corresponding cleanup for opened node states.

- [ ] **Step 4: Run tests — expect PASS**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_sink_executor_diversion.py -v`
Expected: All 10 tests PASS.

- [ ] **Step 5: Run existing SinkExecutor tests for regression**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py -v --tb=short -q`
Expected: All PASS — existing behavior preserved when diversions is empty.

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/engine/executors/sink.py tests/unit/engine/test_sink_executor_diversion.py
git commit -m "feat(executor): add failsink routing to SinkExecutor.write()"
```

---

### Task 5: ChromaSink migration — replace inline filtering with _divert_row()

**Files:**
- Modify: `src/elspeth/plugins/sinks/chroma_sink.py:164-382`
- Modify: `tests/unit/plugins/sinks/test_chroma_sink.py`

- [ ] **Step 1: Write test for ChromaSink using _divert_row()**

```python
# Add to tests/unit/plugins/sinks/test_chroma_sink.py

class TestChromaSinkDivertRow:
    """Test ChromaSink metadata validation via _divert_row() pattern."""

    def test_invalid_metadata_diverted(self, chroma_sink_with_failsink: ChromaSink) -> None:
        """Rows with non-primitive metadata are diverted, not silently filtered."""
        rows = [
            {"doc_id": "1", "content": "hello", "topic": "valid_string"},
            {"doc_id": "2", "content": "world", "topic": {"nested": "dict"}},
        ]
        result = chroma_sink_with_failsink.write(rows, ctx=mock_ctx())
        assert isinstance(result, SinkWriteResult)
        assert len(result.diversions) == 1
        assert result.diversions[0].row_index == 1
        assert "topic" in result.diversions[0].reason

    def test_all_valid_no_diversions(self, chroma_sink_with_failsink: ChromaSink) -> None:
        """All valid rows — zero diversions."""
        rows = [
            {"doc_id": "1", "content": "hello", "topic": "valid"},
        ]
        result = chroma_sink_with_failsink.write(rows, ctx=mock_ctx())
        assert result.diversions == ()

    def test_all_invalid_all_diverted(self, chroma_sink_with_failsink: ChromaSink) -> None:
        """All rows have bad metadata — all diverted, nothing written to ChromaDB."""
        rows = [
            {"doc_id": "1", "content": "hello", "topic": [1, 2, 3]},
            {"doc_id": "2", "content": "world", "topic": {"nested": True}},
        ]
        result = chroma_sink_with_failsink.write(rows, ctx=mock_ctx())
        assert len(result.diversions) == 2
```

Note: You'll need to create a `chroma_sink_with_failsink` fixture that sets `_on_write_failure = "csv_failsink"` on the ChromaSink instance. Base it on the existing ChromaSink test fixtures.

- [ ] **Step 2: Modify ChromaSink.write() to use _divert_row()**

In `src/elspeth/plugins/sinks/chroma_sink.py`, replace the inline metadata filtering block (lines 187-218). The current code:

```python
        rejected_metadata: list[dict[str, Any]] = []
        if metadatas is not None:
            valid_indices: list[int] = []
            for i, meta in enumerate(metadatas):
                bad_fields = { ... }
                if bad_fields:
                    rejected_metadata.append({...})
                else:
                    valid_indices.append(i)
            if rejected_metadata and valid_indices:
                ids = [ids[i] for i in valid_indices]
                ...
```

Replace with:

```python
        if metadatas is not None:
            valid_ids: list[str] = []
            valid_documents: list[str] = []
            valid_metadatas: list[dict[str, Any]] = []
            for i, meta in enumerate(metadatas):
                bad_fields = {
                    key: type(value).__name__
                    for key, value in meta.items()
                    if value is not None and not isinstance(value, (str, int, float, bool))
                }
                if bad_fields:
                    self._divert_row(
                        rows[i],
                        row_index=i,
                        reason=f"Invalid ChromaDB metadata types: {bad_fields}",
                    )
                else:
                    valid_ids.append(ids[i])
                    valid_documents.append(documents[i])
                    valid_metadatas.append(meta)
            ids = valid_ids
            documents = valid_documents
            metadatas = valid_metadatas if valid_metadatas else None
```

Also remove the `rejected_metadata` and `rows_rejected_metadata` variables and their usage throughout the rest of `write()` — they're replaced by `self._get_diversions()`.

Update the return statements to use `SinkWriteResult`:
```python
        return SinkWriteResult(
            artifact=ArtifactDescriptor.for_database(...),
            diversions=self._get_diversions(),
        )
```

- [ ] **Step 3: Remove stale rejected_metadata references from audit recording**

The existing code records `rejected_metadata_detail` in `ctx.record_call()` response_data. This is replaced by the diversion log. Clean up all references to `rejected_metadata`, `rows_rejected_metadata`, and `rejected_metadata_detail` in the `write()` method.

- [ ] **Step 4: Update existing ChromaSink tests**

In `tests/unit/plugins/sinks/test_chroma_sink.py`:

- Tests in `TestChromaSinkMetadataTypeValidation` that check `response_data["rows_rejected_metadata"]` need to change to check `result.diversions`
- Tests that check `response_data["rejected_metadata_detail"]` should check `result.diversions[0].reason` instead
- All tests that assert `isinstance(result, ArtifactDescriptor)` change to `isinstance(result, SinkWriteResult)`
- All `result.content_hash` become `result.artifact.content_hash`

- [ ] **Step 5: Run ChromaSink tests — expect PASS**

Run: `.venv/bin/python -m pytest tests/unit/plugins/sinks/test_chroma_sink.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/plugins/sinks/chroma_sink.py tests/unit/plugins/sinks/test_chroma_sink.py
git commit -m "feat(chroma): migrate inline metadata filtering to _divert_row() pattern"
```

---

### Task 6: Full suite verification + CI checks

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --tb=short -q`
Expected: All PASS.

- [ ] **Step 2: Run mypy**

Run: `.venv/bin/python -m mypy src/`
Expected: PASS (or only pre-existing issues).

- [ ] **Step 3: Run ruff**

Run: `.venv/bin/python -m ruff check src/`
Expected: PASS.

- [ ] **Step 4: Run tier model enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: PASS.

- [ ] **Step 5: Run config contracts check**

Run: `.venv/bin/python -m scripts.check_contracts`
Expected: PASS.

- [ ] **Step 6: Run freeze guard enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_freeze_guards.py`
Expected: PASS — `RowDiversion` uses `freeze_fields()` correctly.

- [ ] **Step 7: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: address lint/type issues from failsink Part 2"
```

- [ ] **Step 8: Close the filigree issue**

```bash
filigree close elspeth-ad6dc0f117 --reason="Implemented: failsink pattern with _divert_row(), SinkWriteResult, DIVERTED outcome, config validation, DAG edges, ChromaSink migration"
```
