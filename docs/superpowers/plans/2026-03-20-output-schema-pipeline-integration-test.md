# Output Schema Contract — Full-Pipeline Integration Test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test output schema contract enforcement through the full `from_plugin_instances()` production path with real and mock transforms.

**Architecture:** One integration test file with 3 mock classes and 5 test methods. Group 1 uses a real `RAGRetrievalTransform` to prove end-to-end propagation. Group 2 uses configurable mock transforms to exercise edge validation happy path, missing field rejection, empty guarantees, and `FrameworkBugError` enforcement.

**Tech Stack:** pytest, `ExecutionGraph.from_plugin_instances()`, `WiredTransform`, `SchemaConfig`, `FrameworkBugError`.

**Spec:** `docs/superpowers/specs/2026-03-20-output-schema-pipeline-integration-test-design.md`

**Prerequisite:** The output schema contract enforcement plan (`docs/superpowers/plans/2026-03-20-output-schema-contract-enforcement.md`) must be implemented first. This test depends on `_validate_output_schema_contract` existing in the DAG builder and `_output_schema_config` being set on all field-adding transforms.

---

### Task 1: Create Directory Structure and Test File with Mocks

**Files:**
- Create: `tests/integration/core/__init__.py`
- Create: `tests/integration/core/dag/__init__.py`
- Create: `tests/integration/core/dag/test_output_schema_pipeline.py`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p tests/integration/core/dag
touch tests/integration/core/__init__.py
touch tests/integration/core/dag/__init__.py
```

- [ ] **Step 2: Write the test file with imports and mock classes**

Create `tests/integration/core/dag/test_output_schema_pipeline.py`:

```python
"""Integration test for output schema contract enforcement through from_plugin_instances().

Tests the full production path:
  real/mock transform constructor → _output_schema_config populated →
  from_plugin_instances() → DAG builder → NodeInfo propagation →
  validate_edge_compatibility() field resolution.

Group 1: Real RAGRetrievalTransform proves end-to-end contract propagation.
Group 2: Mock transforms exercise edge validation scenarios.

Prerequisite: Output schema contract enforcement (Tasks 1-3 from the
enforcement plan) must be implemented — _validate_output_schema_contract
must exist in the DAG builder.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from elspeth.contracts.errors import FrameworkBugError
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.config import SourceSettings, TransformSettings
from elspeth.core.dag import ExecutionGraph, GraphValidationError, WiredTransform
from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform


# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------


class MockSource:
    """Minimal source implementing enough of SourceProtocol for the builder."""

    name = "mock_source"
    output_schema = None
    config: ClassVar[dict[str, Any]] = {"schema": {"mode": "observed"}}
    _on_validation_failure = "discard"
    on_success = "output"


class MockSink:
    """Minimal sink implementing enough of SinkProtocol for the builder."""

    name = "mock_sink"
    input_schema = None
    config: ClassVar[dict[str, Any]] = {}


_SENTINEL = object()


class MockFieldAddingTransform:
    """Mock transform with configurable output fields and required inputs.

    The DAG builder reads _output_schema_config from the transform instance
    and populates NodeInfo. The graph's get_required_fields() reads
    required_input_fields from node_info.config as a TOP-LEVEL key
    (graph.py lines 1459-1463) — NOT nested under "options".
    """

    input_schema = None
    output_schema = None
    on_error: str | None = None
    on_success: str | None = "output"

    def __init__(
        self,
        name: str,
        *,
        guaranteed_fields: tuple[str, ...] = (),
        declared_output_fields: frozenset[str] = frozenset(),
        required_input_fields: list[str] | None = None,
        output_schema_config_override: Any = _SENTINEL,
    ) -> None:
        self.name = name
        self.declared_output_fields = declared_output_fields

        # Build _output_schema_config from guaranteed_fields unless explicitly
        # overridden. _SENTINEL distinguishes "not provided" from "explicitly
        # set to None" — tests 3 and 4 need _output_schema_config = None even
        # when declared_output_fields is non-empty.
        if output_schema_config_override is not _SENTINEL:
            self._output_schema_config = output_schema_config_override
        elif guaranteed_fields:
            self._output_schema_config = SchemaConfig(
                mode="observed",
                fields=None,
                guaranteed_fields=guaranteed_fields,
            )
        else:
            self._output_schema_config = None

        # config must have required_input_fields as a TOP-LEVEL key.
        self.config: dict[str, Any] = {"schema": {"mode": "observed"}}
        if required_input_fields is not None:
            self.config["required_input_fields"] = required_input_fields
```

- [ ] **Step 3: Verify the file imports cleanly**

Run: `.venv/bin/python -c "import tests.integration.core.dag.test_output_schema_pipeline"`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/core/__init__.py tests/integration/core/dag/__init__.py tests/integration/core/dag/test_output_schema_pipeline.py
git commit -m "test: add mock infrastructure for output schema pipeline integration test"
```

---

### Task 2: Group 1 — Real RAG Transform End-to-End Propagation Test

**Files:**
- Modify: `tests/integration/core/dag/test_output_schema_pipeline.py`

- [ ] **Step 1: Write the RAG propagation test**

Add to `tests/integration/core/dag/test_output_schema_pipeline.py`:

```python
# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_fingerprint_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ELSPETH_FINGERPRINT_KEY is set for transforms that may need it."""
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-key-for-pipeline-integration")


