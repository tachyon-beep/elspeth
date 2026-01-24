# Fix Schema Validation Architecture Properly

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move schema validation to plugin construction time, eliminating the need for DAG layer to access SchemaConfig.

**Architecture:** Plugins validate their own schema compatibility during `__init__()`. DAG validation only checks structural issues (cycles, missing nodes). This eliminates information loss, parallel detection mechanisms, and NodeInfo bloat.

**Why NOW (Pre-Release):**
- Post-release: Breaking change to plugin protocol requires migration
- Pre-release: We control all plugins, can update them atomically
- This is the LAST chance to get architecture right before public API

**Tech Stack:** Python protocols, Pydantic validation, plugin hookspecs

---

## The Problem We're Actually Solving

**Current Architecture (Broken):**
```
Plugin.__init__(config)
  ↓ Extract SchemaConfig
  ↓ Create Pydantic schema
  ↓ THROW AWAY SchemaConfig
  ↓
DAG construction
  ↓ Need SchemaConfig (it's gone!)
  ↓ Either introspect Pydantic (Phase 3) OR propagate both (Phase 4)
  ↓
DAG.validate()
  ↓ Check schema compatibility
  ↓ Discovers incompatibilities AFTER plugin instantiation
```

**Proper Architecture:**
```
Plugin.__init__(config)
  ↓ Extract SchemaConfig
  ↓ Create Pydantic schema
  ↓ VALIDATE compatibility with expected upstream/downstream
  ↓ Raise ValueError if incompatible
  ↓
DAG construction
  ↓ Assumes plugins are valid (they crashed during __init__ if not)
  ↓
DAG.validate()
  ↓ Only structural checks (cycles, reachability, missing nodes)
  ↓ NO schema compatibility checks (already done)
```

