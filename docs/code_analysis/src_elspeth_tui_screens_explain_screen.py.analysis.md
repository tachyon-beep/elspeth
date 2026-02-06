# Analysis: src/elspeth/tui/screens/explain_screen.py

**Lines:** 401
**Role:** Main screen for the explain TUI. Manages screen state via a discriminated union pattern (UninitializedState / LoadingFailedState / LoadedState), loads pipeline structure from the Landscape database, handles tree node selection to update the detail panel, and provides state transition methods (load/retry/clear).
**Key dependencies:** Imports `structlog`, `sqlalchemy.exc`, `elspeth.contracts.NodeType`, `elspeth.core.landscape.LandscapeDB`, `elspeth.core.landscape.recorder.LandscapeRecorder`, `elspeth.tui.types`, `elspeth.tui.widgets.lineage_tree.LineageTree`, `elspeth.tui.widgets.node_detail.NodeDetailPanel`. Imported by `elspeth.tui.explain_app` and `elspeth.tui.screens.__init__`.
**Analysis depth:** FULL

## Summary

The file demonstrates strong architecture with its discriminated union state model and explicit state transitions. The state machine is well-tested. However, there is a significant data completeness issue: gate, aggregation, and coalesce node types are silently dropped from the lineage display. There is also a minor concern about `LandscapeRecorder` being instantiated per-call rather than once. Overall the code is well-structured with clear separation of concerns.

## Warnings

### [168-170] Gate, Aggregation, and Coalesce node types are silently dropped from lineage

**What:** The `_load_pipeline_structure` method filters nodes into three categories: `SOURCE`, `TRANSFORM`, and `SINK`. The `NodeType` enum has six values: `SOURCE`, `TRANSFORM`, `GATE`, `AGGREGATION`, `COALESCE`, and `SINK`. Nodes of type `GATE`, `AGGREGATION`, and `COALESCE` are not captured by any filter and are silently excluded from the lineage display.

**Why it matters:** If a pipeline uses gates (routing decisions), aggregations (batch collection), or coalesce (fork/join merges), these nodes will not appear in the lineage tree. This means the TUI will show an incomplete picture of the pipeline -- users investigating a pipeline with routing or aggregation will see gaps in the node chain. For an audit-focused system where "every decision must be traceable," omitting gate nodes is particularly concerning since gates represent explicit routing decisions.

**Evidence:**
```python
source_nodes = [n for n in nodes if n.node_type == NodeType.SOURCE]
transform_nodes = [n for n in nodes if n.node_type == NodeType.TRANSFORM]
sink_nodes = [n for n in nodes if n.node_type == NodeType.SINK]
# NodeType.GATE, NodeType.AGGREGATION, NodeType.COALESCE are dropped
```

### [164, 271] New LandscapeRecorder created on every database access

**What:** `_load_pipeline_structure` (line 164) and `_load_node_state` (line 271) each create a new `LandscapeRecorder(db)` instance. The recorder itself is lightweight (it initializes repository objects from the db), but it creates new `DatabaseOps` and multiple `Repository` objects each time.

**Why it matters:** This is wasteful but not critical for a TUI that makes infrequent queries. However, if the tree selection becomes rapid (keyboard repeat on arrow keys), the repeated instantiation adds unnecessary GC pressure. A single recorder stored on the screen would be cleaner.

### [293-303] _load_node_state returns None on database error, losing error context

**What:** When a recoverable database error occurs during `_load_node_state`, the method logs the error but returns `None`. The caller (`on_tree_select`, line 251) passes `None` to `self._detail_panel.update_state(None)`, which renders "No node selected." The user sees the same message whether the node doesn't exist or the database is unreachable.

**Why it matters:** The user cannot distinguish between "this node has no state data" and "the database query failed." Unlike `_load_pipeline_structure` which transitions to `LoadingFailedState` with an error message, node state loading silently degrades. The user might think the node genuinely has no data when in reality the database is down.

**Evidence:**
```python
except _RECOVERABLE_DB_ERRORS as e:
    logger.warning(
        "Database error loading node state",
        ...
    )
    return None  # Same return as "node not found"
```

### [172-183] Source info construction handles empty source_nodes but produces misleading data

**What:** When `source_nodes` is empty (no source node registered for the run), the code falls through to `{"name": "unknown", "node_id": None}`. This happens silently for non-existent `run_id` values, as confirmed by the test `test_loaded_state_with_empty_data_on_nonexistent_run`.

**Why it matters:** A non-existent `run_id` produces a valid `LoadedState` with `source.name == "unknown"` rather than signaling to the user that the run does not exist. The screen enters `LoadedState` and renders a tree with `Run: <non-existent-id>` and `Source: unknown`. A user investigating a specific run might not realize they have a typo in the run ID. The distinction between "run exists but has no source node" and "run does not exist" is lost.

## Observations

### [39-86] Discriminated union state model is well-designed

**What:** The `ScreenStateType` enum, frozen dataclasses for each state, and the `ScreenState` union type provide a clean state machine. Each state carries exactly the data it needs. `LoadingFailedState` preserves `db` and `run_id` for retry, `LoadedState` carries the full data payload. The `frozen=True` constraint prevents accidental mutation.

### [305-311] get_detail_panel_state accesses private _state attribute

**What:** The method `get_detail_panel_state` returns `self._detail_panel._state`, reaching through the public API boundary to access the panel's private state. While this is within the same module boundary (screen owns the panel), it creates a coupling to the panel's internal representation.

### [348-401] State transition methods have correct guard conditions

**What:** `load()` requires `UninitializedState`, `retry()` requires `LoadingFailedState`, `clear()` accepts any state. These are all correctly guarded with `isinstance` checks and raise `InvalidStateTransitionError` with informative messages. The transitions are well-tested per the test file.

### [238-253] on_tree_select has no validation of node_id format

**What:** The `node_id` parameter is accepted as a plain string with no validation. While this is a read-only display operation (the node_id is used as a database query parameter via SQLAlchemy's parameterized queries, so SQL injection is not a risk), there is no check that `node_id` is non-empty or well-formed.

### [25] _RECOVERABLE_DB_ERRORS is a module-level tuple

**What:** Good practice -- centralizing the exception types that are considered recoverable ensures consistency between `_load_pipeline_structure` and `_load_node_state`. The docstring correctly notes that other exceptions indicate bugs in our code and should crash.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Include GATE, AGGREGATION, and COALESCE node types in the lineage display (map them into the transforms list or add separate categories). (2) Consider distinguishing "node not found" from "database error" in `_load_node_state` return values. (3) Consider detecting and reporting non-existent run IDs rather than silently entering LoadedState with placeholder data.
**Confidence:** HIGH -- the state machine is well-tested, the code is readable, and the issues are clearly identifiable from the NodeType enum and the filter logic.