# ---------------------------------------------------------------------------
# Group 1: Real transform — contract propagation end-to-end
# ---------------------------------------------------------------------------


class TestRealTransformPropagation:
    """Prove the full chain with a real transform through from_plugin_instances()."""

    def test_rag_output_schema_propagates_through_pipeline(self) -> None:
        """RAG _output_schema_config flows through builder into NodeInfo.

        Full chain: real constructor → _build_output_schema_config() →
        builder reads _output_schema_config → NodeInfo stores it →
        get_effective_guaranteed_fields() resolves it.
        """
        rag = RAGRetrievalTransform(
            {
                "output_prefix": "sci",
                "query_field": "question",
                "provider": "chroma",
                "provider_config": {"collection": "test-col", "mode": "ephemeral"},
                "schema": {"mode": "observed"},
            }
        )

        source = MockSource()
        wired = WiredTransform(
            plugin=rag,  # type: ignore[arg-type]
            settings=TransformSettings(
                name="rag_0",
                plugin=rag.name,
                input="source_out",
                on_success="output",
                on_error="discard",
                options={},
            ),
        )

        graph = ExecutionGraph.from_plugin_instances(
            source=source,  # type: ignore[arg-type]
            source_settings=SourceSettings(
                plugin="mock_source", on_success="source_out", options={}
            ),
            transforms=[wired],
            sinks={"output": MockSink()},  # type: ignore[dict-item]
            aggregations={},
            gates=[],
        )

        # Find the RAG transform node
        rag_nodes = [
            n for n in graph.get_nodes() if n.plugin_name == "rag_retrieval"
        ]
        assert len(rag_nodes) == 1
        node_info = rag_nodes[0]

        # Verify _output_schema_config was propagated to NodeInfo
        assert node_info.output_schema_config is not None

        # Verify graph methods resolve the guaranteed fields
        guaranteed = graph.get_effective_guaranteed_fields(node_info.node_id)
        expected = frozenset(
            {"sci__rag_context", "sci__rag_score", "sci__rag_count", "sci__rag_sources"}
        )
        assert expected.issubset(guaranteed), (
            f"Expected {expected} to be a subset of {guaranteed}"
        )
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/integration/core/dag/test_output_schema_pipeline.py::TestRealTransformPropagation -v`
Expected: PASS — the RAG transform's `_output_schema_config` propagates through the builder.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/core/dag/test_output_schema_pipeline.py
git commit -m "test: add RAG end-to-end output schema propagation test through from_plugin_instances()"
```

---

### Task 3: Group 2 — Mock Transform Edge Validation Tests

**Files:**
- Modify: `tests/integration/core/dag/test_output_schema_pipeline.py`

- [ ] **Step 1: Add the helper function and happy-path test**

Add to `tests/integration/core/dag/test_output_schema_pipeline.py`:

