# tests/e2e/audit/test_export_reimport.py
"""E2E tests verifying export/reimport roundtrip for audit data.

The LandscapeExporter produces a flat sequence of records suitable for
compliance review. These tests verify the exported data is complete
and consistent with direct database queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from elspeth.contracts import RunStatus
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.exporter import LandscapeExporter
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.payload_store import FilesystemPayloadStore
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from tests.fixtures.base_classes import as_sink, as_source, as_transform
from tests.fixtures.pipeline import build_linear_pipeline
from tests.fixtures.plugins import CollectSink, PassTransform

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_pipeline(
    tmp_path: Path,
    source_data: list[dict[str, Any]],
    transforms: list[Any] | None = None,
) -> tuple[str, LandscapeDB, FilesystemPayloadStore, CollectSink]:
    """Run a linear pipeline and return (run_id, db, payload_store, sink)."""
    db = LandscapeDB(f"sqlite:///{tmp_path}/audit.db")
    payload_store = FilesystemPayloadStore(tmp_path / "payloads")

    tx = transforms if transforms is not None else [PassTransform()]
    source, tx_list, sinks, graph = build_linear_pipeline(source_data, transforms=tx)
    sink = sinks["default"]

    config = PipelineConfig(
        source=as_source(source),
        transforms=[as_transform(t) for t in tx_list],
        sinks={"default": as_sink(sink)},
    )

    orchestrator = Orchestrator(db)
    result = orchestrator.run(config, graph=graph, payload_store=payload_store)
    assert result.status == RunStatus.COMPLETED
    return result.run_id, db, payload_store, sink


# ---------------------------------------------------------------------------
# TestExportReimport
# ---------------------------------------------------------------------------


class TestExportReimport:
    """Verify export produces complete, consistent audit records."""

    def test_export_produces_all_record_types(self, tmp_path: Path) -> None:
        """Run a pipeline, export via LandscapeExporter.export_run(),
        verify records include run, node, edge, row, token types.
        """
        source_data = [
            {"id": "row_1", "value": 10},
            {"id": "row_2", "value": 20},
        ]
        run_id, db, _payload_store, _sink = _run_pipeline(tmp_path, source_data)

        exporter = LandscapeExporter(db)
        records = list(exporter.export_run(run_id))

        record_types = {r["record_type"] for r in records}

        # Core record types that must always be present
        assert "run" in record_types, "Missing 'run' record type"
        assert "node" in record_types, "Missing 'node' record type"
        assert "edge" in record_types, "Missing 'edge' record type"
        assert "row" in record_types, "Missing 'row' record type"
        assert "token" in record_types, "Missing 'token' record type"

        db.close()

    def test_export_grouped_separates_record_types(self, tmp_path: Path) -> None:
        """Use export_run_grouped() and verify each group has correct fields."""
        source_data = [{"id": "row_1", "value": 100}]
        run_id, db, _payload_store, _sink = _run_pipeline(tmp_path, source_data)

        exporter = LandscapeExporter(db)
        grouped = exporter.export_run_grouped(run_id)

        # Verify grouping structure
        assert isinstance(grouped, dict)
        assert "run" in grouped
        assert "node" in grouped
        assert "row" in grouped
        assert "token" in grouped

        # Verify run group has exactly 1 record with required fields
        run_records = grouped["run"]
        assert len(run_records) == 1
        run_record = run_records[0]
        assert run_record["run_id"] == run_id
        assert run_record["status"] == "completed"
        assert "started_at" in run_record
        assert "completed_at" in run_record

        # Verify node records have required fields
        for node_record in grouped["node"]:
            assert "node_id" in node_record
            assert "plugin_name" in node_record
            assert "node_type" in node_record
            assert node_record["run_id"] == run_id

        # Verify row records have required fields
        for row_record in grouped["row"]:
            assert "row_id" in row_record
            assert "row_index" in row_record
            assert "source_data_hash" in row_record
            assert row_record["run_id"] == run_id

        # Verify token records have required fields
        for token_record in grouped["token"]:
            assert "token_id" in token_record
            assert "row_id" in token_record
            assert token_record["run_id"] == run_id

        db.close()

    def test_export_data_matches_direct_queries(self, tmp_path: Path) -> None:
        """Export a run, compare record counts with direct SQL queries."""
        source_data = [{"id": f"row_{i}", "value": i * 10} for i in range(5)]
        run_id, db, _payload_store, _sink = _run_pipeline(tmp_path, source_data)

        # Get counts from direct recorder queries
        recorder = LandscapeRecorder(db)
        direct_rows = recorder.get_rows(run_id)
        direct_nodes = recorder.get_nodes(run_id)
        direct_edges = recorder.get_edges(run_id)
        direct_tokens = recorder.get_all_tokens_for_run(run_id)

        # Get counts from export
        exporter = LandscapeExporter(db)
        grouped = exporter.export_run_grouped(run_id)

        # Compare counts
        assert len(grouped.get("run", [])) == 1, "Should have exactly 1 run record"

        assert len(grouped.get("row", [])) == len(direct_rows), (
            f"Export row count ({len(grouped.get('row', []))}) != direct query count ({len(direct_rows)})"
        )

        assert len(grouped.get("node", [])) == len(direct_nodes), (
            f"Export node count ({len(grouped.get('node', []))}) != direct query count ({len(direct_nodes)})"
        )

        assert len(grouped.get("edge", [])) == len(direct_edges), (
            f"Export edge count ({len(grouped.get('edge', []))}) != direct query count ({len(direct_edges)})"
        )

        assert len(grouped.get("token", [])) == len(direct_tokens), (
            f"Export token count ({len(grouped.get('token', []))}) != direct query count ({len(direct_tokens)})"
        )

        # Verify run_id consistency across all exported records
        for record_type, records in grouped.items():
            for record in records:
                if "run_id" in record:
                    assert record["run_id"] == run_id, f"Record type '{record_type}' has wrong run_id: {record['run_id']}"

        db.close()