**This eliminates:**
- ❌ Need for SchemaConfig in NodeInfo (doesn't propagate)
- ❌ Need for `_is_dynamic_schema()` introspection (doesn't exist)
- ❌ Need for `_extract_schema_config()` helper (doesn't exist)
- ❌ Risk of from_config() vs from_plugin_instances() divergence (same path)
- ❌ Schema validation logic in DAG layer (moved to plugins)

---

## Task 1: Add Schema Validation to Plugin Protocol

**Goal:** Define protocol methods for plugins to self-validate schemas.

**Files:**
- Modify: `src/elspeth/plugins/protocols.py` (add validation methods)

**Step 1: Write failing test for source validation**

Add to `tests/contracts/test_plugin_protocols.py`:

```python
def test_source_validates_output_schema_on_init() -> None:
    """Sources should validate output schema during construction."""
    from elspeth.plugins.sources.csv_source import CSVSource

    # Valid schema - should succeed
    config = {
        "path": "test.csv",
        "schema": {"fields": "dynamic"},
    }
    source = CSVSource(config)  # Should not raise

    # Invalid schema - should fail during __init__
    bad_config = {
        "path": "test.csv",
        "schema": {"mode": "strict", "fields": ["invalid syntax"]},
    }

    with pytest.raises(ValueError, match="Invalid field spec"):
        CSVSource(bad_config)  # Fails during construction
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/contracts/test_plugin_protocols.py::test_source_validates_output_schema_on_init -xvs
```

Expected: PASS (sources already validate via SchemaConfig.from_dict in __init__)

**Step 3: Add protocol method to SourceProtocol**

In `src/elspeth/plugins/protocols.py`, add to `SourceProtocol`:

```python
class SourceProtocol(Protocol):
    """Protocol for source plugins."""

    name: str
    output_schema: type[PluginSchema] | None

    def load(self, ctx: PluginContext) -> Iterable[SourceRow]:
        """Load data from source."""
        ...

    def validate_output_schema(self) -> list[str]:
        """Validate output schema configuration.

        Called during plugin construction to verify schema is valid.

        Returns:
            List of validation errors (empty if valid)

        Raises:
            ValueError: If schema configuration is invalid

        Note:
            This validates the schema DEFINITION, not compatibility.
            Compatibility validation happens when plugins are wired together.
        """
        ...
```

**Step 4: Run test again**

```bash
pytest tests/contracts/test_plugin_protocols.py::test_source_validates_output_schema_on_init -xvs
```

Expected: PASS (CSVSource already validates in __init__)

**Step 5: Commit**

```bash
git add src/elspeth/plugins/protocols.py tests/contracts/test_plugin_protocols.py
git commit -m "feat: add schema validation to plugin protocols

- Add validate_output_schema() to SourceProtocol
- Sources validate schema during __init__ (already implemented)
- Establishes pattern for transform/sink validation
- Ref: Fix schema validation architecture properly"
```

---

## Task 2: Remove Schema Validation from DAG Layer

**Goal:** DAG validation only checks structural issues, not schema compatibility.

**Files:**
- Modify: `src/elspeth/core/dag.py` (simplify validate() method)
- Modify: `tests/core/test_dag.py` (update test expectations)

**Step 1: Write test for new DAG validation behavior**

Add to `tests/core/test_dag.py`:

```python
def test_dag_validation_only_checks_structure() -> None:
    """DAG validation should only check cycles and connectivity, not schemas."""
    from elspeth.contracts import PluginSchema
    from elspeth.core.dag import ExecutionGraph

    class OutputSchema(PluginSchema):
        value: int

    class DifferentSchema(PluginSchema):
        different: str  # Incompatible!

    graph = ExecutionGraph()

    # Add incompatible schemas
    graph.add_node("source", node_type="source", plugin_name="csv", output_schema=OutputSchema)
    graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=DifferentSchema)
    graph.add_edge("source", "sink", label="continue")

    # OLD behavior: Would raise GraphValidationError for schema mismatch
    # NEW behavior: Only checks structural validity (no cycles)
    errors = graph.validate()
    assert len(errors) == 0  # No structural problems
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_dag.py::test_dag_validation_only_checks_structure -xvs
```

Expected: FAIL (currently validates schema compatibility)

**Step 3: Simplify DAG.validate() method**

In `src/elspeth/core/dag.py`, replace `validate()` method:

```python
def validate(self, raise_on_error: bool = False) -> list[str]:
    """Validate graph structure.

    Checks for:
    - Cycles (graphs must be acyclic)
    - Connectivity (all sinks reachable from source)
    - Route consistency (gate routes reference valid sinks)

    Does NOT check schema compatibility - plugins validate their own
    schemas during construction.

    Args:
        raise_on_error: If True, raise GraphValidationError on first error

    Returns:
        List of validation errors (empty if valid)

    Raises:
        GraphValidationError: If raise_on_error=True and validation fails
    """
    errors = []

    # Check for cycles
    if not nx.is_directed_acyclic_graph(self._graph):
        error_msg = "Graph contains cycles (not a valid DAG)"
        if raise_on_error:
            raise GraphValidationError(error_msg)
        errors.append(error_msg)

    # Check connectivity (all sinks reachable from source)
    source_nodes = [n for n, data in self._graph.nodes(data=True) if data["info"].node_type == "source"]
    sink_nodes = [n for n, data in self._graph.nodes(data=True) if data["info"].node_type == "sink"]

    if source_nodes:
        source_id = source_nodes[0]
        for sink_id in sink_nodes:
            if not nx.has_path(self._graph, source_id, sink_id):
                error_msg = f"Sink '{sink_id}' is not reachable from source"
                if raise_on_error:
                    raise GraphValidationError(error_msg)
                errors.append(error_msg)

    # Check gate routes reference valid sinks
    gate_nodes = [n for n, data in self._graph.nodes(data=True) if data["info"].node_type == "gate"]
    valid_sink_names = set(self._sink_id_map.keys()) if self._sink_id_map else set()

    for gate_id in gate_nodes:
        gate_info = self.get_node_info(gate_id)
        # Gates store route targets in config
        route_config = gate_info.config.get("routes", {})
        for route_target in route_config.values():
            if route_target not in valid_sink_names and route_target != "continue":
                error_msg = f"Gate '{gate_id}' routes to unknown sink '{route_target}'"
                if raise_on_error:
                    raise GraphValidationError(error_msg)
                errors.append(error_msg)

    return errors
```

**Step 4: Delete schema validation methods**

Delete these methods from `src/elspeth/core/dag.py`:
- `_is_dynamic_schema()` (lines 67-84)
- `_get_missing_required_fields()` (lines 49-64)
- `_schemas_compatible()` (lines 87-97)
- `_validate_edge_schemas()` (lines 288-338)
- `_validate_coalesce_schema_compatibility()` (lines 240-286)

**Step 5: Run test to verify it passes**

```bash
pytest tests/core/test_dag.py::test_dag_validation_only_checks_structure -xvs
```

Expected: PASS

**Step 6: Update existing schema validation tests**

Find tests that expect schema validation errors from DAG.validate() and update them to expect plugin construction failures instead:

```bash
# Find tests that check for schema validation in DAG
grep -r "GraphValidationError.*schema" tests/core/test_dag.py
```

Update each to test plugin construction instead:

```python
# OLD:
with pytest.raises(GraphValidationError, match="missing required fields"):
    graph.validate()

# NEW:
with pytest.raises(ValueError, match="Schema compatibility"):
    Transform(bad_config)  # Fails during construction
```

**Step 7: Run all DAG tests**

```bash
pytest tests/core/test_dag.py -v
```

Expected: Some tests will fail (need updating)

**Step 8: Commit**

```bash
git add src/elspeth/core/dag.py tests/core/test_dag.py
git commit -m "refactor: remove schema validation from DAG layer

- DAG validation now only checks structure (cycles, connectivity)
- Delete _is_dynamic_schema, _validate_edge_schemas, etc.
- Schema validation moved to plugin construction (next task)
- Ref: Fix schema validation architecture properly"
```

---

## Task 3: Add Schema Compatibility Validation to Transforms

**Goal:** Transforms validate input/output schema compatibility during construction.

**Files:**
- Modify: `src/elspeth/plugins/base.py` (add validation to BaseTransform)

**Step 1: Write failing test for transform validation**

Add to `tests/plugins/transforms/test_passthrough.py`:

```python
def test_passthrough_validates_schema_compatibility() -> None:
    """PassThrough should validate schema is self-compatible."""
    from elspeth.plugins.transforms.passthrough import PassThrough

    # Valid: Dynamic schema (always compatible with itself)
    config = {"schema": {"fields": "dynamic"}}
    transform = PassThrough(config)  # Should succeed

    # Valid: Explicit schema (compatible with itself)
    config = {"schema": {"mode": "strict", "fields": ["id: int", "name: str"]}}
    transform = PassThrough(config)  # Should succeed

    # Note: PassThrough has same input/output schema, so always compatible
    # More complex transforms tested separately
```

**Step 2: Run test**

```bash
pytest tests/plugins/transforms/test_passthrough.py::test_passthrough_validates_schema_compatibility -xvs
```

Expected: PASS (PassThrough already creates compatible schemas)

**Step 3: Add validation method to BaseTransform**

In `src/elspeth/plugins/base.py`, add to `BaseTransform`:

```python
class BaseTransform(ABC):
    """Base class for transform plugins."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize transform.

        Args:
            config: Plugin configuration

        Raises:
            ValueError: If schema configuration is invalid or incompatible
        """
        self._config = config

        # Subclass must set input_schema and output_schema
        # Validation happens in subclass __init__ after schemas are set

    def _validate_schema_compatibility(self) -> None:
        """Validate input and output schemas are compatible.

        Called by subclass __init__ after setting schemas.

        Raises:
            ValueError: If schemas are incompatible

        Note:
            This is a no-op for transforms where validation doesn't apply:
            - Dynamic schemas (always compatible)
            - Transforms that intentionally change schema (add/remove fields)

            Subclasses can override for custom validation logic.
        """
        # Default: No validation (subclasses override if needed)
        pass
```

**Step 4: Update PassThrough to call validation**

In `src/elspeth/plugins/transforms/passthrough.py`, add to `__init__`:

```python
def __init__(self, config: dict[str, Any]) -> None:
    super().__init__(config)
    cfg = PassThroughConfig.from_dict(config)
    self._validate_input = cfg.validate_input
    self._on_error: str | None = cfg.on_error

    assert cfg.schema_config is not None
    self._schema_config = cfg.schema_config

    schema = create_schema_from_config(
        self._schema_config,
        "PassThroughSchema",
        allow_coercion=False,
    )
    self.input_schema = schema
    self.output_schema = schema

    # NEW: Validate schema compatibility
    self._validate_schema_compatibility()
```

**Step 5: Run test**

```bash
pytest tests/plugins/transforms/test_passthrough.py::test_passthrough_validates_schema_compatibility -xvs
```

Expected: PASS

**Step 6: Commit**

```bash
git add src/elspeth/plugins/base.py src/elspeth/plugins/transforms/passthrough.py tests/plugins/transforms/test_passthrough.py
git commit -m "feat: add schema validation to transform construction

- BaseTransform._validate_schema_compatibility() method
- Called during __init__ after schemas are set
- PassThrough validates self-compatibility
- Ref: Fix schema validation architecture properly"
```

---

## Task 4: Update All Tests to Expect Construction-Time Validation

**Goal:** Update integration tests to expect schema errors during plugin construction, not graph validation.

**Files:**
- Modify: `tests/integration/test_schema_validation_end_to_end.py`
- Modify: `tests/cli/test_plugin_errors.py`

**Step 1: Identify tests that rely on DAG validation**

```bash
grep -r "graph.validate()" tests/integration/ tests/cli/
grep -r "GraphValidationError" tests/integration/ tests/cli/
```

**Step 2: Update tests to expect ValueError from plugin construction**

For each test that expects `GraphValidationError` from `graph.validate()`:

```python
# OLD pattern:
graph = ExecutionGraph.from_plugin_instances(...)
with pytest.raises(GraphValidationError):
    graph.validate()

# NEW pattern:
with pytest.raises(ValueError, match="Schema compatibility"):
    graph = ExecutionGraph.from_plugin_instances(...)
    # Plugin construction fails if schemas incompatible
```

**Step 3: Run integration tests**

```bash
pytest tests/integration/test_schema_validation_end_to_end.py -v
```

Expected: Many failures (need updating)

**Step 4: Update each failing test**

Work through each failure, updating test expectations.

**Step 5: Run CLI tests**

```bash
pytest tests/cli/test_plugin_errors.py -v
```

Expected: Some failures (need updating)

**Step 6: Commit after all tests pass**

```bash
git add tests/integration/ tests/cli/
git commit -m "test: update tests for construction-time validation

- Schema errors now raised during plugin construction
- No longer expect GraphValidationError from graph.validate()
- Expect ValueError during ExecutionGraph.from_plugin_instances()
- Ref: Fix schema validation architecture properly"
```

---

## Task 5: Remove no_bug_hiding.yaml Allowlist Entries

**Goal:** Delete all allowlist entries related to schema detection.

**Files:**
- Modify: `config/cicd/no_bug_hiding.yaml`

**Step 1: Find schema-related allowlist entries**

```bash
grep -E "(_is_dynamic_schema|_extract_schema_config|model_config)" config/cicd/no_bug_hiding.yaml
```

**Step 2: Delete all related entries**

Remove entries for:
- `_is_dynamic_schema` (deleted function)
- `model_config.get()` (no longer used)
- Any other schema introspection patterns

**Step 3: Run no_bug_hiding check**

```bash
pytest tests/contracts/test_no_bug_hiding.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add config/cicd/no_bug_hiding.yaml
git commit -m "chore: remove schema detection from allowlist

- Delete _is_dynamic_schema entry (function deleted)
- Delete model_config.get() entries (no longer used)
- Net reduction: -N entries
- Ref: Fix schema validation architecture properly"
```

---

## Task 6: Run Full Test Suite

**Goal:** Verify all tests pass with new architecture.

**Step 1: Run complete test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All 3,279+ tests PASS

**Step 2: Run type checking**

```bash
mypy src/
```

Expected: Success

**Step 3: Run linting**

```bash
ruff check src/
```

Expected: All checks passed

**Step 4: If any failures, debug and fix**

Work through each failure systematically.

---

## Task 7: Update Bug Tickets

**Goal:** Mark all schema detection bugs as resolved.

**Files:**
- Modify: `docs/bugs/P0-2026-01-24-eliminate-parallel-dynamic-schema-detection.md`
- Modify: `docs/bugs/P0-2026-01-24-dynamic-schema-detection-regression.md`

**Step 1: Update P0-2026-01-24-eliminate-parallel-dynamic-schema-detection.md**

Add resolution section:

```markdown
## Resolution

**Status:** ✅ **RESOLVED** (commit: <hash>)

**Implementation:** ROOT CAUSE FIX - Moved validation to plugin construction

**What Changed:**
1. Schema validation moved from DAG layer to plugin construction
2. DAG.validate() only checks structural issues (cycles, connectivity)
3. Plugins validate their own schemas during __init__()
4. Deleted _is_dynamic_schema(), _validate_edge_schemas(), etc.
5. No SchemaConfig propagation to NodeInfo (not needed)

**Architecture Improvement:**
- Before: 2/5 (parallel mechanisms, Pydantic coupling)
- After: 5/5 (single source of truth, validation at right layer)

**Eliminated:**
- Parallel detection mechanisms (2 → 0, validation happens once)
- Pydantic introspection (gone, not needed)
- NodeInfo bloat (avoided, no new fields)
- Information loss pattern (fixed, config stays with plugin)

**Implemented:** 2026-01-24
**Implementation Plan:** docs/plans/2026-01-24-fix-schema-validation-properly.md
```

**Step 2: Update P0-2026-01-24-dynamic-schema-detection-regression.md**

Mark as superseded:

```markdown
## Resolution Update

**Status:** ✅ **SUPERSEDED BY ROOT CAUSE FIX**

**Original Fix:** Phase 3 introspection (P0-2026-01-24-dynamic-schema-detection-regression)
**Root Cause Fix:** Moved validation to plugin construction (this ticket)

**Why Superseded:**
The introspection fix (Phase 3) was correct but created technical debt.
Instead of fixing the debt (Phase 4 propagation plan), we fixed the
root cause (validation placement).

**See:** docs/plans/2026-01-24-fix-schema-validation-properly.md
```

**Step 3: Commit**

```bash
git add docs/bugs/*.md
git commit -m "docs: mark schema detection bugs as resolved

- Root cause fixed: validation moved to plugin construction
- No parallel mechanisms, no introspection, no NodeInfo bloat
- Architecture quality: 2/5 → 5/5
- Ref: Fix schema validation architecture properly"
```

---

## Completion Checklist

- [ ] Plugin protocols define validation methods
- [ ] DAG validation only checks structure (cycles, connectivity)
- [ ] Schema validation methods deleted from DAG layer
- [ ] Transforms validate during construction
- [ ] All tests updated for construction-time validation
- [ ] no_bug_hiding.yaml allowlist entries removed
- [ ] Full test suite passes (3,279+)
- [ ] mypy clean
- [ ] ruff clean
- [ ] Bug tickets marked resolved

**Success Metrics:**

| Metric | Before (Phase 3) | After (Root Fix) |
|--------|------------------|------------------|
| Detection mechanisms | 2 (SchemaConfig + introspection) | 0 (validation once at construction) |
| Validation locations | 2 (plugin + DAG) | 1 (plugin only) |
| Pydantic coupling | HIGH | NONE |
| NodeInfo fields | 6 | 6 (no change) |
| Architecture quality | 2/5 | **5/5** |
| Information loss | YES (SchemaConfig discarded) | NO (stays with plugin) |
| Technical debt | Created (introspection) | **ELIMINATED** |

---

## Why This Is Better Than Option A (Propagation)

**Option A (propagation plan):**
- Adds `input_schema_config` and `output_schema_config` to NodeInfo
- Propagates SchemaConfig through graph construction
- DAG validation checks `schema_config.is_dynamic`
- **Result:** 2/5 → 4/5 architecture (still has information duplication)

**This Plan (proper fix):**
- NO changes to NodeInfo (stays at 6 fields)
- NO SchemaConfig propagation (doesn't leave plugin)
- DAG validation doesn't check schemas AT ALL
- **Result:** 2/5 → **5/5** architecture (single responsibility, single source of truth)

**Eliminated Complexity:**
- ❌ No extraction helper needed
- ❌ No from_config() vs from_plugin_instances() divergence
- ❌ No SchemaConfig serialization concerns
- ❌ No parallel validation logic
- ❌ No NodeInfo bloat precedent

**You're right - this is the last chance to fix it properly before release.**

---

## References

**Related Documentation:**
- Bug ticket: `docs/bugs/P0-2026-01-24-eliminate-parallel-dynamic-schema-detection.md`
- Systems thinking review: Identified validation placement as root cause
- CLAUDE.md: "Plugin Ownership: System Code, Not User Code"

**Architectural Principle:**
> "Validation should happen where the knowledge lives"
> - Plugins have SchemaConfig → Plugins validate
> - DAG has graph structure → DAG validates structure