```python
# ---------------------------------------------------------------------------
# Group 2: Mock transforms — edge validation scenarios
# ---------------------------------------------------------------------------


def _build_producer_consumer_graph(
    *,
    producer: MockFieldAddingTransform,
    consumer: MockFieldAddingTransform,
) -> ExecutionGraph:
    """Wire producer → consumer through from_plugin_instances().

    Raises GraphValidationError if edge validation fails (validate_edge_compatibility()
    is called automatically inside build_execution_graph() at builder.py line 923).
    Raises FrameworkBugError if a transform declares output fields without
    _output_schema_config (enforcement check runs during node addition, before edges).
    """
    source = MockSource()
    producer_wired = WiredTransform(
        plugin=producer,  # type: ignore[arg-type]
        settings=TransformSettings(
            name="producer_0",
            plugin=producer.name,
            input="source_out",
            on_success="consumer_in",
            on_error="discard",
            options={},
        ),
    )
    consumer_wired = WiredTransform(
        plugin=consumer,  # type: ignore[arg-type]
        settings=TransformSettings(
            name="consumer_0",
            plugin=consumer.name,
            input="consumer_in",
            on_success="output",
            on_error="discard",
            options={},
        ),
    )
    return ExecutionGraph.from_plugin_instances(
        source=source,  # type: ignore[arg-type]
        source_settings=SourceSettings(
            plugin="mock_source", on_success="source_out", options={}
        ),
        transforms=[producer_wired, consumer_wired],
        sinks={"output": MockSink()},  # type: ignore[dict-item]
        aggregations={},
        gates=[],
    )


class TestEdgeValidationWithOutputSchemaContract:
    """Exercise edge validation through from_plugin_instances() with mock transforms."""

    def test_edge_validation_passes_when_fields_satisfied(self) -> None:
        """Producer guarantees field_a and field_b, consumer requires field_a."""
        producer = MockFieldAddingTransform(
            "producer",
            guaranteed_fields=("field_a", "field_b"),
            declared_output_fields=frozenset({"field_a", "field_b"}),
        )
        consumer = MockFieldAddingTransform(
            "consumer",
            required_input_fields=["field_a"],
        )

        graph = _build_producer_consumer_graph(producer=producer, consumer=consumer)
        # If we get here, from_plugin_instances() succeeded — edge validation passed.
        assert graph is not None
```

- [ ] **Step 2: Run the happy-path test**

Run: `.venv/bin/python -m pytest tests/integration/core/dag/test_output_schema_pipeline.py::TestEdgeValidationWithOutputSchemaContract::test_edge_validation_passes_when_fields_satisfied -v`
Expected: PASS.

- [ ] **Step 3: Add the missing-fields rejection test**

Add to `TestEdgeValidationWithOutputSchemaContract`:

```python
    def test_edge_validation_rejects_missing_fields(self) -> None:
        """Producer guarantees field_a only, consumer requires field_a + nonexistent."""
        producer = MockFieldAddingTransform(
            "producer",
            guaranteed_fields=("field_a",),
            declared_output_fields=frozenset({"field_a"}),
        )
        consumer = MockFieldAddingTransform(
            "consumer",
            required_input_fields=["field_a", "nonexistent"],
        )

        with pytest.raises(GraphValidationError, match="Missing fields"):
            _build_producer_consumer_graph(producer=producer, consumer=consumer)
```

- [ ] **Step 4: Run the missing-fields test**

Run: `.venv/bin/python -m pytest tests/integration/core/dag/test_output_schema_pipeline.py::TestEdgeValidationWithOutputSchemaContract::test_edge_validation_rejects_missing_fields -v`
Expected: PASS — `from_plugin_instances()` raises `GraphValidationError`.

- [ ] **Step 5: Add the empty-guarantees rejection test**

Add to `TestEdgeValidationWithOutputSchemaContract`:

```python
    def test_edge_validation_rejects_empty_guarantees(self) -> None:
        """Producer guarantees nothing, consumer requires field_a."""
        producer = MockFieldAddingTransform(
            "producer",
            declared_output_fields=frozenset(),
            output_schema_config_override=None,
        )
        consumer = MockFieldAddingTransform(
            "consumer",
            required_input_fields=["field_a"],
        )

        with pytest.raises(GraphValidationError):
            _build_producer_consumer_graph(producer=producer, consumer=consumer)
```

