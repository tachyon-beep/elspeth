# Composer Schema Contract Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the composer reject pipelines with unsatisfied schema contracts at composition time, and expose per-edge contract data in the preview response.

**Architecture:** Add a new validation pass (pass 9) to `CompositionState.validate()` that walks the connection-field chain, parses schema config via `SchemaConfig.from_dict()` (deferred import from `contracts.schema`), and compares producer guaranteed fields against consumer required fields (from both `required_input_fields` and `schema.required_fields`) for nodes and sinks. Extend `ValidationSummary` with `EdgeContract` tuples. Patch the pipeline-composer skill with contract-aware completion criteria.

**Tech Stack:** Python dataclasses (frozen), `SchemaConfig` from `elspeth.contracts.schema`, pytest

**Spec:** `docs/superpowers/specs/2026-04-14-composer-schema-contract-validation-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/elspeth/web/composer/state.py` | Modify | Add `EdgeContract` dataclass, extend `ValidationSummary`, add `_check_schema_contracts()` helper with text-source heuristic, call it from `validate()` |
| `src/elspeth/web/composer/tools.py` | Modify | Serialize `edge_contracts` in `_execute_preview_pipeline()` |
| `src/elspeth/plugins/sources/text_source.py` | Modify | Auto-declare `guaranteed_fields` for deterministic output + enforcement comment |
| `src/elspeth/web/composer/skills/pipeline_composer.md` | Modify | Add completion criteria item 4, text source safety rule, fix flow example |
| `tests/unit/web/composer/test_state.py` | Modify | Add `TestSchemaContractValidation` class with test cases |
| `tests/unit/web/composer/test_schema_contract_enforcement.py` | Create | Heuristic enforcement test (test case 20) |
| `tests/integration/web/test_composer_runtime_agreement.py` | Create | Composer/runtime agreement test (test case 19) |

---

### Task 1: Add `EdgeContract` Dataclass and Extend `ValidationSummary`

**Files:**
- Modify: `src/elspeth/web/composer/state.py:198-229`
- Test: `tests/unit/web/composer/test_state.py`

- [ ] **Step 1: Write the failing test for EdgeContract**

Add to `tests/unit/web/composer/test_state.py`, after the existing `TestValidationSummary` class:

```python
class TestEdgeContract:
    def test_frozen(self) -> None:
        from elspeth.web.composer.state import EdgeContract

        ec = EdgeContract(
            from_id="source",
            to_id="add_world",
            producer_guarantees=("text",),
            consumer_requires=("text",),
            missing_fields=(),
            satisfied=True,
        )
        with pytest.raises(AttributeError):
            ec.satisfied = False  # type: ignore[misc]

    def test_to_dict_uses_from_key(self) -> None:
        """EdgeContract.to_dict() serializes from_id as 'from' (JSON key)."""
        from elspeth.web.composer.state import EdgeContract

        ec = EdgeContract(
            from_id="source",
            to_id="add_world",
            producer_guarantees=("text",),
            consumer_requires=("text",),
            missing_fields=(),
            satisfied=True,
        )
        d = ec.to_dict()
        assert d["from"] == "source"
        assert d["to"] == "add_world"
        assert d["producer_guarantees"] == ["text"]
        assert d["consumer_requires"] == ["text"]
        assert d["missing_fields"] == []
        assert d["satisfied"] is True

    def test_to_dict_empty_fields(self) -> None:
        from elspeth.web.composer.state import EdgeContract

        ec = EdgeContract(
            from_id="source",
            to_id="sink",
            producer_guarantees=(),
            consumer_requires=(),
            missing_fields=(),
            satisfied=True,
        )
        d = ec.to_dict()
        assert d["producer_guarantees"] == []
        assert d["consumer_requires"] == []
        assert d["missing_fields"] == []


class TestValidationSummaryEdgeContracts:
    def test_default_empty(self) -> None:
        vs = ValidationSummary(is_valid=True, errors=())
        assert vs.edge_contracts == ()

    def test_with_edge_contracts(self) -> None:
        from elspeth.web.composer.state import EdgeContract

        ec = EdgeContract(
            from_id="source",
            to_id="t1",
            producer_guarantees=("text",),
            consumer_requires=("text",),
            missing_fields=(),
            satisfied=True,
        )
        vs = ValidationSummary(is_valid=True, errors=(), edge_contracts=(ec,))
        assert len(vs.edge_contracts) == 1
        assert vs.edge_contracts[0].satisfied is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestEdgeContract -v`
Expected: FAIL with `ImportError: cannot import name 'EdgeContract'`

- [ ] **Step 3: Implement EdgeContract and extend ValidationSummary**

In `src/elspeth/web/composer/state.py`, after `ValidationEntry` (around line 215), add:

```python
@dataclass(frozen=True, slots=True)
class EdgeContract:
    """Schema contract check result for a single producer->consumer edge.

    All fields are scalars or tuples of strings. frozen=True is sufficient.
    """

    from_id: str
    to_id: str
    producer_guarantees: tuple[str, ...]
    consumer_requires: tuple[str, ...]
    missing_fields: tuple[str, ...]
    satisfied: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON responses.

        Uses 'from'/'to' as JSON keys (not from_id/to_id) for readability.
        """
        return {
            "from": self.from_id,
            "to": self.to_id,
            "producer_guarantees": list(self.producer_guarantees),
            "consumer_requires": list(self.consumer_requires),
            "missing_fields": list(self.missing_fields),
            "satisfied": self.satisfied,
        }
```

Then modify `ValidationSummary` to add the new field:

```python
@dataclass(frozen=True, slots=True)
class ValidationSummary:
    """Stage 1 validation result.

    errors block execution. warnings are advisory but actionable.
    suggestions are optional improvements. edge_contracts shows per-edge
    schema contract check results. All are tuples for structured attribution.
    """

    is_valid: bool
    errors: tuple[ValidationEntry, ...]
    warnings: tuple[ValidationEntry, ...] = ()
    suggestions: tuple[ValidationEntry, ...] = ()
    edge_contracts: tuple[EdgeContract, ...] = ()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestEdgeContract tests/unit/web/composer/test_state.py::TestValidationSummaryEdgeContracts -v`
Expected: PASS

- [ ] **Step 5: Run full existing test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py -v`
Expected: All existing tests PASS (EdgeContract default=() is backward-compatible)

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/web/composer/state.py tests/unit/web/composer/test_state.py
git commit -m "feat(composer): add EdgeContract dataclass and extend ValidationSummary"
```

---

### Task 2: Implement Schema Contract Validation Pass

**Files:**
- Modify: `src/elspeth/web/composer/state.py:460-775`
- Test: `tests/unit/web/composer/test_state.py`

This is the core implementation. We write tests first for the positive and negative cases, then implement `_check_schema_contracts()`.

- [ ] **Step 1: Write failing tests — positive cases (1-5)**

Add to `tests/unit/web/composer/test_state.py`, a new class after `TestStage1Validation`:

