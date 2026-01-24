# Fix Schema Validation Architecture Properly

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move schema validation to plugin construction time, eliminating the need for DAG layer to access SchemaConfig.

**Architecture:** Two-phase validation model:
1. **Self-validation** (plugin __init__): Plugin validates its own schema is well-formed
2. **Compatibility validation** (ExecutionGraph construction): System validates plugin connections

DAG validation only checks structural issues (cycles, missing nodes). This eliminates information loss, parallel detection mechanisms, and NodeInfo bloat.

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
PHASE 1: Plugin Construction (Self-Validation)
Plugin.__init__(config)
  ↓ Extract SchemaConfig
  ↓ Create Pydantic schema
  ↓ VALIDATE: Schema is well-formed
  ↓ Raise ValueError if malformed
  ↓
PHASE 2: Graph Construction (Compatibility Validation)
ExecutionGraph.from_plugin_instances(plugins)
  ↓ Wire plugins together (source → transforms → sinks)
  ↓ VALIDATE: Each edge has compatible schemas
  ↓   - Producer has all fields required by consumer
  ↓   - Dynamic schemas compatible with anything
  ↓   - Gates pass-through correctly
  ↓   - Coalesce branches have compatible schemas
  ↓ Raise ValueError if incompatible
  ↓
PHASE 3: Structural Validation (No Schema Knowledge)
DAG.validate()
  ↓ Check cycles (NetworkX)
  ↓ Check reachability
  ↓ NO schema validation (already done in Phase 2)
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
        """Validate output schema is well-formed (self-validation).

        Called during plugin construction to verify schema definition is valid.
        This is PHASE 1 validation - checking the schema itself, not compatibility
        with other plugins.

        Returns:
            List of validation errors (empty if valid)

        Raises:
            ValueError: If schema configuration is invalid

        Note:
            This is SELF-validation only. Plugin checks its own schema is valid.
            COMPATIBILITY validation (does plugin A's output match plugin B's input?)
            happens in PHASE 2 during ExecutionGraph.from_plugin_instances().

        Example:
            - Valid: Schema has no syntax errors, types are well-formed
            - Invalid: Schema has malformed field specs, unknown types
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

## Task 2.5: Add Edge Compatibility Validation to ExecutionGraph

**Goal:** ExecutionGraph validates schema compatibility when wiring plugins together.

**Files:**
- Modify: `src/elspeth/core/dag.py` (add _validate_edge_compatibility method)
- Create: `tests/core/test_edge_validation.py` (new test file)

**Step 1: Write failing test for edge compatibility validation**

Create `tests/core/test_edge_validation.py`:

```python
"""Test edge compatibility validation during graph construction."""

import pytest
from elspeth.contracts import PluginSchema
from elspeth.core.dag import ExecutionGraph


class ProducerSchema(PluginSchema):
    """Producer output schema."""
    id: int
    name: str


class ConsumerSchema(PluginSchema):
    """Consumer input schema."""
    id: int
    name: str
    email: str  # Required field NOT in producer!


def test_edge_validation_detects_missing_fields() -> None:
    """Edges should fail if producer missing required fields."""
    graph = ExecutionGraph()

    # Add source with ProducerSchema
    graph.add_node("source", node_type="source", plugin_name="csv", output_schema=ProducerSchema)

    # Add sink requiring ConsumerSchema (has 'email' field)
    graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=ConsumerSchema)

    # Try to wire them together - should fail
    with pytest.raises(ValueError, match="missing required fields.*email"):
        graph.add_edge("source", "sink", label="continue")
        # Edge validation happens during add_edge()


def test_edge_validation_allows_dynamic_schemas() -> None:
    """Dynamic schemas should be compatible with anything."""
    from elspeth.contracts.schema import create_dynamic_schema

    graph = ExecutionGraph()

    dynamic_schema = create_dynamic_schema("DynamicSchema")

    # Dynamic producer → strict consumer: OK
    graph.add_node("source", node_type="source", plugin_name="csv", output_schema=dynamic_schema)
    graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=ConsumerSchema)
    graph.add_edge("source", "sink", label="continue")  # Should succeed

    # Strict producer → dynamic consumer: OK
    graph2 = ExecutionGraph()
    graph2.add_node("source", node_type="source", plugin_name="csv", output_schema=ProducerSchema)
    graph2.add_node("sink", node_type="sink", plugin_name="csv", input_schema=dynamic_schema)
    graph2.add_edge("source", "sink", label="continue")  # Should succeed


def test_gate_passthrough_validation() -> None:
    """Gates must preserve schema (input == output)."""
    graph = ExecutionGraph()

    # Source produces ProducerSchema
    graph.add_node("source", node_type="source", plugin_name="csv", output_schema=ProducerSchema)

    # Gate claims to pass through but has DIFFERENT output schema
    graph.add_node("gate", node_type="gate", plugin_name="threshold",
                   input_schema=ProducerSchema, output_schema=ConsumerSchema)

    # Should fail - gates must have input == output
    with pytest.raises(ValueError, match="Gate.*must preserve schema"):
        graph.add_edge("source", "gate", label="continue")


def test_coalesce_branch_compatibility() -> None:
    """Coalesce must receive compatible schemas from all branches."""
    graph = ExecutionGraph()

    # Source forks to two paths
    graph.add_node("source", node_type="source", plugin_name="csv", output_schema=ProducerSchema)

    # Path 1: Transform to Schema A
    class SchemaA(PluginSchema):
        value: int

    graph.add_node("transform1", node_type="transform", plugin_name="field_mapper",
                   input_schema=ProducerSchema, output_schema=SchemaA)

    # Path 2: Transform to Schema B (INCOMPATIBLE!)
    class SchemaB(PluginSchema):
        different: str

    graph.add_node("transform2", node_type="transform", plugin_name="field_mapper",
                   input_schema=ProducerSchema, output_schema=SchemaB)

    # Coalesce node
    graph.add_node("coalesce", node_type="coalesce", plugin_name="merge",
                   input_schema=SchemaA)  # Expects SchemaA from both branches

    # Wire up
    graph.add_edge("source", "transform1", label="fork_path_1")
    graph.add_edge("source", "transform2", label="fork_path_2")
    graph.add_edge("transform1", "coalesce", label="continue")  # OK

    # This should fail - transform2 outputs SchemaB, coalesce expects SchemaA
    with pytest.raises(ValueError, match="Coalesce.*incompatible schemas"):
        graph.add_edge("transform2", "coalesce", label="continue")
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_edge_validation.py -xvs
```

Expected: FAIL (edge validation not implemented yet)

**Step 3: Add _validate_edge_compatibility method to ExecutionGraph**

In `src/elspeth/core/dag.py`, add method:

```python
def _validate_edge_compatibility(
    self,
    from_node_id: str,
    to_node_id: str
) -> None:
    """Validate schema compatibility between two connected nodes.

    Args:
        from_node_id: Source node ID
        to_node_id: Destination node ID

    Raises:
        ValueError: If schemas are incompatible

    Validation rules:
    1. Producer output must have all fields required by consumer input
    2. Dynamic schemas are compatible with anything
    3. Gates must preserve schema (input == output)
    4. Coalesce nodes must receive compatible schemas from all inputs
    """
    from_info = self.get_node_info(from_node_id)
    to_info = self.get_node_info(to_node_id)

    producer_schema = from_info.output_schema
    consumer_schema = to_info.input_schema

    # Rule 1: Dynamic schemas bypass validation
    if producer_schema is None or consumer_schema is None:
        return  # Dynamic schema - compatible with anything

    # Rule 2: Gates must preserve schema
    if to_info.node_type == "gate":
        if to_info.input_schema is not to_info.output_schema:
            raise ValueError(
                f"Gate '{to_node_id}' must preserve schema "
                f"(input == output), but input is {to_info.input_schema.__name__} "
                f"and output is {to_info.output_schema.__name__}"
            )

    # Rule 3: Check field compatibility
    missing_fields = self._get_missing_required_fields(
        producer_schema, consumer_schema
    )
    if missing_fields:
        raise ValueError(
            f"Edge from '{from_node_id}' to '{to_node_id}' invalid: "
            f"producer schema '{producer_schema.__name__}' missing required fields "
            f"for consumer schema '{consumer_schema.__name__}': {missing_fields}"
        )

    # Rule 4: Coalesce compatibility checked when second+ edge added
    if to_info.node_type == "coalesce":
        # Check if this is second+ incoming edge
        existing_edges = list(self._graph.in_edges(to_node_id, data=True))
        if len(existing_edges) > 0:
            # Get schema from first incoming edge
            first_edge_source = existing_edges[0][0]
            first_producer = self.get_node_info(first_edge_source)
            first_schema = first_producer.output_schema

            # New edge must have same schema
            if producer_schema is not first_schema:
                raise ValueError(
                    f"Coalesce '{to_node_id}' receives incompatible schemas: "
                    f"first input has {first_schema.__name__ if first_schema else 'dynamic'}, "
                    f"'{from_node_id}' has {producer_schema.__name__ if producer_schema else 'dynamic'}"
                )


def _get_missing_required_fields(
    self,
    producer_schema: type[PluginSchema] | None,
    consumer_schema: type[PluginSchema] | None,
) -> list[str]:
    """Get required fields that producer doesn't provide.

    Args:
        producer_schema: Schema of data producer
        consumer_schema: Schema of data consumer

    Returns:
        List of field names missing from producer
    """
    if producer_schema is None or consumer_schema is None:
        return []  # Dynamic schema

    producer_fields = set(producer_schema.model_fields.keys())
    consumer_required = {
        name for name, field in consumer_schema.model_fields.items()
        if field.is_required()
    }

    return sorted(consumer_required - producer_fields)
```

**Step 4: Update add_edge() to call validation**

In `src/elspeth/core/dag.py`, update `add_edge()` method:

```python
def add_edge(self, from_node_id: str, to_node_id: str, label: str) -> None:
    """Add edge between nodes with schema compatibility validation.

    Args:
        from_node_id: Source node ID
        to_node_id: Destination node ID
        label: Edge label (e.g., "continue", "route_to_sink")

    Raises:
        ValueError: If schemas are incompatible
    """
    # Validate schema compatibility BEFORE adding edge
    self._validate_edge_compatibility(from_node_id, to_node_id)

    # Add edge to graph
    self._graph.add_edge(from_node_id, to_node_id, label=label)
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/core/test_edge_validation.py -xvs
```

Expected: PASS

**Step 6: Commit**

```bash
git add src/elspeth/core/dag.py tests/core/test_edge_validation.py
git commit -m "feat: add edge compatibility validation to ExecutionGraph

- Validate schema compatibility during add_edge()
- Phase 2 validation: plugins connected with compatible schemas
- Checks missing fields, dynamic schemas, gate pass-through, coalesce
- Ref: Fix schema validation architecture properly"
```

---

## Task 3: Add Self-Validation to Plugin Base Classes

**Goal:** Plugin base classes validate their own schemas are well-formed (self-validation, not compatibility).

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

    def _validate_self_consistency(self) -> None:
        """Validate plugin's own schemas are self-consistent (PHASE 1).

        Called by subclass __init__ after setting schemas. This is SELF-validation
        only - checking that the plugin's own configuration makes sense.

        Raises:
            ValueError: If schemas are internally inconsistent

        Note:
            This is NOT about compatibility with OTHER plugins. That happens in
            PHASE 2 during ExecutionGraph.from_plugin_instances().

            Examples of self-consistency checks:
            - PassThrough: input_schema must equal output_schema
            - FieldMapper: output fields must be subset of input fields (if mode=strict)
            - Gate: input_schema must equal output_schema (pass-through)

            This is a no-op for transforms with no self-consistency constraints.
            Subclasses override for custom validation logic.
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

    # NEW: Validate self-consistency (PHASE 1)
    self._validate_self_consistency()