- [ ] **Step 6: Run the empty-guarantees test**

Run: `.venv/bin/python -m pytest tests/integration/core/dag/test_output_schema_pipeline.py::TestEdgeValidationWithOutputSchemaContract::test_edge_validation_rejects_empty_guarantees -v`
Expected: PASS — `from_plugin_instances()` raises `GraphValidationError`.

- [ ] **Step 7: Commit Group 2 edge validation tests**

```bash
git add tests/integration/core/dag/test_output_schema_pipeline.py
git commit -m "test: add edge validation integration tests for output schema contracts"
```

---

### Task 4: Group 2 — Enforcement Check Through Production Path

**Files:**
- Modify: `tests/integration/core/dag/test_output_schema_pipeline.py`

- [ ] **Step 1: Add the enforcement test**

Add to `TestEdgeValidationWithOutputSchemaContract`:

```python
    def test_enforcement_fires_through_production_path(self) -> None:
        """Transform with declared_output_fields but no _output_schema_config crashes at build time.

        _validate_output_schema_contract runs during the transform-iteration loop
        (before edge validation). No consumer is needed — from_plugin_instances()
        raises FrameworkBugError before the graph is built.

        This test depends on the enforcement spec's Task 3 being implemented.
        """
        broken_transform = MockFieldAddingTransform(
            "broken",
            declared_output_fields=frozenset({"field_a"}),
            output_schema_config_override=None,
        )
        source = MockSource()
        wired = WiredTransform(
            plugin=broken_transform,  # type: ignore[arg-type]
            settings=TransformSettings(
                name="broken_0",
                plugin="broken",
                input="source_out",
                on_success="output",
                on_error="discard",
                options={},
            ),
        )

        with pytest.raises(FrameworkBugError, match="declares output fields"):
            ExecutionGraph.from_plugin_instances(
                source=source,  # type: ignore[arg-type]
                source_settings=SourceSettings(
                    plugin="mock_source", on_success="source_out", options={}
                ),
                transforms=[wired],
                sinks={"output": MockSink()},  # type: ignore[dict-item]
                aggregations={},
                gates=[],
            )
```

- [ ] **Step 2: Run the enforcement test**

Run: `.venv/bin/python -m pytest tests/integration/core/dag/test_output_schema_pipeline.py::TestEdgeValidationWithOutputSchemaContract::test_enforcement_fires_through_production_path -v`
Expected: PASS — `from_plugin_instances()` raises `FrameworkBugError` during the transform-iteration loop.

- [ ] **Step 3: Run the full test file**

Run: `.venv/bin/python -m pytest tests/integration/core/dag/test_output_schema_pipeline.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 4: Run ruff**

Run: `.venv/bin/python -m ruff check tests/integration/core/dag/test_output_schema_pipeline.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/integration/core/dag/test_output_schema_pipeline.py
git commit -m "test: add FrameworkBugError enforcement integration test through from_plugin_instances()"
```

---

### Task 5: Final Verification

- [ ] **Step 1: Run the full integration test suite for DAG-related tests**

```bash
.venv/bin/python -m pytest tests/integration/core/ tests/unit/core/test_dag_schema_propagation.py -v
```

Expected: All pass — no regressions in existing schema propagation tests, all 5 new tests pass.

- [ ] **Step 2: Run ruff and mypy on the new file**

```bash
.venv/bin/python -m ruff check tests/integration/core/dag/test_output_schema_pipeline.py
.venv/bin/python -m mypy tests/integration/core/dag/test_output_schema_pipeline.py
```

Expected: Both pass cleanly.

- [ ] **Step 3: Update spec status**

In `docs/superpowers/specs/2026-03-20-output-schema-pipeline-integration-test-design.md`, change `**Status:** Draft` to `**Status:** Implemented`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-03-20-output-schema-pipeline-integration-test-design.md
git commit -m "docs: mark output schema pipeline integration test spec as implemented"
```