```python
class TestSchemaContractValidation:
    """Tests for schema contract validation (pass 9) in CompositionState.validate()."""

    def _empty_state(self) -> CompositionState:
        return CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=1,
        )

    def _make_source(
        self,
        on_success: str = "t1",
        plugin: str = "csv",
        options: dict[str, Any] | None = None,
    ) -> SourceSpec:
        return SourceSpec(
            plugin=plugin,
            on_success=on_success,
            options=options or {},
            on_validation_failure="quarantine",
        )

    def _make_transform(
        self,
        id: str,
        input: str,
        on_success: str,
        plugin: str = "value_transform",
        options: dict[str, Any] | None = None,
    ) -> NodeSpec:
        return NodeSpec(
            id=id,
            node_type="transform",
            plugin=plugin,
            input=input,
            on_success=on_success,
            on_error=None,
            options=options or {},
            condition=None,
            routes=None,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )

    def _make_gate(
        self,
        id: str,
        input: str,
        routes: dict[str, str],
        condition: str = "row['x'] > 0",
    ) -> NodeSpec:
        return NodeSpec(
            id=id,
            node_type="gate",
            plugin=None,
            input=input,
            on_success=None,
            on_error=None,
            options={},
            condition=condition,
            routes=routes,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )

    def _make_output(self, name: str = "main") -> OutputSpec:
        return OutputSpec(name=name, plugin="csv", options={"path": f"outputs/{name}.csv"}, on_write_failure="discard")

    def _make_edge(
        self,
        id: str,
        from_node: str,
        to_node: str,
        edge_type: EdgeType = "on_success",
    ) -> EdgeSpec:
        return EdgeSpec(id=id, from_node=from_node, to_node=to_node, edge_type=edge_type, label=None)

    # --- Positive cases ---

    def test_fixed_schema_satisfies_requirement(self) -> None:
        """Test 1: Source with fixed schema guaranteeing 'text' satisfies consumer."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors
        assert not any("contract" in e.message.lower() for e in result.errors)

    def test_text_heuristic_infers_guarantee(self) -> None:
        """Test 2: Text source with column + observed schema — heuristic infers guarantee.

        The composer infers {column} as a guaranteed field for text sources
        with observed schema and no explicit guaranteed_fields. This mirrors
        what TextSource does at runtime (auto-declares guaranteed_fields in
        __init__), so both the composer and the runtime agree.
        """
        state = self._empty_state()
        state = state.with_source(self._make_source(
            plugin="text",
            options={"column": "text", "schema": {"mode": "observed"}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors

    def test_text_heuristic_respects_explicit_guaranteed_fields(self) -> None:
        """Test 3: Text source with explicit guaranteed_fields — heuristic defers."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            plugin="text",
            options={
                "column": "text",
                "schema": {"mode": "observed", "guaranteed_fields": ["text"]},
            },
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors

    def test_no_required_input_fields_skips_check(self) -> None:
        """Test 4: Consumer with no required_input_fields — no error."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "observed"}},
        ))
        state = state.with_node(self._make_transform("t1", "t1", "main"))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors

    def test_empty_required_input_fields_skips_check(self) -> None:
        """Test 5: Consumer with required_input_fields: [] — no error."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "observed"}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": []},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors
```

- [ ] **Step 2: Run positive tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation -v -k "not negative and not topology and not malformed and not partial and not optional and not no_schema"`
Expected: PASS (these positive tests will pass because validate() currently doesn't emit contract errors — the tests check for absence of errors, which is the current behavior. We need to also add the negative tests to confirm the implementation works.)

Actually, tests 1-5 will pass on current code because the current `validate()` never emits contract errors. The negative tests (step 3) are what will fail and drive the implementation.

- [ ] **Step 3: Write failing tests — negative cases (6-10)**

Append to `TestSchemaContractValidation`:

```python
    # --- Negative cases ---

    def test_observed_schema_no_guarantees_fails(self) -> None:
        """Test 6: Observed schema with no guarantees, consumer requires 'text'."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "observed"}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("schema contract violation" in e.message.lower() for e in result.errors)
        assert any("text" in e.message for e in result.errors)

    def test_partial_match_fails(self) -> None:
        """Test 7: Producer guarantees ['text'], consumer requires ['text', 'score']."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text", "score"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("score" in e.message for e in result.errors)

    def test_optional_field_not_guaranteed(self) -> None:
        """Test 8: Optional field (text: str?) is NOT guaranteed."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str?"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("text" in e.message for e in result.errors)

    def test_no_schema_config_fails(self) -> None:
        """Test 9: Source with no schema config at all — no guarantees."""
        state = self._empty_state()
        state = state.with_source(self._make_source(options={}))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("schema contract violation" in e.message.lower() for e in result.errors)

    def test_malformed_schema_emits_error(self) -> None:
        """Test 10: Malformed schema dict — error emitted, is_valid false."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "invalid_mode"}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("schema" in e.message.lower() for e in result.errors)
