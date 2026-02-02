# tests/engine/test_orchestrator_contracts.py
"""Tests for orchestrator schema contract recording.

Verifies that the orchestrator:
1. Records source contracts to the run after first-row inference
2. Passes output contracts to register_node for source nodes
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from elspeth.contracts import (
    SourceRow,
)
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from tests.conftest import (
    _TestSchema,
    _TestSinkBase,
    _TestSourceBase,
    as_sink,
    as_source,
)
from tests.engine.orchestrator_test_helpers import build_production_graph

if TYPE_CHECKING:
    from elspeth.contracts import ArtifactDescriptor


class TestOrchestratorContractRecording:
    """Test orchestrator records schema contracts to audit trail."""

    def test_source_contract_recorded_after_first_row(self, payload_store) -> None:
        """Orchestrator records source contract after first row is processed."""
        db = LandscapeDB.in_memory()

        # Create a test contract
        test_contract = SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract(
                    normalized_name="id",
                    original_name="ID",
                    python_type=int,
                    required=True,
                    source="inferred",
                ),
                FieldContract(
                    normalized_name="value",
                    original_name="Value",
                    python_type=str,
                    required=True,
                    source="inferred",
                ),
            ),
            locked=True,
        )

        class ContractSource(_TestSourceBase):
            """Source that provides a schema contract."""

            name = "contract_source"
            output_schema = _TestSchema

            def __init__(self, data: list[dict[str, Any]], contract: SchemaContract) -> None:
                super().__init__()
                self._data = data
                self._contract = contract

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                for row in self._data:
                    yield SourceRow.valid(row, contract=self._contract)

            def get_schema_contract(self) -> SchemaContract | None:
                return self._contract

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                super().__init__()
                self.results: list[dict[str, Any]] = []

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                from elspeth.contracts import ArtifactDescriptor

                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

        source = ContractSource(
            data=[{"id": 1, "value": "a"}, {"id": 2, "value": "b"}],
            contract=test_contract,
        )
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        result = orchestrator.run(config, graph=graph, payload_store=payload_store)

        assert result.rows_processed == 2

        # Verify contract was recorded in runs table
        from sqlalchemy import select

        from elspeth.core.landscape.schema import runs_table

        with db.engine.connect() as conn:
            run_row = conn.execute(select(runs_table).where(runs_table.c.run_id == result.run_id)).fetchone()

            assert run_row is not None
            assert run_row.schema_contract_json is not None

            # Parse and verify the contract
            import json

            contract_data = json.loads(run_row.schema_contract_json)
            assert contract_data["mode"] == "OBSERVED"
            assert contract_data["locked"] is True
            assert len(contract_data["fields"]) == 2

            # Verify field details
            fields_by_name = {f["normalized_name"]: f for f in contract_data["fields"]}
            assert fields_by_name["id"]["original_name"] == "ID"
            assert fields_by_name["id"]["python_type"] == "int"
            assert fields_by_name["value"]["original_name"] == "Value"
            assert fields_by_name["value"]["python_type"] == "str"

    def test_source_node_receives_output_contract(self, payload_store) -> None:
        """Source node registration includes output contract."""
        db = LandscapeDB.in_memory()

        test_contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract(
                    normalized_name="name",
                    original_name="Name",
                    python_type=str,
                    required=True,
                    source="declared",
                ),
            ),
            locked=True,
        )

        class ContractSource(_TestSourceBase):
            name = "contract_source"
            output_schema = _TestSchema

            def __init__(self, contract: SchemaContract) -> None:
                super().__init__()
                self._contract = contract

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield SourceRow.valid({"name": "test"}, contract=self._contract)

            def get_schema_contract(self) -> SchemaContract | None:
                return self._contract

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                super().__init__()
                self.results: list[dict[str, Any]] = []

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                from elspeth.contracts import ArtifactDescriptor

                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

        source = ContractSource(contract=test_contract)
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        result = orchestrator.run(config, graph=graph, payload_store=payload_store)

        assert result.rows_processed == 1

        # Verify source node has output_contract_json recorded
        from sqlalchemy import select

        from elspeth.core.landscape.schema import nodes_table

        with db.engine.connect() as conn:
            source_node = conn.execute(
                select(nodes_table).where((nodes_table.c.run_id == result.run_id) & (nodes_table.c.node_type == "source"))
            ).fetchone()

            assert source_node is not None
            assert source_node.output_contract_json is not None

            # Parse and verify the contract
            import json

            contract_data = json.loads(source_node.output_contract_json)
            assert contract_data["mode"] == "FIXED"
            assert contract_data["locked"] is True
            assert len(contract_data["fields"]) == 1
            assert contract_data["fields"][0]["normalized_name"] == "name"
            assert contract_data["fields"][0]["original_name"] == "Name"

    def test_no_contract_when_source_returns_none(self, payload_store) -> None:
        """Orchestrator handles sources that return None for get_schema_contract."""
        db = LandscapeDB.in_memory()

        class NoContractSource(_TestSourceBase):
            name = "no_contract_source"
            output_schema = _TestSchema

            def __init__(self) -> None:
                super().__init__()

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield SourceRow.valid({"x": 1})

            def get_schema_contract(self) -> SchemaContract | None:
                return None

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                super().__init__()
                self.results: list[dict[str, Any]] = []

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                from elspeth.contracts import ArtifactDescriptor

                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

        source = NoContractSource()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        result = orchestrator.run(config, graph=graph, payload_store=payload_store)

        assert result.rows_processed == 1

        # Verify no contract recorded when source returns None
        from sqlalchemy import select

        from elspeth.core.landscape.schema import runs_table

        with db.engine.connect() as conn:
            run_row = conn.execute(select(runs_table).where(runs_table.c.run_id == result.run_id)).fetchone()

            assert run_row is not None
            assert run_row.schema_contract_json is None

    def test_contract_recorded_with_empty_pipeline(self, payload_store) -> None:
        """Contract recording works with zero rows (empty source)."""
        db = LandscapeDB.in_memory()

        test_contract = SchemaContract(
            mode="OBSERVED",
            fields=(),
            locked=False,  # Not locked since no rows processed
        )

        class EmptyContractSource(_TestSourceBase):
            name = "empty_source"
            output_schema = _TestSchema

            def __init__(self, contract: SchemaContract) -> None:
                super().__init__()
                self._contract = contract

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                # Empty iterator - no rows
                return iter([])

            def get_schema_contract(self) -> SchemaContract | None:
                return self._contract

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                super().__init__()
                self.results: list[dict[str, Any]] = []

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                from elspeth.contracts import ArtifactDescriptor

                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

        source = EmptyContractSource(contract=test_contract)
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        result = orchestrator.run(config, graph=graph, payload_store=payload_store)

        assert result.rows_processed == 0

        # With no rows processed, contract should NOT be recorded (first-row inference didn't happen)
        from sqlalchemy import select

        from elspeth.core.landscape.schema import runs_table

        with db.engine.connect() as conn:
            run_row = conn.execute(select(runs_table).where(runs_table.c.run_id == result.run_id)).fetchone()

            assert run_row is not None
            # No contract recorded because first-row callback never fires
            assert run_row.schema_contract_json is None
