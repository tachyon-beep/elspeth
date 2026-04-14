# Composer Schema Contract Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the composer reject pipelines with unsatisfied schema contracts at composition time, and expose per-edge contract data in the preview response.

**Architecture:** Add a new validation pass (pass 9) to `CompositionState.validate()` that walks the connection-field chain but reuses shared raw-config contract helpers extracted into `elspeth.contracts.schema` rather than re-implementing runtime semantics inline. The shared helpers are responsible for parsing schema config, computing producer guarantees, computing node consumer requirements (top-level `required_input_fields`, aggregation `options.required_input_fields`, then explicit `schema.required_fields`), computing sink consumer requirements via `schema.get_effective_required_fields()`, and applying the closed-list observed-only text-source deterministic guarantee rule. Extend `ValidationSummary` with `EdgeContract` tuples, update `ExecutionGraph` to delegate its raw-config requirement extraction to the same helpers, refactor the gate/coalesce walk-back into a shared helper in `state.py`, and patch the pipeline-composer skill with contract-aware completion criteria that remain stricter than today's behaviour.

**Tech Stack:** Python dataclasses (frozen), `SchemaConfig` from `elspeth.contracts.schema`, pytest

**Spec:** `docs/superpowers/specs/2026-04-14-composer-schema-contract-validation-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/elspeth/contracts/schema.py` | Modify | Add shared raw-config contract helpers used by both composer and runtime; centralize observed-only text-source guarantee rule and sink `get_effective_required_fields()` semantics |
| `src/elspeth/core/dag/graph.py` | Modify | Delegate raw-config consumer requirement extraction to the shared helpers instead of maintaining a second copy of the logic |
| `src/elspeth/web/composer/state.py` | Modify | Add `EdgeContract` dataclass, extend `ValidationSummary`, add `_check_schema_contracts()` connection-walk that calls the shared helpers, call it from `validate()` |
| `src/elspeth/web/composer/tools.py` | Modify | Serialize `edge_contracts` in `_execute_preview_pipeline()` |
| `src/elspeth/plugins/sources/text_source.py` | Modify | Auto-declare `guaranteed_fields` for deterministic observed-schema output only + enforcement comment |
| `src/elspeth/web/composer/skills/pipeline_composer.md` | Modify | Add completion criteria item 4, align guidance with the observed-text special-case without weakening the general validation stance, fix flow example |
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
- Modify: `src/elspeth/contracts/schema.py`
- Modify: `src/elspeth/core/dag/graph.py`
- Modify: `src/elspeth/web/composer/state.py:460-775`
- Test: `tests/unit/web/composer/test_state.py`

This is the core implementation. We write tests first for the positive and negative cases, then extract shared raw-config contract helpers into `elspeth.contracts.schema`, delegate the runtime's raw-config requirement reads to those helpers, and finally implement `_check_schema_contracts()` on top of the shared layer.

