# tests/engine/test_orchestrator_contracts.py
"""Tests for orchestrator schema contract recording.

Verifies that the orchestrator:
1. Records source contracts to the run after first-row inference
2. Passes output contracts to register_node for source nodes
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from elspeth.contracts import (
    PipelineRow,
    SourceRow,
)
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from tests.conftest import (
    _TestSchema,
    _TestSourceBase,
    _TestTransformBase,
    as_sink,
    as_source,
    as_transform,
)
from tests.engine.conftest import CollectSink
from tests.engine.orchestrator_test_helpers import build_production_graph


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
                yield from self.wrap_rows([{"x": 1}])

            def get_schema_contract(self) -> SchemaContract | None:
                return None

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

        # PIPELINEROW MIGRATION: Contract IS recorded even with no rows
        # Source contract is stored at run start (not after first row) to support resume/recovery
        from sqlalchemy import select

        from elspeth.core.landscape.schema import runs_table

        with db.engine.connect() as conn:
            run_row = conn.execute(select(runs_table).where(runs_table.c.run_id == result.run_id)).fetchone()

            assert run_row is not None
            # Contract recorded from source at run start, even with 0 rows processed
            assert run_row.schema_contract_json is not None
            # Empty source produces empty contract (no fields)
            import json

            contract_data = json.loads(run_row.schema_contract_json)
            assert contract_data["fields"] == []
            assert contract_data["mode"] == "OBSERVED"

    def test_contract_recorded_after_first_valid_row_not_first_iteration(self, payload_store) -> None:
        """Contract recorded after first VALID row, not first iteration.

        BUG FIX: mwwo - Run schema contract tied to first iteration, not first valid row

        If the first row is quarantined, the contract should still be recorded
        when a later valid row is processed. This tests the fix for the bug where
        the schema_contract_recorded flag was set on first iteration regardless
        of whether the row was valid.
        """
        db = LandscapeDB.in_memory()

        test_contract = SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract(
                    normalized_name="id",
                    original_name="id",
                    python_type=int,
                    required=True,
                    source="inferred",
                ),
            ),
            locked=True,
        )

        class QuarantineThenValidSource(_TestSourceBase):
            """Source that yields quarantined row first, then valid row."""

            name = "quarantine_first_source"
            output_schema = _TestSchema
            _on_validation_failure = "quarantine"

            def __init__(self, contract: SchemaContract) -> None:
                super().__init__()
                self._contract: SchemaContract | None = None
                self._expected_contract = contract

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                # First row: quarantined (contract not set yet)
                yield SourceRow.quarantined(
                    row={"id": "invalid"},  # String instead of int
                    error="type error",
                    destination="quarantine",
                )

                # Second row: valid (now set the contract)
                self._contract = self._expected_contract
                yield SourceRow.valid({"id": 1}, contract=self._contract)

            def get_schema_contract(self) -> SchemaContract | None:
                return self._contract

        source = QuarantineThenValidSource(contract=test_contract)
        sink = CollectSink()
        quarantine_sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink), "quarantine": as_sink(quarantine_sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        result = orchestrator.run(config, graph=graph, payload_store=payload_store)

        # Both rows should be processed
        assert result.rows_processed == 2
        # One quarantined, one succeeded
        assert result.rows_quarantined == 1
        assert result.rows_succeeded == 1

        # Verify contract WAS recorded (not skipped due to quarantined first row)
        from sqlalchemy import select

        from elspeth.core.landscape.schema import nodes_table, runs_table

        with db.engine.connect() as conn:
            run_row = conn.execute(select(runs_table).where(runs_table.c.run_id == result.run_id)).fetchone()

            assert run_row is not None
            # Contract should be recorded after the second (valid) row
            assert run_row.schema_contract_json is not None

            # Verify the contract content
            import json

            contract_data = json.loads(run_row.schema_contract_json)
            assert contract_data["mode"] == "OBSERVED"
            assert len(contract_data["fields"]) == 1
            assert contract_data["fields"][0]["normalized_name"] == "id"

            # Also verify source node has output_contract (c1v5 fix)
            source_node = conn.execute(
                select(nodes_table).where((nodes_table.c.run_id == result.run_id) & (nodes_table.c.node_type == "source"))
            ).fetchone()

            assert source_node is not None
            assert source_node.output_contract_json is not None

    def test_transform_schema_evolution_updates_contract(self, payload_store) -> None:
        """Transform adding fields during execution should have updated contract recorded.

        Edge case: When a transform adds fields to the pipeline, the orchestrator
        should record the evolved contract (input fields + added fields) to the
        nodes table as the transform's output_contract_json.

        This verifies that schema evolution is tracked in the audit trail.
        """
        from elspeth.contracts import TransformResult

        db = LandscapeDB.in_memory()

        # Source provides base fields
        test_contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract(
                    normalized_name="id",
                    original_name="ID",
                    python_type=int,
                    required=True,
                    source="declared",
                ),
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

        class BaseSource(_TestSourceBase):
            name = "base_source"
            output_schema = _TestSchema

            def __init__(self, contract: SchemaContract) -> None:
                super().__init__()
                self._contract = contract

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield SourceRow.valid({"id": 1, "name": "Alice"}, contract=self._contract)

            def get_schema_contract(self) -> SchemaContract | None:
                return self._contract

        class EnrichTransform(_TestTransformBase):
            """Transform that adds a 'score' field."""

            name = "enrich_transform"
            transforms_adds_fields = True  # Signal that this transform adds fields

            def process(self, row: Any, ctx: Any) -> TransformResult:
                # Add new field
                output = {**row.to_dict(), "score": 95.5}
                return TransformResult.success(
                    PipelineRow(output, row.contract),
                    success_reason={"action": "enriched"},
                )

        source = BaseSource(contract=test_contract)
        transform = EnrichTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        result = orchestrator.run(config, graph=graph, payload_store=payload_store)

        assert result.rows_processed == 1
        assert sink.results == [{"id": 1, "name": "Alice", "score": 95.5}]

        # Verify transform node has evolved output contract
        from sqlalchemy import select

        from elspeth.core.landscape.schema import nodes_table

        with db.engine.connect() as conn:
            transform_node = conn.execute(
                select(nodes_table).where((nodes_table.c.run_id == result.run_id) & (nodes_table.c.plugin_name == "enrich_transform"))
            ).fetchone()

            assert transform_node is not None
            assert transform_node.output_contract_json is not None

            # Parse and verify evolved contract
            import json

            contract_data = json.loads(transform_node.output_contract_json)
            assert len(contract_data["fields"]) == 3  # id, name, score

            # Verify all fields present
            field_names = {f["normalized_name"] for f in contract_data["fields"]}
            assert "id" in field_names
            assert "name" in field_names
            assert "score" in field_names  # New field added by transform

            # Verify new field details
            score_field = next(f for f in contract_data["fields"] if f["normalized_name"] == "score")
            assert score_field["python_type"] == "float"
            assert score_field["source"] == "inferred"
            assert score_field["required"] is False  # Inferred fields are not required


class TestOrchestratorSecretResolutions:
    """Test orchestrator records secret resolutions to audit trail."""

    def test_secret_resolutions_recorded_when_provided(self, payload_store, monkeypatch) -> None:
        """Orchestrator records secret resolutions when passed."""
        import time

        # Set up fingerprint key in environment
        monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-fingerprint-key")

        db = LandscapeDB.in_memory()

        # Simple source/sink
        class SimpleSource(_TestSourceBase):
            name = "simple_source"
            output_schema = _TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows([{"x": 1}])

        source = SimpleSource()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        # Create secret resolutions like load_secrets_from_config() now returns
        # (with pre-computed fingerprint, no plaintext value)
        from elspeth.core.security.fingerprint import secret_fingerprint

        timestamp = time.time()
        fp = secret_fingerprint("secret-value-xyz", key=b"test-fingerprint-key")
        secret_resolutions = [
            {
                "env_var_name": "TEST_API_KEY",
                "source": "keyvault",
                "vault_url": "https://testvault.vault.azure.net",
                "secret_name": "test-api-key",
                "timestamp": timestamp,
                "latency_ms": 100.0,
                "fingerprint": fp,
            }
        ]

        result = orchestrator.run(
            config,
            graph=graph,
            payload_store=payload_store,
            secret_resolutions=secret_resolutions,
        )

        assert result.rows_processed == 1

        # Verify secret resolution was recorded
        from sqlalchemy import select

        from elspeth.core.landscape.schema import secret_resolutions_table

        with db.engine.connect() as conn:
            resolution_row = conn.execute(
                select(secret_resolutions_table).where(secret_resolutions_table.c.run_id == result.run_id)
            ).fetchone()

            assert resolution_row is not None
            assert resolution_row.env_var_name == "TEST_API_KEY"
            assert resolution_row.source == "keyvault"
            assert resolution_row.vault_url == "https://testvault.vault.azure.net"
            assert resolution_row.secret_name == "test-api-key"
            assert resolution_row.resolution_latency_ms == 100.0

            # Verify pre-computed fingerprint was stored correctly
            assert resolution_row.fingerprint == fp

    def test_no_secret_resolutions_when_not_provided(self, payload_store) -> None:
        """Orchestrator works normally when secret_resolutions is None."""
        db = LandscapeDB.in_memory()

        class SimpleSource(_TestSourceBase):
            name = "simple_source"
            output_schema = _TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows([{"x": 1}])

        source = SimpleSource()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink)},
        )
        graph = build_production_graph(config, default_sink="default")
        orchestrator = Orchestrator(db)

        # No secret_resolutions provided
        result = orchestrator.run(
            config,
            graph=graph,
            payload_store=payload_store,
        )

        assert result.rows_processed == 1

        # Verify no secret resolutions were recorded
        from sqlalchemy import select

        from elspeth.core.landscape.schema import secret_resolutions_table

        with db.engine.connect() as conn:
            resolution_rows = conn.execute(
                select(secret_resolutions_table).where(secret_resolutions_table.c.run_id == result.run_id)
            ).fetchall()

            assert len(resolution_rows) == 0