```

- [ ] **Step 4: Run negative tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_observed_schema_no_guarantees_fails tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_partial_match_fails tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_no_schema_config_fails -v`
Expected: FAIL (current validate() doesn't check contracts)

- [ ] **Step 5: Implement `_check_schema_contracts()` helper**

In `src/elspeth/web/composer/state.py`, add a new function after `_validate_gate_expression()` (around line 254):

```python
def _check_schema_contracts(
    source: SourceSpec | None,
    nodes: tuple[NodeSpec, ...],
    outputs: tuple[OutputSpec, ...],
) -> tuple[list[ValidationEntry], list[ValidationEntry], list[EdgeContract]]:
    """Check schema contracts along the connection-field chain.

    Walks the producer→consumer chain and verifies that every consumer's
    required fields (from required_input_fields OR schema.required_fields)
    are guaranteed by its upstream producer's schema. Checks both node
    consumers and sink consumers — mirroring the runtime's
    validate_edge_compatibility() + _validate_sink_required_fields().

    Coalesce nodes are detected and skipped — their guarantees are computed
    at runtime from branch policies and merge strategies, which the composer
    cannot replicate. A warning is emitted for skipped edges.

    Uses a deferred import to keep state.py's module-level imports minimal
    (only contracts.freeze). The import is L3→L0, which is layer-legal.

    Returns (errors, warnings, edge_contracts) — errors are blocking,
    warnings are advisory, edge_contracts are informational.
    """
    from elspeth.contracts.schema import SchemaConfig

    errors: list[ValidationEntry] = []
    contract_warnings: list[ValidationEntry] = []
    edge_contracts: list[EdgeContract] = []
    _err = ValidationEntry

    if source is None:
        return errors, contract_warnings, edge_contracts

    # Track producers whose schema failed to parse — suppress downstream
    # contract violations for these (avoid double-errors: parse error + missing fields)
    parse_failed_producers: set[str] = set()

    # Guard: "source" is a reserved sentinel ID used in the producer map
    # and walk-back termination. A node with id="source" would cause
    # incorrect walk-back termination.
    for node in nodes:
        if node.id == "source":
            errors.append(_err(
                f"node:{node.id}",
                "Node ID 'source' is reserved for the pipeline source and cannot be used as a node ID.",
                "high",
            ))
            return errors, contract_warnings, edge_contracts

    # --- Build producer map: connection_point → (id, plugin_name, options) ---
    # The source produces data at source.on_success
    # Each node produces data at node.on_success (and routes for gates)
    producer_map: dict[str, tuple[str, str | None, Mapping[str, Any]]] = {}

    # Source produces at its on_success connection point
    producer_map[source.on_success] = ("source", source.plugin, source.options)

    # Each node produces at its on_success and/or routes
    def _register_producer(connection_point: str, producer_id: str, plugin: str | None, options: Mapping[str, Any]) -> None:
        """Register a producer for a connection point, detecting collisions."""
        if connection_point in producer_map:
            existing_id = producer_map[connection_point][0]
            if existing_id != producer_id:
                errors.append(_err(
                    f"connection:{connection_point}",
                    (
                        f"Connection point '{connection_point}' has multiple producers: "
                        f"'{existing_id}' and '{producer_id}'. Each connection point "
                        f"must have exactly one producer."
                    ),
                    "high",
                ))
                return  # Keep the first producer — don't overwrite
        producer_map[connection_point] = (producer_id, plugin, options)

    for node in nodes:
        if node.on_success is not None:
            _register_producer(node.on_success, node.id, node.plugin, node.options)
        # Gate routes: each route target gets the same producer info
        # Gates are schema-preserving — they don't add or remove fields
        if node.routes is not None:
            for route_target in node.routes.values():
                # For gates, the guaranteed fields come from whatever feeds the gate,
                # not from the gate itself (gates have no schema).
                # We use the gate's own entry — _get_guaranteed_fields handles this
                # by returning empty for nodes with no schema, but we need the
                # gate's *upstream* guarantees. For now, register the gate as producer.
                _register_producer(route_target, node.id, node.plugin, node.options)

    # CLOSED LIST — do not add entries without design review.
    # Only sources with fully deterministic output qualify (output shape
    # entirely determined by config, not by input data).
    # See: docs/superpowers/specs/2026-04-14-composer-schema-contract-validation-design.md
    # (Shifting the Burden archetype — each addition looks locally reasonable,
    # but collectively rebuilds the runtime validator badly.)
    _TEXT_HEURISTIC_PLUGINS: frozenset[str] = frozenset({"text"})

    def _get_guaranteed_fields(
        entity_id: str,
        plugin_name: str | None,
        options: Mapping[str, Any],
    ) -> frozenset[str]:
        """Extract guaranteed fields from a producer's schema config.

        Uses SchemaConfig.get_effective_guaranteed_fields() as the primary source
        of truth — the same method the runtime uses (graph.py:get_guaranteed_fields).

        For plugins in _TEXT_HEURISTIC_PLUGINS, applies a secondary inference:
        if the plugin has a deterministic output column and the schema doesn't
        already declare guaranteed_fields, infers {column} as guaranteed. This
        mirrors what TextSource does at runtime (Task 6b auto-declares
        guaranteed_fields in its schema config at init time), so the composer
        and runtime agree on the guarantee.
        """
        schema_raw = options.get("schema")

        if schema_raw is not None:
            try:
                schema_config = SchemaConfig.from_dict(schema_raw)
            except ValueError as exc:
                # Malformed schema — emit error. Schema config is Tier 2 data.
                errors.append(_err(
                    f"{'source' if entity_id == 'source' else f'node:{entity_id}'}",
                    f"Invalid schema config: {exc}",
                    "high",
                ))
                parse_failed_producers.add(entity_id)
                return frozenset()

            guaranteed = schema_config.get_effective_guaranteed_fields()
            has_explicit_guarantees = schema_config.declares_guaranteed_fields
        else:
            guaranteed = frozenset()
            has_explicit_guarantees = False

        # Text source heuristic — see _TEXT_HEURISTIC_PLUGINS constant above.
        # Single application point after schema resolution.
        # This mirrors what TextSource.__init__ does at runtime (Task 6b):
        # when column is set and schema is observed with no explicit
        # guaranteed_fields, the plugin auto-declares {column} as guaranteed.
        if (
            plugin_name in _TEXT_HEURISTIC_PLUGINS
            and not has_explicit_guarantees
        ):
            column = options.get("column")
            if isinstance(column, str) and column:
                guaranteed = guaranteed | frozenset({column})

        return guaranteed

    def _get_required_fields(consumer_id: str, options: Mapping[str, Any]) -> frozenset[str]:
        """Extract required fields from a consumer's options.

        Mirrors the runtime's get_required_fields() (graph.py:1795) priority:
        1. Explicit required_input_fields from plugin config
        2. Explicit required_fields in schema config

        Does NOT include implicit requirements from typed schemas — those
        are handled by runtime type validation (Phase 2 in validate_edge_compatibility).
        """
        # Priority 1: required_input_fields (explicit plugin-level declaration)
        required = options.get("required_input_fields")
        if required is not None and required:
            # Guard against bare string — frozenset("text") would produce {"t","e","x"}
            if isinstance(required, str):
                errors.append(_err(
                    f"node:{consumer_id}",
                    f"required_input_fields must be a list, got bare string: {required!r}",
                    "high",
                ))
                return frozenset()
            return frozenset(required)

        # Priority 2: schema.required_fields (schema-level contract declaration)
        schema_raw = options.get("schema")
        if schema_raw is not None:
            try:
                schema_config = SchemaConfig.from_dict(schema_raw)
            except ValueError:
                # Parse error already caught by _get_guaranteed_fields for producers.
                # For consumers, we just skip — the error is in the consumer's schema,
                # not in the contract check itself.
                return frozenset()
            if schema_config.required_fields is not None:
                return frozenset(schema_config.required_fields)

        return frozenset()

    # --- Walk consumer nodes and check contracts ---
    for node in nodes:
        consumer_required = _get_required_fields(node.id, node.options)
        node_input = node.input

        # Find the producer for this node's input connection point
        producer_info = producer_map.get(node_input)
        if producer_info is None:
            # No producer found — topology error already caught by pass 8
            continue

        producer_id, producer_plugin, producer_options = producer_info

        # For gates (schema-preserving), walk up to find the real producer.
        # Gate nodes have no schema of their own — they pass through their
        # upstream producer's guarantees. Walk back through the chain.
        #
        # Precondition: pass 8 (connection completeness) already validated that
        # every node.input is reachable. If producer_map.get(input) returns None
        # here, it means pass 8 flagged it — not a silent failure.
        #
        # Scope: this walk-back handles route gates only. Fork gates (fork_to)
        # create parallel DAG branches with coalesce merge. Coalesce nodes
        # are detected after the walk-back and skipped with a warning —
        # their guarantees are computed at runtime from branch policies.
        actual_id, actual_plugin, actual_options = producer_id, producer_plugin, producer_options
        # visited guards against cycles that pass 8 may not have caught —
        # pass 8 checks reachability (every node.input has a producer), not
        # acyclicity. A self-referencing gate or a gate cycle would loop
        # forever without this set.
        visited: set[str] = set()
        while actual_id != "source" and actual_id not in visited:
            visited.add(actual_id)
            # Find the node with this id
            upstream_node = next((n for n in nodes if n.id == actual_id), None)
            if upstream_node is None:
                break
            # If this node is a gate (schema-preserving), look further upstream
            if upstream_node.node_type != "gate":
                break
            # Find what feeds this gate
            gate_producer = producer_map.get(upstream_node.input)
            if gate_producer is None:
                break
            actual_id, actual_plugin, actual_options = gate_producer

        # Coalesce nodes compute their guarantees at runtime from branch
        # policies and merge strategies (builder.py:938). The composer can't
        # replicate this — it would need to instantiate plugins and walk
        # branch schemas, which breaks the pure-function design. Rather than
        # checking against wrong guarantees (the coalesce's own schema config,
        # which doesn't reflect the computed merge), skip the contract check
        # and emit a warning so the user knows this edge isn't verified.
        if actual_id != "source":
            actual_node = next((n for n in nodes if n.id == actual_id), None)
            if actual_node is not None and actual_node.node_type == "coalesce":
                contract_warnings.append(_err(
                    f"edge:{actual_id}->{node.id}",
                    (
                        f"Schema contract check skipped: producer '{actual_id}' is a coalesce node.\n"
                        f"  Coalesce guarantees are computed at runtime from branch policies and\n"
                        f"  merge strategies — the composer cannot verify this statically.\n"
                        f"  The runtime validator will check this edge."
                    ),
                    "medium",
                ))
                continue

        producer_guaranteed = _get_guaranteed_fields(actual_id, actual_plugin, actual_options)

        # Skip edge contract entirely if the producer had a parse error —
        # the parse error is already reported, and emitting an EdgeContract
        # with satisfied=False and empty producer_guarantees would confuse
        # users (they'd see a contract failure that can't be fixed by
        # adjusting field declarations — the real fix is the schema syntax).
        if actual_id in parse_failed_producers:
            continue

        # Build EdgeContract — use actual_id (the real producer after gate walk-back),
        # not producer_id (which may be a gate that has no schema of its own)
        missing = consumer_required - producer_guaranteed
        satisfied = not missing
        edge_contracts.append(EdgeContract(
            from_id=actual_id,
            to_id=node.id,
            producer_guarantees=tuple(sorted(producer_guaranteed)),
            consumer_requires=tuple(sorted(consumer_required)),
            missing_fields=tuple(sorted(missing)),
            satisfied=satisfied,
        ))

        # Check for violations
        if missing:
            # Use actual_id/actual_plugin (the real producer after gate walk-back),
            # not producer_id (which may be a schema-preserving gate)
            producer_label = actual_plugin or actual_id
            consumer_label = node.plugin or node.id
            errors.append(_err(
                f"edge:{actual_id}->{node.id}",
                (
                    f"Schema contract violation: '{actual_id}' -> '{node.id}'.\n"
                    f"  Consumer ({consumer_label}) requires fields: {sorted(consumer_required)}\n"
                    f"  Producer ({producer_label}) guarantees: "
                    f"{sorted(producer_guaranteed) if producer_guaranteed else '(none - observed schema)'}\n"
                    f"  Missing fields: {sorted(missing)}\n"
                    f"  Fix: Add missing fields to the source schema (use mode 'fixed' or 'flexible'),\n"
                    f"  set explicit guaranteed_fields, or remove from required_input_fields if optional."
                ),
                "high",
            ))

    # --- Walk sink outputs and check their contracts ---
    # Mirrors runtime's _validate_sink_required_fields() (graph.py:1674).
    # Sinks can declare required fields via schema.required_fields.
    for output in outputs:
        sink_required = _get_required_fields(f"output:{output.name}", output.options)
        if not sink_required:
            continue

        # Find the producer for this output's connection point (output.name)
        producer_info = producer_map.get(output.name)
        if producer_info is None:
            # No producer found — topology error already caught by earlier passes
            continue

        producer_id, producer_plugin, producer_options = producer_info

        # Gate walk-back for sinks (same logic as node consumers)
        actual_id, actual_plugin, actual_options = producer_id, producer_plugin, producer_options
        visited_sink: set[str] = set()
        while actual_id != "source" and actual_id not in visited_sink:
            visited_sink.add(actual_id)
            upstream_node = next((n for n in nodes if n.id == actual_id), None)
            if upstream_node is None:
                break
            if upstream_node.node_type != "gate":
                break
            gate_producer = producer_map.get(upstream_node.input)
            if gate_producer is None:
                break
            actual_id, actual_plugin, actual_options = gate_producer

        # Coalesce skip for sinks (same logic as node consumers above)
        if actual_id != "source":
            actual_node = next((n for n in nodes if n.id == actual_id), None)
            if actual_node is not None and actual_node.node_type == "coalesce":
                contract_warnings.append(_err(
                    f"edge:{actual_id}->output:{output.name}",
                    (
                        f"Schema contract check skipped: producer '{actual_id}' is a coalesce node.\n"
                        f"  Coalesce guarantees are computed at runtime from branch policies and\n"
                        f"  merge strategies — the composer cannot verify this statically.\n"
                        f"  The runtime validator will check this edge."
                    ),
                    "medium",
                ))
                continue

        producer_guaranteed = _get_guaranteed_fields(actual_id, actual_plugin, actual_options)

        if actual_id in parse_failed_producers:
            continue

        missing = sink_required - producer_guaranteed
        satisfied = not missing
        edge_contracts.append(EdgeContract(
            from_id=actual_id,
            to_id=f"output:{output.name}",
            producer_guarantees=tuple(sorted(producer_guaranteed)),
            consumer_requires=tuple(sorted(sink_required)),
            missing_fields=tuple(sorted(missing)),
            satisfied=satisfied,
        ))

        if missing:
            producer_label = actual_plugin or actual_id
            errors.append(_err(
                f"edge:{actual_id}->output:{output.name}",
                (
                    f"Schema contract violation: '{actual_id}' -> sink '{output.name}'.\n"
                    f"  Sink ({output.plugin}) requires fields: {sorted(sink_required)}\n"
                    f"  Producer ({producer_label}) guarantees: "
                    f"{sorted(producer_guaranteed) if producer_guaranteed else '(none - observed schema)'}\n"
                    f"  Missing fields: {sorted(missing)}\n"
                    f"  Fix: Add missing fields to the upstream schema (use mode 'fixed' or 'flexible'),\n"
                    f"  set explicit guaranteed_fields, or remove from sink's required_fields if optional."
                ),
                "high",
            ))

    return errors, contract_warnings, edge_contracts
```

- [ ] **Step 6: Call `_check_schema_contracts()` from `validate()`**

In `CompositionState.validate()`, before the `return ValidationSummary(...)` at the end (around line 770), add the contract check:

```python
        # 9. Schema contract validation
        contract_errors, contract_warnings, edge_contracts = _check_schema_contracts(self.source, self.nodes, self.outputs)
        errors.extend(contract_errors)
        warnings.extend(contract_warnings)

        return ValidationSummary(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            suggestions=tuple(suggestions),
            edge_contracts=tuple(edge_contracts),
        )
```

Remove the old `return ValidationSummary(...)` that was there before.

- [ ] **Step 7: Run negative tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation -v`
Expected: All 10 tests PASS

- [ ] **Step 8: Run full test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py -v`
Expected: All tests PASS. The `test_validate_clean_pipeline_no_warnings` test should still pass because it has no `required_input_fields` on any node, so the contract check is skipped.

- [ ] **Step 9: Commit**

```bash
git add src/elspeth/web/composer/state.py tests/unit/web/composer/test_state.py
git commit -m "feat(composer): add schema contract validation pass (pass 9)"
```

---

### Task 3: Add Topology Test Cases (11-14)

**Files:**
- Test: `tests/unit/web/composer/test_state.py`

- [ ] **Step 1: Write topology tests**

Append to `TestSchemaContractValidation`:

```python
    # --- Topology cases ---

    def test_gate_inherits_source_guarantees(self) -> None:
        """Test 11: Gate route targets inherit source's guaranteed fields."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="gate_in",
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_gate(
            "g1", "gate_in", {"high": "main", "low": "errors"},
        ))
        # Add a transform after the gate on the "high" route
        state = state.with_node(self._make_transform(
            "t1", "main", "out",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output("out"))
        state = state.with_output(self._make_output("errors"))
        state = state.with_edge(self._make_edge("e1", "source", "g1"))
        state = state.with_edge(self._make_edge("e2", "g1", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors

    def test_route_gate_two_routes_inherit_guarantees(self) -> None:
        """Test 12: Route gate with two routes — both paths inherit source guarantees.

        Note: This tests route gates (node.routes), NOT fork gates (node.fork_to).
        Fork gates create parallel DAG branches requiring branch-aware contract
        checking, which is out of scope for this pass.
        """
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="gate_in",
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_gate(
            "g1", "gate_in", {"a": "path_a", "b": "path_b"},
        ))
        state = state.with_node(self._make_transform(
            "ta", "path_a", "out_a",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_node(self._make_transform(
            "tb", "path_b", "out_b",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output("out_a"))
        state = state.with_output(self._make_output("out_b"))
        state = state.with_edge(self._make_edge("e1", "source", "g1"))
        state = state.with_edge(self._make_edge("e2", "g1", "ta"))
        state = state.with_edge(self._make_edge("e3", "g1", "tb"))
        result = state.validate()
        assert result.is_valid, result.errors

    def test_multi_hop_transform_no_schema_breaks_chain(self) -> None:
        """Test 13: Transform A has no schema — transform B's requirements fail."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        # Transform A: no schema, no requirements — passes through
        state = state.with_node(self._make_transform("ta", "t1", "ta_out"))
        # Transform B: requires 'text' but ta guarantees nothing
        state = state.with_node(self._make_transform(
            "tb", "ta_out", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "ta"))
        state = state.with_edge(self._make_edge("e2", "ta", "tb"))
        result = state.validate()
        assert not result.is_valid
        assert any("text" in e.message for e in result.errors)

    def test_transform_then_gate_walk_back_terminates(self) -> None:
        """Test 14b: source → transform A (no schema) → gate → transform B (requires text).

        The gate walk-back should stop at transform A (not a gate), and
        transform A has no schema so it guarantees nothing. Transform B's
        requirement should fail.
        """
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="ta_in",
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        # Transform A: no schema, no requirements
        state = state.with_node(self._make_transform("ta", "ta_in", "gate_in"))
        # Gate after transform A
        state = state.with_node(self._make_gate(
            "g1", "gate_in", {"high": "tb_in", "low": "sink"},
        ))
        # Transform B: requires 'text', downstream of gate
        state = state.with_node(self._make_transform(
            "tb", "tb_in", "out",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output("out"))
        state = state.with_output(self._make_output("sink"))
        state = state.with_edge(self._make_edge("e1", "source", "ta"))
        state = state.with_edge(self._make_edge("e2", "ta", "g1"))
        state = state.with_edge(self._make_edge("e3", "g1", "tb"))
        result = state.validate()
        # Walk-back: tb's producer is g1 (gate) → walk back to g1's producer → ta (not gate, stop)
        # ta has no schema → guarantees nothing → contract violation
        assert not result.is_valid
        assert any("text" in e.message for e in result.errors)

    def test_multi_sink_gate_routing(self) -> None:
        """Test 14c: Gate routes to multiple sinks — contract check per route."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="gate_in",
            options={"schema": {"mode": "observed"}},
        ))
        state = state.with_node(self._make_gate(
            "g1", "gate_in", {"high": "sink_a", "low": "sink_b"},
        ))
        state = state.with_output(self._make_output("sink_a"))
        state = state.with_output(self._make_output("sink_b"))
        state = state.with_edge(self._make_edge("e1", "source", "g1"))
        state = state.with_edge(self._make_edge("e2", "g1", "sink_a"))
        state = state.with_edge(self._make_edge("e3", "g1", "sink_b"))
        result = state.validate()
        # No consumer nodes with required_input_fields — should be valid
        assert result.is_valid, result.errors

    def test_mixed_consumer_requirements_from_same_producer(self) -> None:
        """Test 14d: One producer feeds two consumers — one satisfied, one violated."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="gate_in",
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_gate(
            "g1", "gate_in", {"a": "path_a", "b": "path_b"},
        ))
        # Consumer A: requires "text" — satisfied by source
        state = state.with_node(self._make_transform(
            "ta", "path_a", "out_a",
            options={"required_input_fields": ["text"]},
        ))
        # Consumer B: requires "score" — NOT guaranteed by source
        state = state.with_node(self._make_transform(
            "tb", "path_b", "out_b",
            options={"required_input_fields": ["score"]},
        ))
        state = state.with_output(self._make_output("out_a"))
        state = state.with_output(self._make_output("out_b"))
        state = state.with_edge(self._make_edge("e1", "source", "g1"))
        state = state.with_edge(self._make_edge("e2", "g1", "ta"))
        state = state.with_edge(self._make_edge("e3", "g1", "tb"))
        result = state.validate()
        # Pipeline should fail — consumer B's requirement is unsatisfied
        assert not result.is_valid
        assert any("score" in e.message for e in result.errors)
        # Consumer A's contract should be satisfied
        ta_contract = next(ec for ec in result.edge_contracts if ec.to_id == "ta")
        assert ta_contract.satisfied is True
        # Consumer B's contract should be violated
        tb_contract = next(ec for ec in result.edge_contracts if ec.to_id == "tb")
        assert tb_contract.satisfied is False
        assert "score" in tb_contract.missing_fields

    # --- Guard tests ---

    def test_node_id_source_is_reserved(self) -> None:
        """Test 14e: A node with id='source' triggers an error and aborts the pass.

        The id 'source' is a reserved sentinel used in the producer map and
        walk-back termination. If a node used this id, the walk-back would
        terminate prematurely (thinking it reached the source) and the
        producer map would silently conflict with the real source entry.
        The guard detects this and returns early with an error.
        """
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        # Node with reserved id="source" — should be caught by the guard
        state = state.with_node(self._make_transform(
            "source", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "source"))
        result = state.validate()
        assert not result.is_valid
        assert any("reserved" in e.message.lower() for e in result.errors)

    def test_bare_string_required_input_fields_emits_error(self) -> None:
        """Test 14f: required_input_fields as a bare string emits a validation error.

        If required_input_fields is 'text' instead of ['text'], frozenset('text')
        would produce {'t', 'e', 'x'} — a silent, hard-to-debug bug. The guard
        in _get_required_fields detects bare strings and emits a ValidationEntry
        instead of silently corrupting the field set.
        """
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": "text"},  # bare string, not list
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("bare string" in e.message.lower() for e in result.errors)
```

- [ ] **Step 2: Run topology tests**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation -v -k "gate or route_gate or multi_hop or multi_sink or mixed_consumer or reserved or bare_string"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/web/composer/test_state.py
git commit -m "test(composer): add topology test cases for schema contract validation"
```

---

### Task 4: Add EdgeContract Data Integrity Tests (15-16)

**Files:**
- Test: `tests/unit/web/composer/test_state.py`

- [ ] **Step 1: Write edge contract data tests**

Append to `TestSchemaContractValidation`:

```python
    # --- Data integrity ---

    def test_edge_contracts_populated_correctly(self) -> None:
        """Test 15: ValidationSummary.edge_contracts has correct entries."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()

        assert len(result.edge_contracts) >= 1
        contract = next(ec for ec in result.edge_contracts if ec.to_id == "t1")
        assert contract.from_id == "source"
        assert "text" in contract.producer_guarantees
        assert "text" in contract.consumer_requires
        assert contract.satisfied is True

    def test_edge_contract_to_dict_serialization(self) -> None:
        """Test 16: EdgeContract.to_dict() uses 'from'/'to' keys."""
        from elspeth.web.composer.state import EdgeContract

        ec = EdgeContract(
            from_id="source",
            to_id="t1",
            producer_guarantees=("text",),
            consumer_requires=("text",),
            missing_fields=(),
            satisfied=True,
        )
        d = ec.to_dict()
        # 'from' is a Python keyword — verify it's used as JSON key
        assert "from" in d
        assert "to" in d
        assert "from_id" not in d
        assert "to_id" not in d
```

- [ ] **Step 2: Run data integrity tests**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation -v -k "edge_contract"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/web/composer/test_state.py
git commit -m "test(composer): add edge contract data integrity tests"
```

---

### Task 5: Expose `edge_contracts` in Preview Response

**Files:**
- Modify: `src/elspeth/web/composer/tools.py:2599-2624`
- Test: `tests/unit/web/composer/test_tools.py`

- [ ] **Step 1: Write failing test for preview response**

Add to the preview test class in `tests/unit/web/composer/test_tools.py` (alongside `test_preview_valid_pipeline`):

```python
    def test_preview_pipeline_includes_edge_contracts(self) -> None:
        """Test 17: preview_pipeline response includes edge_contracts with field data."""
        state = _empty_state()
        catalog = _mock_catalog()
        # Build a pipeline with source (fixed schema) + transform (required_input_fields)
        r1 = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"path": "/data/in.csv", "schema": {"mode": "fixed", "fields": ["text: str"]}},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
        )
        r2 = execute_tool(
            "upsert_node",
            {
                "id": "t1",
                "node_type": "transform",
                "plugin": "value_transform",
                "input": "t1",
                "on_success": "main",
                "options": {"required_input_fields": ["text"], "operations": [{"field": "out", "expression": "row['text']"}]},
            },
            r1.updated_state,
            catalog,
        )
        r3 = execute_tool(
            "set_output",
            {"sink_name": "main", "plugin": "csv", "options": {"path": "outputs/out.csv"}, "on_write_failure": "discard"},
            r2.updated_state,
            catalog,
        )
        r4 = execute_tool("preview_pipeline", {}, r3.updated_state, catalog)

        assert r4.success is True
        assert "edge_contracts" in r4.data
        contracts = r4.data["edge_contracts"]
        assert len(contracts) >= 1
        # Find the source→t1 contract
        source_to_t1 = next(c for c in contracts if c["to"] == "t1")
        assert source_to_t1["from"] == "source"
        assert "text" in source_to_t1["producer_guarantees"]
        assert "text" in source_to_t1["consumer_requires"]
        assert source_to_t1["satisfied"] is True
        # Verify consistency: is_valid should be True since contract is satisfied
        assert r4.data["is_valid"] is True
```

- [ ] **Step 2: Modify `_execute_preview_pipeline()` to include edge_contracts**

In `src/elspeth/web/composer/tools.py`, in the `_execute_preview_pipeline()` function, add `edge_contracts` to the summary dict (after line 2608):

```python
    summary: dict[str, Any] = {
        "is_valid": validation.is_valid,
        "errors": [e.to_dict() for e in validation.errors],
        "warnings": [e.to_dict() for e in validation.warnings],
        "suggestions": [e.to_dict() for e in validation.suggestions],
        "edge_contracts": [ec.to_dict() for ec in validation.edge_contracts],
        "source": None,
        "node_count": len(state.nodes),
        "output_count": len(state.outputs),
        "nodes": [{"id": n.id, "node_type": n.node_type, "plugin": n.plugin} for n in state.nodes],
        "outputs": [{"name": o.name, "plugin": o.plugin} for o in state.outputs],
    }
```

- [ ] **Step 3: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_tools.py -v -k "edge_contract"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/elspeth/web/composer/tools.py tests/unit/web/composer/test_tools.py
git commit -m "feat(composer): expose edge_contracts in preview_pipeline response"
```

---

### Task 6: Add Enforcement Comment and Auto-Declare Guaranteed Fields in `text_source.py`

**Files:**
- Modify: `src/elspeth/plugins/sources/text_source.py`

- [ ] **Step 1: Add enforcement comment**

In `src/elspeth/plugins/sources/text_source.py`, at line 109 (the `yield from self._validate_and_yield({self._column: value}, ctx)` line), add a comment:

```python
                    # Composer heuristic depends on this: web/composer/state.py
                    # infers {self._column} as a guaranteed output field for the
                    # text source. If you change which key the row uses, update
                    # _check_schema_contracts() in state.py.
                    yield from self._validate_and_yield(
                        {self._column: value},
                        ctx,
                    )
```

- [ ] **Step 2: Auto-declare `guaranteed_fields` in `__init__`**

In `TextSource.__init__()`, after `self._schema_config = cfg.schema_config` (line 72), add logic to auto-declare the column as a guaranteed field when the schema doesn't already declare one. This ensures the runtime's `SchemaConfig.get_effective_guaranteed_fields()` returns `{column}` — matching the composer's heuristic inference.

```python
        self._schema_config = cfg.schema_config

        # Auto-declare {column} as a guaranteed output field when the schema
        # is observed with no explicit guaranteed_fields. TextSource always
        # produces {column: value} for every row — this is a provable invariant,
        # not an inference. The composer's heuristic in web/composer/state.py
        # (_TEXT_HEURISTIC_PLUGINS) mirrors this logic so both validators agree.
        #
        # This makes text sources "just work" without requiring the user or LLM
        # to know about schema modes: observed text sources pass contract checks
        # for downstream consumers that require the column field.
        if (
            self._schema_config is not None
            and not self._schema_config.declares_guaranteed_fields
            and self._column
        ):
            # Rebuild schema config with guaranteed_fields including the column.
            # Use from_dict on a modified dict to preserve all other settings.
            schema_dict = cfg.raw_schema_dict.copy()
            existing = list(schema_dict.get("guaranteed_fields", []))
            if self._column not in existing:
                existing.append(self._column)
            schema_dict["guaranteed_fields"] = existing
            self._schema_config = SchemaConfig.from_dict(schema_dict)
```

Note: This requires `TextSourceConfig` to expose `raw_schema_dict` (the original schema dict before parsing). If it doesn't exist, extract it from `config.get("schema", {})` instead:

```python
        # Alternative if raw_schema_dict is not available:
        if (
            self._schema_config is not None
            and not self._schema_config.declares_guaranteed_fields
            and self._column
        ):
            schema_dict = dict(config.get("schema", {}))
            existing = list(schema_dict.get("guaranteed_fields", []))
            if self._column not in existing:
                existing.append(self._column)
            schema_dict["guaranteed_fields"] = existing
            self._schema_config = SchemaConfig.from_dict(schema_dict)
```

- [ ] **Step 3: Commit**

```bash
git add src/elspeth/plugins/sources/text_source.py
git commit -m "feat(text_source): auto-declare column as guaranteed field, add enforcement comment

TextSource always produces {column: value} — this is a provable invariant.
Auto-declaring guaranteed_fields makes the runtime's SchemaConfig agree with
the composer's heuristic, so both validators produce the same answer.
This removes the need for users/LLMs to know about schema modes for text sources."
```

---

### Task 7: Heuristic Enforcement Test

**Files:**
- Create: `tests/unit/web/composer/test_schema_contract_enforcement.py`

- [ ] **Step 1: Write the enforcement test**

```python
"""Enforcement test tying the composer's text-source heuristic to the plugin's actual behavior.

The composer's _check_schema_contracts() infers that a text source with
column='X' always produces rows containing key 'X'. TextSource.__init__
auto-declares {column} as a guaranteed field in its schema config. This test
verifies both sides agree: the plugin produces the key AND declares it as
guaranteed. If either side changes, this test fails.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from elspeth.contracts.contexts import SourceContext
from elspeth.contracts.schema import SchemaConfig
from elspeth.plugins.sources.text_source import TextSource


class TestTextSourceHeuristicEnforcement:
    def test_text_source_produces_configured_column_key(self) -> None:
        """Test 20a: Text source output key matches the composer heuristic assumption.

        The composer's _check_schema_contracts() infers that a text source with
        column='text' guarantees field 'text' in its output. This test verifies
        that TextSource actually produces rows with that key.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            config: dict[str, Any] = {
                "path": tmp_path,
                "column": "text",
                "schema": {"mode": "observed"},
            }
            source = TextSource(config)
            ctx = MagicMock(spec=SourceContext)
            ctx.record_validation_error = MagicMock()

            rows = list(source.load(ctx))
            assert len(rows) >= 1
            # The critical assertion: the row contains the configured column key
            first_row = rows[0].row
            assert "text" in first_row, (
                f"TextSource with column='text' must produce rows with key 'text'. "
                f"Got keys: {list(first_row.keys())}. "
                f"The composer heuristic in web/composer/state.py depends on this."
            )
            assert first_row["text"] == "hello"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_text_source_auto_declares_guaranteed_fields(self) -> None:
        """Test 20b: TextSource auto-declares {column} as guaranteed in its schema config.

        The runtime's get_guaranteed_fields() reads SchemaConfig from the plugin.
        TextSource.__init__ must auto-populate guaranteed_fields so the runtime
        agrees with the composer's heuristic. Without this, the composer says
        "valid" but the runtime rejects — the exact bug this plan fixes.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            config: dict[str, Any] = {
                "path": tmp_path,
                "column": "text",
                "schema": {"mode": "observed"},
            }
            source = TextSource(config)

            # After __init__, the schema config should declare "text" as guaranteed
            guaranteed = source._schema_config.get_effective_guaranteed_fields()
            assert "text" in guaranteed, (
                f"TextSource with column='text' must auto-declare 'text' as a "
                f"guaranteed field in its schema config. Got: {guaranteed}. "
                f"Without this, runtime rejects pipelines the composer approves."
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_text_source_preserves_explicit_guaranteed_fields(self) -> None:
        """Test 20c: TextSource does not override explicit guaranteed_fields."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            config: dict[str, Any] = {
                "path": tmp_path,
                "column": "text",
                "schema": {"mode": "observed", "guaranteed_fields": ["custom_field"]},
            }
            source = TextSource(config)

            # Explicit guaranteed_fields should be preserved, not overridden
            guaranteed = source._schema_config.get_effective_guaranteed_fields()
            assert "custom_field" in guaranteed, (
                "Explicit guaranteed_fields must be preserved"
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_schema_contract_enforcement.py -v`
Expected: PASS — TextSource now auto-declares guaranteed_fields (Task 6 step 2)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/web/composer/test_schema_contract_enforcement.py
git commit -m "test(composer): add enforcement tests tying composer heuristic to text_source behavior"
```

---

### Task 8: Composer/Runtime Agreement Test

**Files:**
- Create: `tests/integration/web/test_composer_runtime_agreement.py`

- [ ] **Step 1: Write the agreement test**

This test builds the same pipeline configuration, validates it through both the composer and the runtime DAG validator, and asserts they agree.

```python
"""Composer/runtime agreement test.

Verifies that the composer's schema contract validation and the runtime
DAG validator agree on pass/fail for the same pipeline configuration.
Prevents the two validators from silently diverging.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.core.config import ElspethSettings, SinkSettings, SourceSettings, TransformSettings
from elspeth.core.dag.graph import ExecutionGraph, GraphValidationError
from elspeth.web.composer.state import (
    CompositionState,
    EdgeSpec,
    NodeSpec,
    OutputSpec,
    PipelineMetadata,
    SourceSpec,
)


class TestComposerRuntimeAgreement:
    """Test 19: Composer and runtime validators agree on schema contracts."""

    def _empty_state(self) -> CompositionState:
        return CompositionState(
            source=None, nodes=(), edges=(), outputs=(),
            metadata=PipelineMetadata(), version=1,
        )

    def _build_runtime_graph(
        self,
        source_plugin: str,
        source_options: dict[str, Any],
        transform_options: dict[str, Any],
        sink_options: dict[str, Any],
    ) -> ExecutionGraph:
        """Build a runtime ExecutionGraph using the correct API.

        Uses ElspethSettings -> instantiate_plugins_from_config -> from_plugin_instances,
        matching the pattern in existing integration tests.
        """
        config = ElspethSettings(
            source=SourceSettings(
                plugin=source_plugin,
                on_success="t1",
                options={**source_options, "on_validation_failure": "discard"},
            ),
            transforms=[
                TransformSettings(
                    name="t1",
                    plugin="value_transform",
                    input="t1",
                    on_success="main",
                    on_error="discard",
                    options=transform_options,
                ),
            ],
            sinks={
                "main": SinkSettings(
                    plugin="csv",
                    on_write_failure="discard",
                    options=sink_options,
                ),
            },
        )
        plugins = instantiate_plugins_from_config(config)
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins.source,
            source_settings=plugins.source_settings,
            transforms=plugins.transforms,
            sinks=plugins.sinks,
            aggregations=plugins.aggregations,
            gates=list(config.gates),
        )
        return graph

    def test_both_reject_missing_required_field(self) -> None:
        """Both validators reject: observed source, consumer requires 'text'."""
        # --- Composer validation ---
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            state = self._empty_state()
            state = state.with_source(SourceSpec(
                plugin="text",
                on_success="t1",
                options={
                    "path": tmp_path,
                    "column": "line",
                    "schema": {"mode": "observed"},
                },
                on_validation_failure="quarantine",
            ))
            state = state.with_node(NodeSpec(
                id="t1", node_type="transform", plugin="value_transform",
                input="t1", on_success="main", on_error=None,
                options={
                    "required_input_fields": ["text"],
                    "operations": [{"field": "out", "expression": "row['text'] + ' world'"}],
                    "schema": {"mode": "observed"},
                },
                condition=None, routes=None, fork_to=None,
                branches=None, policy=None, merge=None,
            ))
            state = state.with_output(OutputSpec(
                name="main", plugin="csv",
                options={"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                on_write_failure="discard",
            ))
            state = state.with_edge(EdgeSpec(
                id="e1", from_node="source", to_node="t1",
                edge_type="on_success", label=None,
            ))

            composer_result = state.validate()

            # Composer should reject — consumer requires 'text' but source
            # column is 'line', and schema is observed with no guarantees.
            # Observed mode guarantees nothing regardless of plugin type.
            assert not composer_result.is_valid, (
                "Composer should reject: source column is 'line' but consumer requires 'text'"
            )
            assert any("schema contract violation" in e.message.lower() for e in composer_result.errors)

            # --- Runtime validation ---
            # Build the same pipeline through the runtime path and verify it also rejects.
            try:
                graph = self._build_runtime_graph(
                    source_plugin="text",
                    source_options={"path": tmp_path, "column": "line", "schema": {"mode": "observed"}},
                    transform_options={
                        "required_input_fields": ["text"],
                        "operations": [{"field": "out", "expression": "row['text'] + ' world'"}],
                        "schema": {"mode": "observed"},
                    },
                    sink_options={"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                )
                graph.validate_edge_compatibility()
                pytest.fail(
                    "Runtime should have rejected: consumer requires 'text' "
                    "but source column is 'line' (observed schema)"
                )
            except GraphValidationError as exc:
                assert "text" in str(exc).lower() or "required" in str(exc).lower(), (
                    f"Runtime rejected but for unexpected reason: {exc}"
                )

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_both_accept_satisfied_contract(self) -> None:
        """Both validators accept: fixed source with guaranteed field."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            state = self._empty_state()
            state = state.with_source(SourceSpec(
                plugin="text",
                on_success="t1",
                options={
                    "path": tmp_path,
                    "column": "text",
                    "schema": {"mode": "fixed", "fields": ["text: str"]},
                },
                on_validation_failure="quarantine",
            ))
            state = state.with_node(NodeSpec(
                id="t1", node_type="transform", plugin="value_transform",
                input="t1", on_success="main", on_error=None,
                options={
                    "required_input_fields": ["text"],
                    "operations": [{"field": "out", "expression": "row['text'] + ' world'"}],
                    "schema": {"mode": "observed"},
                },
                condition=None, routes=None, fork_to=None,
                branches=None, policy=None, merge=None,
            ))
            state = state.with_output(OutputSpec(
                name="main", plugin="csv",
                options={"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                on_write_failure="discard",
            ))
            state = state.with_edge(EdgeSpec(
                id="e1", from_node="source", to_node="t1",
                edge_type="on_success", label=None,
            ))

            composer_result = state.validate()
            assert composer_result.is_valid, composer_result.errors

            # --- Runtime validation ---
            graph = self._build_runtime_graph(
                source_plugin="text",
                source_options={"path": tmp_path, "column": "text", "schema": {"mode": "fixed", "fields": ["text: str"]}},
                transform_options={
                    "required_input_fields": ["text"],
                    "operations": [{"field": "out", "expression": "row['text'] + ' world'"}],
                    "schema": {"mode": "observed"},
                },
                sink_options={"path": "outputs/out.csv", "schema": {"mode": "observed"}},
            )
            graph.validate_edge_compatibility()
            # If we reach here, runtime agrees with composer: both accept

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_both_accept_observed_text_source_with_auto_guarantee(self) -> None:
        """Both validators accept: text source with observed schema + column guarantee.

        This is the critical agreement case that validates the heuristic/auto-declare
        pattern. The composer's heuristic infers {column} as guaranteed for text
        sources. TextSource.__init__ auto-declares {column} as guaranteed_fields
        in its schema config. Both validators call
        SchemaConfig.get_effective_guaranteed_fields() and get the same answer.

        If either the composer heuristic or the TextSource auto-declaration is
        removed without removing the other, this test fails — catching the
        divergence that would cause false positives or false negatives.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            state = self._empty_state()
            state = state.with_source(SourceSpec(
                plugin="text",
                on_success="t1",
                options={
                    "path": tmp_path,
                    "column": "text",
                    "schema": {"mode": "observed"},
                },
                on_validation_failure="quarantine",
            ))
            state = state.with_node(NodeSpec(
                id="t1", node_type="transform", plugin="value_transform",
                input="t1", on_success="main", on_error=None,
                options={
                    "required_input_fields": ["text"],
                    "operations": [{"field": "out", "expression": "row['text'] + ' world'"}],
                    "schema": {"mode": "observed"},
                },
                condition=None, routes=None, fork_to=None,
                branches=None, policy=None, merge=None,
            ))
            state = state.with_output(OutputSpec(
                name="main", plugin="csv",
                options={"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                on_write_failure="discard",
            ))
            state = state.with_edge(EdgeSpec(
                id="e1", from_node="source", to_node="t1",
                edge_type="on_success", label=None,
            ))

            # Composer should accept — heuristic infers {column} as guaranteed
            composer_result = state.validate()
            assert composer_result.is_valid, (
                "Composer should accept: text heuristic infers 'text' from column"
            )

            # Runtime should also accept — TextSource auto-declares guaranteed_fields
            graph = self._build_runtime_graph(
                source_plugin="text",
                source_options={"path": tmp_path, "column": "text", "schema": {"mode": "observed"}},
                transform_options={
                    "required_input_fields": ["text"],
                    "operations": [{"field": "out", "expression": "row['text'] + ' world'"}],
                    "schema": {"mode": "observed"},
                },
                sink_options={"path": "outputs/out.csv", "schema": {"mode": "observed"}},
            )
            graph.validate_edge_compatibility()
            # If we reach here, both agree: accept

        finally:
            Path(tmp_path).unlink(missing_ok=True)
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/integration/web/test_composer_runtime_agreement.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/web/test_composer_runtime_agreement.py
git commit -m "test(integration): add composer/runtime agreement test for schema contracts"
```

---

### Task 9: Regression Test for the Original Bug

**Files:**
- Test: `tests/unit/web/composer/test_state.py`

- [ ] **Step 1: Write regression test**

Append to `TestSchemaContractValidation`:

```python
    # --- Regression test ---

    def test_text_heuristic_rescues_original_bug_scenario(self) -> None:
        """Test 18: The original bug scenario now passes thanks to the text heuristic.

        text source (column=text, observed schema) + value_transform
        (required_input_fields=["text"]) + csv output.

        The original bug: composer had NO contract checking at all, so it
        reported is_valid=True for any pipeline regardless of field contracts.
        The regression guard for that bug is test_observed_schema_no_guarantees_fails
        (test 6), which uses a non-text source with no heuristic.

        This test confirms the text heuristic correctly infers 'text' from
        column='text', so the specific original scenario is now valid (correctly).
        The runtime agrees because TextSource auto-declares {column} as
        guaranteed in its schema config (Task 6b).
        """
        state = self._empty_state()
        state = state.with_source(self._make_source(
            plugin="text",
            options={"column": "text", "schema": {"mode": "observed"}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={
                "required_input_fields": ["text"],
                "operations": [{"field": "combined", "expression": "row['text'] + ' world'"}],
            },
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))

        result = state.validate()
        # With the text heuristic, this now passes (correctly)
        assert result.is_valid, result.errors
        # edge_contracts must confirm the contract is satisfied
        assert any(
            ec.to_id == "t1" and ec.satisfied
            for ec in result.edge_contracts
        )
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_text_heuristic_rescues_original_bug_scenario -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/web/composer/test_state.py
git commit -m "test(composer): add regression test for original false-positive schema bug"
```

---

### Task 10: Patch the Pipeline Composer Skill

**Files:**
- Modify: `src/elspeth/web/composer/skills/pipeline_composer.md:102-113, 353-357, 116`

- [ ] **Step 1: Add completion criteria item 4**

In `pipeline_composer.md`, after line 107 (`3. All required plugin options are filled with meaningful values (not empty)`), add:

```markdown
4. **All edge contracts are satisfied** — every downstream step's `required_input_fields` must be guaranteed by its upstream producer. Check `edge_contracts` in the preview response. If any edge shows `"satisfied": false`, the pipeline is not complete. If `edge_contracts` is empty (`[]`), this means no field contracts were declared by any node — it does **not** mean all contracts are satisfied. Pipelines without `required_input_fields` declarations are not verified by the composer's contract check; the runtime validator is the final authority.
```

- [ ] **Step 2: Add text source safety rule**

After line 356 (`- When wiring a text file via \`set_source_from_blob\`, you MUST pass...`), add:

```markdown
- **Schema rule for text sources:** When downstream steps reference the text column by name (via `required_input_fields` or expressions like `row['text']`), always configure the source with a `fixed` schema declaring that field: `{"column": "text", "schema": {"mode": "fixed", "fields": ["text: str"]}}`. Do not rely on `observed` schema when downstream steps have field requirements. The `observed` mode guarantees no fields to downstream consumers.
```

- [ ] **Step 2b: Add forward-reference in schema mode section**

In the "Choosing the right mode" bullet list (around line 143), after the `- **Sources:** Match the mode to how well you know the input data...` bullet, add:

```markdown
  **Exception:** If downstream steps declare `required_input_fields` or reference fields by name, use `fixed` or `flexible` — not `observed`. See the text source safety rule in "Plugin Quick Reference > Sources > text" below.
```

- [ ] **Step 3: Add fix flow example**

After the "Tool Failure Recovery" section (after line 127), add a new subsection:

```markdown
#### Fixing Schema Contract Violations

When `preview_pipeline` returns an unsatisfied edge contract, follow this sequence:

1. **Read the violation** — identify which edge failed, what fields are missing, and which node is the producer.
2. **Patch the producer schema** — typically `patch_source_options` to change from `observed` to `fixed` with the required fields declared:
   ```json
   patch_source_options({
     "patch": {"schema": {"mode": "fixed", "fields": ["text: str"]}}
   })
   ```
3. **Re-preview** — call `preview_pipeline` and verify the edge now shows `"satisfied": true`.
4. **Only then report success.**

**Example — text source + value_transform:**
- `preview_pipeline` returns: `edge_contracts: [{"from": "source", "to": "add_world", "satisfied": false, "consumer_requires": ["text"], "producer_guarantees": []}]`
- Fix: `patch_source_options({"patch": {"schema": {"mode": "fixed", "fields": ["text: str"]}}})`
- Re-preview confirms: `"satisfied": true`

If `get_pipeline_state` and `preview_pipeline` disagree (e.g., state shows a field but preview shows an unsatisfied contract), treat this as unresolved. Do not report success. Re-run both tools, fix the discrepancy, and confirm before responding.

#### Known Limitation: Intermediate Transforms Break the Guarantee Chain

Transforms without explicit schema declarations report zero guaranteed fields to downstream consumers — even schema-preserving transforms like `passthrough`. If a transform sits between a source and a consumer with `required_input_fields`, the contract check will report a violation even though the data flows through unchanged.

**Fix:** Either add a `schema` to the intermediate transform declaring the fields it passes through, or move `required_input_fields` to the first transform in the chain (directly downstream of the source). The source→first-consumer edge is where contract checking is most reliable.

#### Non-Converging Contract Violations

If `preview_pipeline` still shows `"satisfied": false` after patching the producer schema, **stop patching and explain the limitation to the user.** The most common cause is an intermediate transform that does not propagate schema guarantees (see above). Do not repeatedly call `patch_source_options` or `patch_node_options` trying different schema configurations — if one patch didn't resolve it, the issue is structural, not a missing field declaration. Ask the user whether to:
1. Add an explicit `schema` declaration on the intermediate transform, or
2. Accept that this contract cannot be verified at composition time (the runtime validator will still check it).
```

- [ ] **Step 4: Run skill drift test to check for regressions**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_skill_drift.py -v`
Expected: PASS (or update the drift test if it checks for specific content hashes)

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/web/composer/skills/pipeline_composer.md
git commit -m "docs(skill): add schema contract completion criteria, text source rule, fix flow example"
```

---

### Task 11: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full unit test suite**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/ -v`
Expected: All PASS

- [ ] **Step 2: Run integration tests**

Run: `.venv/bin/python -m pytest tests/integration/web/ -v`
Expected: All PASS

- [ ] **Step 3: Run type checker**

Run: `.venv/bin/python -m mypy src/elspeth/web/composer/state.py src/elspeth/web/composer/tools.py`
Expected: No errors

- [ ] **Step 4: Run linter**

Run: `.venv/bin/python -m ruff check src/elspeth/web/composer/state.py src/elspeth/web/composer/tools.py`
Expected: No errors

- [ ] **Step 5: Run tier model enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: No new violations (the deferred import of `SchemaConfig` from L0 into L3 is layer-legal)

- [ ] **Step 6: Register follow-up issue for expanded agreement tests**

The composer/runtime agreement test (Task 8) covers two scenarios: reject (wrong field) and accept (correct fixed schema). It does NOT cover coalesce-merge topologies, type-level schema compatibility, or aggregation node nested options — cases where the runtime validator checks properties the composer does not. These gaps are expected (documented in the spec's "What This Doesn't Catch" table) but should be tracked for future expansion.

Create a Filigree issue:
```bash
filigree create "Expand composer/runtime agreement tests — coalesce, type-level, aggregation" \
  --type=task --priority=3 \
  --description="The agreement test in tests/integration/web/test_composer_runtime_agreement.py covers two basic scenarios (reject + accept). Expand to cover: (1) coalesce-merge branch intersection, (2) type-level schema compatibility (Pydantic schema construction), (3) aggregation nodes with nested schema options. These are cases where runtime may reject but the composer currently cannot check. See docs/superpowers/specs/2026-04-14-composer-schema-contract-validation-design.md 'What This Doesn't Catch' table."
```