**Dependency note:** The generic contract pass can land before the observed-text special case, but the observed-text acceptance rule must not be enabled in composer unless Task 6 Step 2 lands in the same changeset or earlier. If tasks are committed atomically, keep the observed-text-positive composer tests (`test_text_heuristic_infers_guarantee`, Task 8 observed-text accept, and Task 9's reported scenario regression) out of the Task 2 commit and enable them only when the runtime has matching backing.

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

    def _make_coalesce(
        self,
        id: str,
        input: str,
        on_success: str,
        branches: tuple[str, ...] = ("branch_a", "branch_b"),
        policy: str = "require_all",
        merge: str = "nested",
    ) -> NodeSpec:
        return NodeSpec(
            id=id,
            node_type="coalesce",
            plugin=None,
            input=input,
            on_success=on_success,
            on_error=None,
            options={},
            condition=None,
            routes=None,
            fork_to=None,
            branches=branches,
            policy=policy,
            merge=merge,
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

        Staging rule: this test must land with Task 6, not in the initial
        generic contract-pass commit, because runtime backing is added there.
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
        """Test 5: Consumer with required_input_fields: [] and no schema.required_fields — no error."""
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

    def test_sink_required_fields_satisfied(self) -> None:
        """Test 5b: Sink required_fields satisfied by upstream guarantees."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="main",
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_output(OutputSpec(
            name="main",
            plugin="csv",
            options={
                "path": "outputs/main.csv",
                "schema": {"mode": "observed", "required_fields": ["text"]},
            },
            on_write_failure="discard",
        ))
        result = state.validate()
        assert result.is_valid, result.errors
        sink_contract = next(ec for ec in result.edge_contracts if ec.to_id == "output:main")
        assert sink_contract.satisfied is True
        assert "text" in sink_contract.consumer_requires

    def test_consumer_schema_required_fields_satisfied(self) -> None:
        """Test 5c: Consumer falls back to explicit schema.required_fields."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"schema": {"mode": "observed", "required_fields": ["text"]}},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors
        edge_contract = next(ec for ec in result.edge_contracts if ec.to_id == "t1")
        assert edge_contract.satisfied is True
        assert edge_contract.consumer_requires == ("text",)
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

    def test_sink_required_fields_violation_fails(self) -> None:
        """Test 10b: Sink required_fields violated by upstream guarantees."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="main",
            options={"schema": {"mode": "fixed", "fields": ["line: str"]}},
        ))
        state = state.with_output(OutputSpec(
            name="main",
            plugin="csv",
            options={
                "path": "outputs/main.csv",
                "schema": {"mode": "observed", "required_fields": ["text"]},
            },
            on_write_failure="discard",
        ))
        result = state.validate()
        assert not result.is_valid
        assert any("sink" in e.message.lower() and "text" in e.message.lower() for e in result.errors)
        sink_contract = next(ec for ec in result.edge_contracts if ec.to_id == "output:main")
        assert sink_contract.satisfied is False
        assert "text" in sink_contract.missing_fields

    def test_consumer_schema_required_fields_violation_fails(self) -> None:
        """Test 10c: required_input_fields=[] still falls through to schema.required_fields."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["line: str"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={
                "required_input_fields": [],
                "schema": {"mode": "observed", "required_fields": ["text"]},
            },
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("text" in e.message for e in result.errors)

    def test_malformed_consumer_schema_emits_error(self) -> None:
        """Test 10d: Malformed consumer schema is a blocking error, not empty requirements."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_transform(
            "t1", "t1", "main",
            options={"schema": {"mode": "invalid_mode"}},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("schema" in e.message.lower() for e in result.errors)
        assert not any(ec.to_id == "t1" for ec in result.edge_contracts)
```

- [ ] **Step 4: Run negative tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_observed_schema_no_guarantees_fails tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_partial_match_fails tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_no_schema_config_fails tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_consumer_schema_required_fields_violation_fails tests/unit/web/composer/test_state.py::TestSchemaContractValidation::test_malformed_consumer_schema_emits_error -v`
Expected: FAIL (current validate() doesn't check contracts)

- [ ] **Step 5: Add shared raw-config helpers and implement `_check_schema_contracts()`**

In `src/elspeth/contracts/schema.py`, add a small public helper surface that both the composer and runtime can reuse:

```python
def parse_raw_schema_config(raw_schema: object, *, owner: str) -> SchemaConfig | None: ...
def get_raw_producer_guaranteed_fields(
    plugin_name: str | None,
    options: Mapping[str, Any],
    *,
    owner: str,
) -> frozenset[str]: ...
def get_raw_node_required_fields(
    options: Mapping[str, Any],
    *,
    owner: str,
    node_type: str | None = None,
) -> frozenset[str]: ...
def get_raw_sink_required_fields(
    options: Mapping[str, Any],
    *,
    owner: str,
) -> frozenset[str]: ...
```

Rules for the shared helper layer:

- `parse_raw_schema_config()` raises `ValueError` for malformed schema dicts.
- Define the closed-list observed-text heuristic marker at module scope in `src/elspeth/contracts/schema.py`, not inside a helper body:
  `_TEXT_HEURISTIC_PLUGINS: frozenset[str] = frozenset({"text"})`
  Keep the existing "do not extend without design review" comment adjacent to that constant so discoverability survives refactors.
- `get_raw_producer_guaranteed_fields()` uses `SchemaConfig.get_effective_guaranteed_fields()`. The observed-text special case is staged with Task 6 and applies only when `plugin_name == "text"`, `column` is a non-empty string, `schema.mode == "observed"`, and `declares_guaranteed_fields is False`.
- `get_raw_node_required_fields()` mirrors today's runtime `ExecutionGraph.get_required_fields()` semantics exactly: top-level `required_input_fields` first, then aggregation-nested `options["required_input_fields"]` when `node_type == "aggregation"` and the raw config is wrapper-shaped, then explicit `schema.required_fields`. An empty list does not block the fallback; `required_input_fields: []` means "no Priority 1 requirements declared", not "ignore schema.required_fields". Reject bare-string `required_input_fields` with `ValueError` at either level.
- `get_raw_sink_required_fields()` is intentionally stricter: parse the sink schema and return `schema.get_effective_required_fields()`, so fixed/flexible typed sink fields are treated as required even when `required_fields` is omitted explicitly.
- `state.py` and `graph.py` must not keep independent copies of the observed-text rule or sink requirement extraction.
- The helper surface must be shape-tolerant for aggregation configs: composer passes `node.options` directly, runtime passes the wrapped aggregation config whose plugin options live under `"options"`. The shared helper owns that normalization so the two call sites stay coupled.
- Keep helper side effects explicit. If a nested helper can append diagnostics, pass `errors`/`warnings` into it explicitly rather than mutating hidden closure state. In practice `_register_producer(..., errors)` and `_walk_to_real_producer(..., warnings)` should advertise their side effects in their signatures.

In `src/elspeth/core/dag/graph.py`, update the raw-config requirement extraction path to delegate to the shared helper surface instead of re-implementing the parsing logic inline. Runtime graph validation still owns graph walking, coalesce semantics, and `GraphValidationError`; the shared helper only owns raw-config contract semantics.

In `src/elspeth/web/composer/state.py`, keep the topology walk but replace the inline schema logic with deferred imports of the shared helpers:

```python
from elspeth.contracts.schema import (
    get_raw_node_required_fields,
    get_raw_producer_guaranteed_fields,
    get_raw_sink_required_fields,
)
```

Then implement `_check_schema_contracts()` with these rules:

- producer helper `ValueError` => emit blocking `ValidationEntry`, mark the producer as uncheckable, and suppress downstream edge contracts sourced from that producer
- node consumer helper `ValueError` => emit blocking `ValidationEntry` on that node and skip its edge contract rather than fabricating an empty requirement set. This includes malformed consumer `schema` dicts; they must not silently collapse to `frozenset()`.
- sink helper `ValueError` => emit blocking `ValidationEntry` on that output and skip its edge contract
- build `node_by_id = {node.id: node for node in nodes}` once near the top of the function and use it for all producer lookups
- extract the duplicated gate/coalesce walk-back from the node loop and sink loop into `_walk_to_real_producer(producer_id, *, producer_map, node_by_id, warnings)` so both paths share the same route-gate termination and coalesce warning/skip behavior
- build `EdgeContract` rows only when both sides parsed successfully
- `_check_schema_contracts()` may accumulate into local mutable lists, but its return type should be immutable tuples to match the surrounding frozen-dataclass design. Do not leak `tuple[list, list, list]` out of the helper boundary.

Key excerpt:

```python
def _check_schema_contracts(
    source: SourceSpec | None,
    nodes: tuple[NodeSpec, ...],
    outputs: tuple[OutputSpec, ...],
) -> tuple[
    tuple[ValidationEntry, ...],
    tuple[ValidationEntry, ...],
    tuple[EdgeContract, ...],
]:
    from elspeth.contracts.schema import (
        get_raw_node_required_fields,
        get_raw_producer_guaranteed_fields,
        get_raw_sink_required_fields,
    )

    errors: list[ValidationEntry] = []
    contract_warnings: list[ValidationEntry] = []
    edge_contracts: list[EdgeContract] = []
    parse_failed_producers: set[str] = set()
    node_by_id = {node.id: node for node in nodes}

    def _walk_to_real_producer(
        producer_id: str,
        *,
        producer_map: Mapping[str, tuple[str, str | None, Mapping[str, Any]]],
        node_by_id: Mapping[str, NodeSpec],
        warnings: list[ValidationEntry],
    ) -> str | None:
        ...

    ...

    for node in nodes:
        try:
            consumer_required = get_raw_node_required_fields(
                node.options,
                owner=f"node:{node.id}",
                node_type=node.node_type,
            )
        except ValueError as exc:
            errors.append(_err(f"node:{node.id}", f"Invalid contract config: {exc}", "high"))
            continue

        actual_id = _walk_to_real_producer(
            node.input,
            producer_map=producer_map,
            node_by_id=node_by_id,
            warnings=contract_warnings,
        )
        if actual_id is None:
            continue

        ...

        try:
            producer_guaranteed = get_raw_producer_guaranteed_fields(
                actual_plugin,
                actual_options,
                owner="source" if actual_id == "source" else f"node:{actual_id}",
            )
        except ValueError as exc:
            errors.append(
                _err(
                    "source" if actual_id == "source" else f"node:{actual_id}",
                    f"Invalid contract config: {exc}",
                    "high",
                )
            )
            parse_failed_producers.add(actual_id)
            continue

        ...

    for output in outputs:
        try:
            sink_required = get_raw_sink_required_fields(
                output.options,
                owner=f"output:{output.name}",
            )
        except ValueError as exc:
            errors.append(_err(f"output:{output.name}", f"Invalid contract config: {exc}", "high"))
            continue

        actual_id = _walk_to_real_producer(
            output.name,
            producer_map=producer_map,
            node_by_id=node_by_id,
            warnings=contract_warnings,
        )
        if actual_id is None:
            continue

    return tuple(errors), tuple(contract_warnings), tuple(edge_contracts)
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

- [ ] **Step 7: Run contract tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation -v`
Expected: All contract tests in this class PASS

- [ ] **Step 8: Run full test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py -v`
Expected: All tests PASS. The `test_validate_clean_pipeline_no_warnings` test should still pass because it has no `required_input_fields` on any node, so the contract check is skipped.

- [ ] **Step 9: Commit**

```bash
git add src/elspeth/contracts/schema.py src/elspeth/core/dag/graph.py src/elspeth/web/composer/state.py tests/unit/web/composer/test_state.py
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

    def test_aggregation_consumer_required_input_fields_fail(self) -> None:
        """Test 14e: Aggregation consumers honor required_input_fields contracts."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="agg1",
            options={"schema": {"mode": "fixed", "fields": ["line: str"]}},
        ))
        state = state.with_node(NodeSpec(
            id="agg1",
            node_type="aggregation",
            plugin="batch_stats",
            input="agg1",
            on_success="main",
            on_error=None,
            options={
                "value_field": "value",
                "required_input_fields": ["value"],
                "schema": {"mode": "observed"},
            },
            condition=None,
            routes=None,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "agg1"))
        result = state.validate()
        assert not result.is_valid
        assert any("value" in e.message for e in result.errors)

    def test_coalesce_producer_emits_skip_warning(self) -> None:
        """Test 14f: Coalesce producer emits a warning and skips fake contract checks."""
        state = self._empty_state()
        state = state.with_source(self._make_source(
            on_success="branch_a",
            options={"schema": {"mode": "fixed", "fields": ["text: str"]}},
        ))
        state = state.with_node(self._make_coalesce(
            "c1",
            "branch_a",
            "after_merge",
        ))
        state = state.with_node(self._make_transform(
            "t1", "after_merge", "main",
            options={"required_input_fields": ["text"]},
        ))
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "c1"))
        state = state.with_edge(self._make_edge("e2", "c1", "t1"))
        result = state.validate()
        assert result.is_valid, result.errors
        assert any(
            "coalesce node" in w.message.lower() and "runtime validator will check" in w.message.lower()
            for w in result.warnings
        )
        assert not any(ec.to_id == "t1" for ec in result.edge_contracts)

    # --- Guard tests ---

    def test_node_id_source_is_reserved(self) -> None:
        """Test 14g: A node with id='source' triggers an error and aborts the pass.

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
        """Test 14h: required_input_fields as a bare string emits a validation error.

        If required_input_fields is 'text' instead of ['text'], frozenset('text')
        would produce {'t', 'e', 'x'} — a silent, hard-to-debug bug. The guard
        in the shared raw-config consumer helper detects bare strings and emits a ValidationEntry
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

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_state.py::TestSchemaContractValidation -v -k "gate or route_gate or multi_hop or multi_sink or mixed_consumer or aggregation or coalesce or reserved or bare_string"`
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

This pass intentionally exposes the raw contract evidence, not redundant convenience booleans. Do not add `contracts_all_satisfied` to the preview response here; clients can derive it from `edge_contracts`. Likewise, do not add `has_unverified_edges` to `ValidationSummary` in this pass; skipped checks remain represented by warnings plus the absence of a matching `EdgeContract`.

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

**Prerequisite note:** This task is the runtime backing for the observed-text special case. If tasks are committed separately, do not enable the observed-text-positive tests from Task 2, Task 8, or Task 9 until this task lands.

- [ ] **Step 1: Add enforcement comment**

In `src/elspeth/plugins/sources/text_source.py`, at line 109 (the `yield from self._validate_and_yield({self._column: value}, ctx)` line), add a comment:

```python
                    # Shared composer/runtime contract helper depends on this:
                    # elspeth.contracts.schema.get_raw_producer_guaranteed_fields()
                    # infers {self._column} for observed text sources only.
                    # If you change which key the row uses, update that helper
                    # and its agreement tests.
                    yield from self._validate_and_yield(
                        {self._column: value},
                        ctx,
                    )
