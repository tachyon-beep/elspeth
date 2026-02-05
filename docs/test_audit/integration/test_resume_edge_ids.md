# Test Audit: tests/integration/test_resume_edge_ids.py

**Auditor:** Claude
**Date:** 2026-02-05
**Batch:** 105-106

## Overview

This file contains integration tests for Bug #3 (Resume Uses Synthetic Edge IDs). Tests verify that resume uses real edge IDs from the database instead of generating synthetic IDs, preventing FK violations when gates record routing events.

**Lines:** 294
**Test Class:** `TestResumeEdgeIDs`
**Test Count:** 2

---

## Summary

| Category | Issues Found |
|----------|--------------|
| Defects | 0 |
| Test Path Integrity Violations | 1 (MAJOR) |
| Overmocking | 0 |
| Missing Coverage | 1 |
| Tests That Do Nothing | 0 |
| Structural Issues | 1 |
| Inefficiency | 1 |

---

## Issues

### 1. [MAJOR] Test Path Integrity Violation - Manual Graph Construction

**Location:** `gate_graph` fixture (lines 80-94)

**Problem:** The test manually constructs an `ExecutionGraph` using `graph.add_node()` and `graph.add_edge()` instead of using the production path `ExecutionGraph.from_plugin_instances()`.

```python
@pytest.fixture
def gate_graph(self) -> ExecutionGraph:
    """Create a graph with a gate routing to multiple sinks."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
    graph.add_node("gate", node_type=NodeType.GATE, plugin_name="simple_gate", config=schema_config)
    # ... manual construction continues
```

**Why It Matters:** Per CLAUDE.md "Test Path Integrity" section: "Tests must use production code paths like `ExecutionGraph.from_plugin_instances()`". Manual graph construction can mask bugs in the production construction path (see BUG-LINEAGE-01 discussion in CLAUDE.md).

**Recommendation:** Refactor to use `ExecutionGraph.from_plugin_instances()` with real plugin instances. The `SimpleGate` class defined in the file can be used as part of a proper plugin instantiation flow.

---

### 2. [MINOR] Raw SQL for Node Registration

**Location:** `_register_nodes_raw` method (lines 96-151)

**Problem:** Nodes are registered using raw SQL instead of going through `LandscapeRecorder.register_node()`. While this may be intentional to avoid full pipeline setup, it creates a divergent code path from production.

```python
def _register_nodes_raw(self, db: LandscapeDB, run_id: str) -> None:
    """Register nodes using raw SQL to avoid full pipeline setup."""
    # ... raw SQL inserts
```

**Impact:** If `LandscapeRecorder.register_node()` has bugs or different behavior than raw SQL, this test won't catch them.

**Recommendation:** Either use `LandscapeRecorder.register_node()` for consistency, or document why raw SQL is necessary for this specific test scenario.

---

### 3. [MINOR] Missing Coverage - Routing Event Recording

**Location:** `test_resume_with_gate_no_fk_violation` (lines 218-294)

**Problem:** The test claims to verify "No FK violations when recording routing events" (comment on line 231), but never actually records any routing events. It only verifies that edge IDs can be loaded from the database.

```python
# 7. Verify all edge IDs are real (not synthetic)
for (_from_node, _label), edge_id in loaded_edge_map.items():
    assert not edge_id.startswith("resume_edge_")
    # Verify this edge_id actually exists in database
    with db.engine.connect() as conn:
        edge_exists = conn.execute(select(edges_table).where(edges_table.c.edge_id == edge_id)).fetchone()
    assert edge_exists is not None, f"Edge ID {edge_id} not found in database"

# SUCCESS: If we got here without FK violations, the fix works!
```

**Impact:** The test doesn't actually trigger the FK violation scenario it claims to protect against.

**Recommendation:** Add a step that actually records routing events using the loaded edge IDs and verifies no FK violations occur.

---

### 4. [MINOR] Inefficiency - Repeated Database Connections

**Location:** `test_resume_with_gate_no_fk_violation` (lines 284-290)

**Problem:** Inside a loop, a new database connection is opened for each edge verification:

```python
for (_from_node, _label), edge_id in loaded_edge_map.items():
    assert not edge_id.startswith("resume_edge_")
    # Verify this edge_id actually exists in database
    with db.engine.connect() as conn:  # New connection per iteration
        edge_exists = conn.execute(select(edges_table).where(edges_table.c.edge_id == edge_id)).fetchone()
```

**Recommendation:** Refactor to verify all edges in a single query or use a single connection for the loop.

---

## Passing Criteria

- Test class has proper `Test` prefix (discovered by pytest)
- Tests verify real business logic (edge ID persistence)
- Fixtures are appropriately scoped
- No overmocking - tests interact with real database

---

## Verdict

**NEEDS REVISION** - The major test path integrity violation should be addressed. Manual graph construction masks potential bugs in the production `from_plugin_instances()` path.