```

**Step 5: Run test**

```bash
pytest tests/plugins/transforms/test_passthrough.py::test_passthrough_validates_schema_compatibility -xvs
```

Expected: PASS

**Step 6: Commit**

```bash
git add src/elspeth/plugins/base.py src/elspeth/plugins/transforms/passthrough.py tests/plugins/transforms/test_passthrough.py
git commit -m "feat: add self-validation to transform construction

- BaseTransform._validate_self_consistency() method
- PHASE 1: Plugin validates its own schema is well-formed
- PassThrough ensures input_schema == output_schema
- Does NOT validate compatibility with other plugins (that's PHASE 2)
- Ref: Fix schema validation architecture properly"
```

---

## Task 3.5: Add Enforcement Mechanism for Validation

**Goal:** Ensure plugins CANNOT skip validation (compile-time enforcement).

**Files:**
- Modify: `src/elspeth/plugins/base.py` (add validation enforcement)
- Create: `tests/contracts/test_validation_enforcement.py` (enforcement tests)

**Step 1: Write test for enforcement**

Create `tests/contracts/test_validation_enforcement.py`:

```python
"""Test that plugins cannot skip validation."""

import pytest
from elspeth.plugins.base import BaseTransform
from elspeth.contracts import PluginSchema


class TestSchema(PluginSchema):
    """Test schema."""
    value: int


def test_transform_must_call_validation() -> None:
    """Transforms that forget to call _validate_self_consistency should fail."""

    class BadTransform(BaseTransform):
        """Transform that forgets to call validation."""

        def __init__(self, config: dict) -> None:
            super().__init__(config)
            self.input_schema = TestSchema
            self.output_schema = TestSchema
            # BUG: Forgot to call self._validate_self_consistency()

        def process(self, row, ctx):
            return row

    # This should raise an error at construction time
    with pytest.raises(RuntimeError, match="must call.*_validate_self_consistency"):
        BadTransform({})


def test_transform_with_validation_succeeds() -> None:
    """Transforms that call validation should succeed."""

    class GoodTransform(BaseTransform):
        """Transform that correctly calls validation."""

        def __init__(self, config: dict) -> None:
            super().__init__(config)
            self.input_schema = TestSchema
            self.output_schema = TestSchema
            self._validate_self_consistency()  # Correct!

        def process(self, row, ctx):
            return row

    # Should succeed
    transform = GoodTransform({})
    assert transform.input_schema is TestSchema
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/contracts/test_validation_enforcement.py::test_transform_must_call_validation -xvs
```

Expected: FAIL (enforcement not implemented yet)

**Step 3: Add enforcement via __init_subclass__**

In `src/elspeth/plugins/base.py`, add enforcement to `BaseTransform`:

```python
class BaseTransform(ABC):
    """Base class for transform plugins."""

    _validation_called: bool = False

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize transform.

        Args:
            config: Plugin configuration

        Raises:
            ValueError: If schema configuration is invalid or incompatible
            RuntimeError: If subclass forgets to call _validate_self_consistency()
        """
        self._config = config
        self._validation_called = False

        # Subclass must set input_schema and output_schema
        # Validation happens in subclass __init__ after schemas are set

    def _validate_self_consistency(self) -> None:
        """Validate plugin's own schemas are self-consistent (PHASE 1).

        Called by subclass __init__ after setting schemas. This is SELF-validation
        only - checking that the plugin's own configuration makes sense.

        Raises:
            ValueError: If schemas are internally inconsistent

        Note:
            This is NOT about compatibility with OTHER plugins. That happens in
            PHASE 2 during ExecutionGraph.from_plugin_instances().

            Examples of self-consistency checks:
            - PassThrough: input_schema must equal output_schema
            - FieldMapper: output fields must be subset of input fields (if mode=strict)
            - Gate: input_schema must equal output_schema (pass-through)

            This is a no-op for transforms with no self-consistency constraints.
            Subclasses override for custom validation logic.
        """
        # Mark that validation was called
        self._validation_called = True

        # Default: No validation (subclasses override if needed)
        pass

    def __post_init__(self) -> None:
        """Verify validation was called.

        This runs AFTER subclass __init__ completes.

        Raises:
            RuntimeError: If subclass forgot to call _validate_self_consistency()
        """
        if not self._validation_called:
            raise RuntimeError(
                f"{self.__class__.__name__} must call self._validate_self_consistency() "
                f"in __init__ after setting input_schema and output_schema"
            )
```

**Step 4: Hook __post_init__ via __init_subclass__**

Add to `BaseTransform`:

```python
def __init_subclass__(cls, **kwargs):
    """Hook to wrap __init__ with validation check."""
    super().__init_subclass__(**kwargs)

    original_init = cls.__init__

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # After __init__ completes, verify validation was called
        if not self._validation_called:
            raise RuntimeError(
                f"{self.__class__.__name__} must call self._validate_self_consistency() "
                f"in __init__ after setting input_schema and output_schema"
            )

    cls.__init__ = wrapped_init
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/contracts/test_validation_enforcement.py -xvs
```

Expected: PASS

**Step 6: Run all transform tests to ensure no breakage**

```bash
pytest tests/plugins/transforms/ -v
```

Expected: PASS (all transforms already call validation after Task 3)

**Step 7: Commit**

```bash
git add src/elspeth/plugins/base.py tests/contracts/test_validation_enforcement.py
git commit -m "feat: enforce validation calls via __init_subclass__

- BaseTransform automatically checks validation was called
- Raises RuntimeError if plugin forgets _validate_self_consistency()
- Compile-time enforcement (fails during construction, not runtime)
- Cannot skip validation accidentally
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

**Phase 1 Validation (Self-Validation):**
- [ ] Plugin protocols define self-validation methods
- [ ] Transforms validate self-consistency during construction
- [ ] Enforcement mechanism ensures validation cannot be skipped
- [ ] Validation enforcement tests pass

**Phase 2 Validation (Compatibility):**
- [ ] ExecutionGraph validates edge compatibility during add_edge()
- [ ] Missing field detection works
- [ ] Dynamic schema compatibility works
- [ ] Gate pass-through validation works
- [ ] Coalesce branch compatibility validation works
- [ ] Edge validation tests pass

**Phase 3 Validation (Structure Only):**
- [ ] DAG validation only checks structure (cycles, connectivity)
- [ ] Schema validation methods deleted from DAG layer (~200 LOC)

**Test Updates:**
- [ ] All tests updated for two-phase validation model
- [ ] Integration tests expect ValueError during plugin wiring (not DAG.validate)
- [ ] no_bug_hiding.yaml allowlist entries removed

**Quality Gates:**
- [ ] Full test suite passes (3,279+)
- [ ] mypy clean
- [ ] ruff clean
- [ ] Bug tickets marked resolved

**Success Metrics:**

| Metric | Before (Phase 3) | After (Root Fix) |
|--------|------------------|------------------|
| Detection mechanisms | 2 (SchemaConfig + introspection) | 0 (no detection, validation at construction) |
| Validation phases | 1 (DAG validates everything) | 2 (self + compatibility) |
| Validation locations | 2 (plugin + DAG) | 2 (plugin self-check + graph edge-check) |
| Pydantic coupling | HIGH (introspection) | NONE (no introspection) |
| NodeInfo fields | 6 | 6 (no change) |
| Architecture quality | 2/5 | **5/5** |
| Information loss | YES (SchemaConfig discarded) | NO (stays with plugin) |
| Technical debt | Created (introspection) | **ELIMINATED** |
| Validation enforcement | NO (plugins can skip) | YES (__init_subclass__ hook) |
| Gate validation | Missing | Explicit (input == output check) |
| Coalesce validation | Missing | Explicit (branch compatibility check) |

---

## Two-Phase Validation: The Key Insight

The critical architectural insight is distinguishing between two fundamentally different kinds of validation:

### Phase 1: Self-Validation (Plugin Construction)

**What it validates:** Is the plugin's own schema well-formed and internally consistent?

**When it happens:** During `Plugin.__init__(config)`

**Who knows enough to validate:** The plugin itself (has access to its own config)

**Examples:**
- Source: Output schema has valid field definitions
- Transform: If pass-through, input_schema == output_schema
- Sink: Input schema has valid field definitions

**Failure mode:** ValueError raised during plugin construction

**Key property:** Plugin can validate itself WITHOUT knowledge of other plugins

### Phase 2: Compatibility Validation (Graph Construction)

**What it validates:** Are two plugins compatible when wired together?

**When it happens:** During `ExecutionGraph.add_edge(from_node, to_node)`

**Who knows enough to validate:** The graph construction code (has access to both plugins)

**Examples:**
- Does source output schema have all fields required by transform input?
- Is dynamic schema → strict schema compatible?
- Does gate preserve schema (input == output)?
- Do all coalesce branches produce compatible schemas?

**Failure mode:** ValueError raised during edge creation

**Key property:** Requires knowledge of BOTH plugins being connected

### Why This Distinction Matters

**The Architecture Critic's key observation:**
> "A plugin cannot validate its compatibility with other plugins during its own
> __init__() because the other plugins don't exist yet."

This is why propagating SchemaConfig to NodeInfo (Option A) was the wrong fix:
- It tried to move DAG validation logic from DAG.validate() to DAG construction
- But it kept ALL validation at the DAG layer
- This missed the opportunity to move SELF-validation to plugins

**The root cause fix:**
- Phase 1 validation moves to plugins (they validate themselves)
- Phase 2 validation stays at graph construction (cross-plugin checks)
- DAG.validate() only checks structure (no schema knowledge needed)

**Result:** Each layer validates what it has knowledge to validate

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