```

- [ ] **Step 2: Auto-declare `guaranteed_fields` in `__init__`**

In `TextSource.__init__()`, after `self._schema_config = cfg.schema_config` (line 72), add logic to auto-declare the column as a guaranteed field only when the schema is `observed` and does not already declare `guaranteed_fields`. This makes the narrow shared observed-text rule mechanical in runtime code without changing the semantics of `fixed`/`flexible` schemas. Use the normalized `SchemaConfig.to_dict()` round-trip that already exists; do not add a new `raw_schema_dict` field to config models.

```python
        self._schema_config = cfg.schema_config

        # Auto-declare {column} as a guaranteed output field only for the
        # shared observed-text contract case: observed schema, no explicit
        # guaranteed_fields, non-empty column. TextSource always produces
        # {column: value} for every row, so this is a provable invariant.
        # Keep this narrow: fixed/flexible schemas already express their
        # guarantees through normal SchemaConfig semantics and must not be
        # rewritten into an explicit guaranteed_fields declaration.
        if (
            self._schema_config is not None
            and self._schema_config.mode == "observed"
            and not self._schema_config.declares_guaranteed_fields
            and self._column
        ):
            # Rebuild schema config with guaranteed_fields including the column.
            # Use SchemaConfig.to_dict() on the validated, normalized config
            # rather than reaching back to raw YAML input.
            schema_dict = self._schema_config.to_dict()
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
the shared contract helper, so both validators produce the same answer.
This encodes the shared observed-text contract mechanically without relaxing
general schema validation."
```

---

### Task 7: Observed-Text Enforcement Test

**Files:**
- Create: `tests/unit/web/composer/test_schema_contract_enforcement.py`

- [ ] **Step 1: Write the enforcement test**

```python
"""Enforcement test tying the shared observed-text contract rule to the plugin.

The shared contract helpers in elspeth.contracts.schema infer that an observed
text source with column='X' guarantees field 'X'. TextSource.__init__
auto-declares {column} as a guaranteed field for that same narrow case.
This test verifies both sides agree: the plugin produces the key and declares
it as guaranteed for observed schemas only. If either side changes, this test
fails.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from elspeth.contracts.contexts import SourceContext
from elspeth.plugins.sources.text_source import TextSource


class TestTextSourceHeuristicEnforcement:
    def test_text_source_produces_configured_column_key(self) -> None:
        """Test 20a: Text source output key matches the shared contract rule.

        The shared raw-config helper infers that a text source with
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
                f"The shared contract helper in elspeth.contracts.schema depends on this."
            )
            assert first_row["text"] == "hello"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_text_source_auto_declares_guaranteed_fields(self) -> None:
        """Test 20b: TextSource auto-declares {column} for observed schemas only.

        The runtime reads SchemaConfig from the plugin. TextSource.__init__
        must auto-populate guaranteed_fields for the observed-text special case
        so runtime and composer agree. Without this, the shared helper would say
        "valid" while runtime rejects.

        White-box note: this test intentionally inspects source._schema_config.
        There is no public accessor for the plugin's normalized SchemaConfig, and
        the behavior under test lives in __init__ before row loading begins.
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

            # Intentional white-box assertion against the normalized internal config.
            # This test is pinning constructor-time contract state, not public row output.
            guaranteed = source._schema_config.get_effective_guaranteed_fields()
            assert "text" in guaranteed, (
                f"TextSource with column='text' must auto-declare 'text' as a "
                f"guaranteed field in its schema config. Got: {guaranteed}. "
                f"Without this, runtime rejects pipelines the composer approves."
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_text_source_preserves_explicit_guaranteed_fields(self) -> None:
        """Test 20c: TextSource does not override explicit guaranteed_fields.

        White-box by design for the same reason as test 20b: the contract state
        is normalized in __init__ and has no public accessor.
        """
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

    def test_text_source_observed_only_auto_declare_does_not_touch_fixed_schema(self) -> None:
        """Test 20d: Fixed schemas are not rewritten into explicit guarantees.

        White-box by design for the same reason as test 20b.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            config: dict[str, Any] = {
                "path": tmp_path,
                "column": "text",
                "schema": {"mode": "fixed", "fields": ["text: str"]},
            }
            source = TextSource(config)

            assert source._schema_config.declares_guaranteed_fields is False, (
                "Observed-text auto-declare must not rewrite fixed schema semantics"
            )
            assert "text" in source._schema_config.get_effective_guaranteed_fields()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_schema_contract_enforcement.py -v`
Expected: PASS — TextSource now auto-declares observed-text guarantees and leaves fixed schemas untouched

- [ ] **Step 3: Commit**

```bash
git add tests/unit/web/composer/test_schema_contract_enforcement.py
git commit -m "test(composer): add enforcement tests tying observed-text contract to text_source behavior"
```

---

### Task 8: Composer/Runtime Agreement Test

**Files:**
- Create: `tests/integration/web/test_composer_runtime_agreement.py`

- [ ] **Step 1: Write the agreement test**

This test builds the same pipeline configuration, validates it through both the composer and the runtime DAG validator, and asserts they agree on the shared-contract cases covered here. It is not a proof that composer and runtime are globally identical. If the composer later adds intentionally stricter preflight checks that runtime does not mirror, document those in separate asymmetry tests rather than forcing them into this agreement suite. Cover the node-consumer failure case, the observed-text acceptance case, the strict-sink parity case that motivated the shared helper extraction, and an aggregation-consumer failure case that proves the runtime's nested `config["options"]["required_input_fields"]` path stays coupled to the composer's flat `node.options` view.

```python
"""Composer/runtime agreement test.

Verifies that the composer's schema contract validation and the runtime
DAG validator agree on pass/fail for the same pipeline configuration in the
shared-contract cases covered here. This suite does not claim global
equivalence; intentionally stricter composer-only checks should live in
separate tests with explicit documentation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.core.config import (
    AggregationSettings,
    ElspethSettings,
    SinkSettings,
    SourceSettings,
    TransformSettings,
    TriggerConfig,
)
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
        sink_options: dict[str, Any],
        transform_options: dict[str, Any] | None = None,
        transform_plugin: str | None = "value_transform",
        aggregation_options: dict[str, Any] | None = None,
        aggregation_plugin: str | None = None,
    ) -> ExecutionGraph:
        """Build a runtime ExecutionGraph using the correct API.

        Uses ElspethSettings -> instantiate_plugins_from_config -> from_plugin_instances,
        matching the pattern in existing integration tests.
        """
        source_on_success = "agg1" if aggregation_plugin is not None else ("t1" if transform_plugin is not None else "main")
        transforms: list[TransformSettings] = []
        aggregations: list[AggregationSettings] = []
        if transform_plugin is not None:
            transforms.append(
                TransformSettings(
                    name="t1",
                    plugin=transform_plugin,
                    input="t1",
                    on_success="main",
                    on_error="discard",
                    options=transform_options or {},
                ),
            )
        if aggregation_plugin is not None:
            aggregations.append(
                AggregationSettings(
                    name="agg1",
                    plugin=aggregation_plugin,
                    input="agg1",
                    on_success="main",
                    on_error="discard",
                    trigger=TriggerConfig(count=1),
                    options=aggregation_options or {},
                ),
            )

        config = ElspethSettings(
            source=SourceSettings(
                plugin=source_plugin,
                on_success=source_on_success,
                options={**source_options, "on_validation_failure": "discard"},
            ),
            transforms=transforms,
            aggregations=aggregations,
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

            # Composer should reject — the observed-text special case can only
            # guarantee the configured column. Here the source column is
            # 'line', so downstream requirement 'text' is still unsatisfied.
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

        This is the critical agreement case that validates the shared
        observed-text rule. The shared helper infers {column} as guaranteed
        for observed text sources. TextSource.__init__ auto-declares
        {column} as guaranteed_fields in its schema config. Both validators call
        SchemaConfig.get_effective_guaranteed_fields() and get the same answer.

        If either the shared helper or the TextSource auto-declaration is
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

            # Composer should accept — the shared helper infers {column}
            composer_result = state.validate()
            assert composer_result.is_valid, (
                "Composer should accept: observed text rule infers 'text' from column"
            )

            # Runtime should also accept — TextSource auto-declares observed-text guarantees
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

    def test_both_reject_strict_sink_typed_requirement_without_upstream_guarantee(self) -> None:
        """Both validators reject: strict sink requirement from typed sink schema."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            tmp_path = f.name

        try:
            state = self._empty_state()
            state = state.with_source(SourceSpec(
                plugin="text",
                on_success="main",
                options={
                    "path": tmp_path,
                    "column": "line",
                    "schema": {"mode": "observed"},
                },
                on_validation_failure="quarantine",
            ))
            state = state.with_output(OutputSpec(
                name="main",
                plugin="csv",
                options={
                    "path": "outputs/out.csv",
                    "schema": {"mode": "fixed", "fields": ["text: str"]},
                },
                on_write_failure="discard",
            ))

            composer_result = state.validate()
            assert not composer_result.is_valid, (
                "Composer should reject: sink fixed schema requires 'text' "
                "but upstream only guarantees 'line'"
            )
            assert any(
                ec.to_id == "output:main" and not ec.satisfied
                for ec in composer_result.edge_contracts
            )

            try:
                graph = self._build_runtime_graph(
                    source_plugin="text",
                    source_options={"path": tmp_path, "column": "line", "schema": {"mode": "observed"}},
                    sink_options={"path": "outputs/out.csv", "schema": {"mode": "fixed", "fields": ["text: str"]}},
                    transform_plugin=None,
                )
                graph.validate_edge_compatibility()
                pytest.fail(
                    "Runtime should have rejected: sink typed schema requires 'text' "
                    "but upstream guarantees only 'line'"
                )
            except GraphValidationError as exc:
                assert "sink" in str(exc).lower() or "requires" in str(exc).lower(), (
                    f"Runtime rejected but for unexpected reason: {exc}"
                )

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_both_reject_aggregation_nested_required_input_fields_without_upstream_guarantee(self) -> None:
        """Both validators reject: aggregation contract comes from nested runtime options."""
        state = self._empty_state()
        state = state.with_source(SourceSpec(
            plugin="csv",
            on_success="agg1",
            options={
                "path": "inputs/in.csv",
                "schema": {"mode": "fixed", "fields": ["line: str"]},
            },
            on_validation_failure="quarantine",
        ))
        state = state.with_node(NodeSpec(
            id="agg1",
            node_type="aggregation",
            plugin="batch_stats",
            input="agg1",
            on_success="main",
            on_error=None,
            options={
                "value_field": "value",
                "required_input_fields": ["value"],
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
            id="e1", from_node="source", to_node="agg1",
            edge_type="on_success", label=None,
        ))

        composer_result = state.validate()
        assert not composer_result.is_valid
        assert any("value" in e.message.lower() for e in composer_result.errors)

        try:
            graph = self._build_runtime_graph(
                source_plugin="csv",
                source_options={"path": "inputs/in.csv", "schema": {"mode": "fixed", "fields": ["line: str"]}},
                sink_options={"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                transform_plugin=None,
                aggregation_plugin="batch_stats",
                aggregation_options={
                    "value_field": "value",
                    "required_input_fields": ["value"],
                    "schema": {"mode": "observed"},
                },
            )
            graph.validate_edge_compatibility()
            pytest.fail("Runtime should reject: aggregation requires 'value' but source guarantees only 'line'")
        except GraphValidationError as exc:
            assert "value" in str(exc).lower() or "required" in str(exc).lower(), (
                f"Runtime rejected but for unexpected reason: {exc}"
            )
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

### Task 9: Regression Test for the Reported Text-Source Scenario

**Files:**
- Test: `tests/unit/web/composer/test_state.py`

- [ ] **Step 1: Write regression test**

Append to `TestSchemaContractValidation`:

```python
    # --- Regression test ---

    def test_text_heuristic_rescues_original_bug_scenario(self) -> None:
        """Test 18: The reported text-source scenario now passes via the shared rule.

        text source (column=text, observed schema) + value_transform
        (required_input_fields=["text"]) + csv output.

        The original bug family: composer had NO contract checking at all, so it
        reported is_valid=True for any pipeline regardless of field contracts.
        The regression guard for that bug is test_observed_schema_no_guarantees_fails
        (test 6), which uses a non-text source with no observed-text exception.

        This test confirms the narrow observed-text rule correctly infers
        'text' from column='text', so the reported scenario is now valid
        (correctly). The runtime agrees because TextSource auto-declares
        {column} as guaranteed in its schema config (Task 6b).
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
        # With the shared observed-text rule, this now passes (correctly)
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
4. **All edge contracts are satisfied** — every downstream step's `required_input_fields` must be guaranteed by its upstream producer, and sink schemas may impose their own required fields. Check `edge_contracts` in the preview response. If any edge shows `"satisfied": false`, the pipeline is not complete. If `edge_contracts` is empty (`[]`), this means no field contracts were declared by any node — it does **not** mean all contracts are satisfied. If preview warnings say a contract check was skipped (for example because the producer is a coalesce node), treat that as unresolved rather than satisfied and surface the warning to the user. Pipelines without `required_input_fields` declarations are not verified by the composer's contract check; the runtime validator is the final authority.
```

- [ ] **Step 2: Add text source contract rule**

After line 356 (`- When wiring a text file via \`set_source_from_blob\`, you MUST pass...`), add:

```markdown
- **Schema rule for text sources:** Prefer an explicit `fixed` or `flexible` schema when you know the text column shape; it gives the strongest contract and clearer types. Narrow exception: a `text` source with `{"schema": {"mode": "observed"}}` and a non-empty `column` is still treated as guaranteeing `{column}` by the shared composer/runtime contract helper when `guaranteed_fields` is not explicitly set. Do not generalize this exception to other observed sources.
```

- [ ] **Step 2b: Add forward-reference in schema mode section**

In the "Choosing the right mode" bullet list (around line 143), after the `- **Sources:** Match the mode to how well you know the input data...` bullet, add:

```markdown
  **Default:** If downstream steps declare `required_input_fields` or reference fields by name, prefer `fixed` or `flexible` so the contract is explicit. `text` is the only observed-source exception, and only for its configured `column`; see the text source contract rule in "Plugin Quick Reference > Sources > text" below.
```

- [ ] **Step 3: Add fix flow example**

After the "Tool Failure Recovery" section (after line 127), add a new subsection:

```markdown
#### Fixing Schema Contract Violations

When `preview_pipeline` returns an unsatisfied edge contract, follow this sequence:

1. **Read the violation** — identify which edge failed, what fields are missing, and which node is the producer.
2. **Patch the producer contract** — usually by fixing the actual producer shape first, then making the schema explicit. For most sources this means `patch_source_options` to change from `observed` to `fixed`/`flexible` with the required fields declared:
   ```json
   patch_source_options({
     "patch": {"schema": {"mode": "fixed", "fields": ["text: str"]}}
   })
   ```
3. **Re-preview** — call `preview_pipeline` and verify the edge now shows `"satisfied": true`.
4. **Only then report success.**

**Example — csv source + value_transform:**
- `preview_pipeline` returns: `edge_contracts: [{"from": "source", "to": "add_world", "satisfied": false, "consumer_requires": ["text"], "producer_guarantees": []}]`
- Fix: `patch_source_options({"patch": {"schema": {"mode": "fixed", "fields": ["text: str"]}}})`
- Re-preview confirms: `"satisfied": true`

**Text-source note:** if the source plugin is `text` and the consumer requires the configured `column`, observed mode is already valid via the shared observed-text rule. If the required field and `column` do not match, fix the `column` or downstream field reference; do not invent a `fixed` schema that claims a different key than the plugin actually emits.

If `get_pipeline_state` and `preview_pipeline` disagree (e.g., state shows a field but preview shows an unsatisfied contract), treat this as unresolved. Do not report success. Re-run both tools, fix the discrepancy, and confirm before responding.

#### Known Limitation: Intermediate Transforms Break the Guarantee Chain

Transforms without explicit schema declarations report zero guaranteed fields to downstream consumers — even schema-preserving transforms like `passthrough`. If a transform sits between a source and a consumer with `required_input_fields`, the contract check will report a violation even though the data flows through unchanged.

**Fix:** Either add a `schema` to the intermediate transform declaring the fields it passes through, or move `required_input_fields` to the first transform in the chain (directly downstream of the source). The source→first-consumer edge is where contract checking is most reliable.

#### Non-Converging Contract Violations

If `preview_pipeline` still shows `"satisfied": false` after patching the producer schema, **stop patching and explain the limitation to the user.** The most common cause is an intermediate transform that does not propagate schema guarantees (see above). Do not repeatedly call `patch_source_options` or `patch_node_options` trying different schema configurations — if one patch didn't resolve it, the issue is structural, not a missing field declaration. Ask the user whether to:
1. Add an explicit `schema` declaration on the intermediate transform, or
2. Accept that this contract cannot be verified at composition time (the runtime validator will still check it).

If the same producer feeds multiple consumers with conflicting truthful requirements, do not loop trying to force one schema to satisfy all of them. Surface the conflict explicitly and ask whether to:
1. Split the path so each consumer gets its own producer contract,
2. Insert an intermediate transform or aggregation with an explicit schema on one branch, or
3. Relax or correct one of the downstream requirements if it was overstated.
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

Run: `.venv/bin/python -m mypy src/elspeth/contracts/schema.py src/elspeth/core/dag/graph.py src/elspeth/plugins/sources/text_source.py src/elspeth/web/composer/state.py src/elspeth/web/composer/tools.py`
Expected: No errors

- [ ] **Step 4: Run linter**

Run: `.venv/bin/python -m ruff check src/elspeth/contracts/schema.py src/elspeth/core/dag/graph.py src/elspeth/plugins/sources/text_source.py src/elspeth/web/composer/state.py src/elspeth/web/composer/tools.py`
Expected: No errors

- [ ] **Step 5: Run tier model enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: No new violations (the deferred import of the shared raw-config contract helpers from L0 into L3 is layer-legal)

- [ ] **Step 6: Register follow-up issue for expanded agreement tests**

The composer/runtime agreement test (Task 8) covers four scenarios: reject (wrong field), accept (observed text source special-case), reject (strict sink typed-schema requirement), and reject (aggregation consumer requirement coming from the runtime's nested `options` shape). It still does NOT cover coalesce-merge topologies or type-level schema compatibility — cases where the runtime validator checks properties the composer does not. These remaining gaps are expected (documented in the spec's "What This Doesn't Catch" table) but should be tracked for future expansion.

Create a Filigree issue:
```bash
filigree create "Expand composer/runtime agreement tests — coalesce and type-level" \
  --type=task --priority=3 \
  --description="The agreement test in tests/integration/web/test_composer_runtime_agreement.py covers four basic scenarios (node reject, observed-text accept, strict-sink reject, aggregation nested-options reject). Expand it to cover the remaining runtime-only gaps: (1) coalesce-merge branch intersection, (2) type-level schema compatibility (Pydantic schema construction). These are cases where runtime may reject but the composer currently cannot check. See docs/superpowers/specs/2026-04-14-composer-schema-contract-validation-design.md 'What This Doesn't Catch' table."
```
