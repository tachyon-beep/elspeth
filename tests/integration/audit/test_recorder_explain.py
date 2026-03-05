"""Tests for LandscapeRecorder explain functionality and graceful degradation."""

from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.contracts import NodeType
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.contracts.schema import SchemaConfig

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


class TestExplainGracefulDegradation:
    """Tests for explain_row() when payloads are unavailable."""

    def test_explain_with_missing_row_payload(self, tmp_path: Path, payload_store) -> None:
        """explain_row() succeeds even when row payload is purged."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.payload_store import FilesystemPayloadStore

        # Set up with payload store
        db = LandscapeDB.in_memory()
        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        recorder = LandscapeRecorder(db, payload_store=payload_store)

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # create_row auto-stores payload via configured payload_store
        row_data = {"name": "test", "value": 42}

        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data=row_data,
        )

        # Purge the payload (simulate retention policy)
        payload_store.delete(row.source_data_ref)

        # explain_row should still work
        lineage = recorder.explain_row(
            run_id=run.run_id,
            row_id=row.row_id,
        )

        assert lineage is not None
        assert lineage.source_data_hash is not None  # Hash preserved
        assert lineage.source_data is None  # Payload unavailable
        assert lineage.payload_available is False

    def test_explain_reports_payload_status(self, tmp_path: Path, payload_store) -> None:
        """explain_row() explicitly reports payload availability."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.payload_store import FilesystemPayloadStore

        # Set up with payload store
        db = LandscapeDB.in_memory()
        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        recorder = LandscapeRecorder(db, payload_store=payload_store)

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # create_row auto-stores payload via configured payload_store
        row_data = {"name": "test"}

        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data=row_data,
        )

        # Purge the payload
        payload_store.delete(row.source_data_ref)

        # Check payload_available attribute
        lineage = recorder.explain_row(
            run_id=run.run_id,
            row_id=row.row_id,
        )

        assert lineage is not None
        assert lineage.payload_available is False

    def test_explain_with_available_payload(self, tmp_path: Path, payload_store) -> None:
        """explain_row() returns payload when available."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.payload_store import FilesystemPayloadStore

        # Set up with payload store
        db = LandscapeDB.in_memory()
        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        recorder = LandscapeRecorder(db, payload_store=payload_store)

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # create_row auto-stores payload via configured payload_store
        row_data = {"name": "test", "value": 123}

        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data=row_data,
        )

        # Payload NOT purged
        lineage = recorder.explain_row(
            run_id=run.run_id,
            row_id=row.row_id,
        )

        assert lineage is not None
        assert lineage.source_data is not None  # Payload available
        assert lineage.source_data == row_data
        assert lineage.payload_available is True

    def test_explain_row_not_found(self) -> None:
        """explain_row() returns None when row doesn't exist."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="v1")

        lineage = recorder.explain_row(
            run_id=run.run_id,
            row_id="nonexistent",
        )

        assert lineage is None

    def test_explain_row_without_payload_store(self) -> None:
        """explain_row() works when no payload store is configured."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)  # No payload store

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data={"name": "test"},
        )

        lineage = recorder.explain_row(
            run_id=run.run_id,
            row_id=row.row_id,
        )

        assert lineage is not None
        assert lineage.source_data_hash is not None
        assert lineage.source_data is None  # No payload store
        assert lineage.payload_available is False

    def test_explain_row_with_no_payload_ref(self, tmp_path: Path) -> None:
        """explain_row() handles rows when no payload_store is configured.

        When LandscapeRecorder is created without a payload_store, rows are
        created without payload storage (payload_ref is None).
        """
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        # No payload_store configured - payloads won't be stored
        recorder = LandscapeRecorder(db, payload_store=None)

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Create row — no payload_store configured, so source_data_ref will be None
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data={"name": "test"},
        )

        lineage = recorder.explain_row(
            run_id=run.run_id,
            row_id=row.row_id,
        )

        assert lineage is not None
        assert lineage.source_data_hash is not None
        assert lineage.source_data is None  # No payload store configured
        assert lineage.payload_available is False

    def test_explain_row_with_corrupted_payload(self, tmp_path: Path, payload_store) -> None:
        """explain_row() crashes on corrupted payload — Tier 1 integrity violation."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.payload_store import FilesystemPayloadStore

        db = LandscapeDB.in_memory()
        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        recorder = LandscapeRecorder(db, payload_store=payload_store)

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # create_row auto-stores valid canonical JSON via payload_store
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data={"name": "test"},
        )

        # Store corrupted (non-JSON) data separately with a valid hash
        bad_ref = payload_store.store(b"this is not valid json {{{{")

        # Point the row's source_data_ref to the corrupted payload
        from elspeth.core.landscape.schema import rows_table

        with db.engine.connect() as conn:
            conn.execute(rows_table.update().where(rows_table.c.row_id == row.row_id).values(source_data_ref=bad_ref))
            conn.commit()

        # Tier 1 violation: corrupted payload store data is OUR data — must crash
        with pytest.raises(AuditIntegrityError, match="Corrupt payload"):
            recorder.explain_row(
                run_id=run.run_id,
                row_id=row.row_id,
            )

    def test_explain_row_with_non_object_payload(self, tmp_path: Path, payload_store) -> None:
        """explain_row() rejects non-object JSON payloads as corruption."""
        import json

        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.payload_store import FilesystemPayloadStore

        db = LandscapeDB.in_memory()
        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        recorder = LandscapeRecorder(db, payload_store=payload_store)

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # create_row auto-stores valid canonical JSON via payload_store
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data={"name": "test"},
        )

        # Store non-object JSON separately with a valid hash
        bad_ref = payload_store.store(json.dumps([1, 2, 3]).encode())

        # Point the row's source_data_ref to the non-object payload
        from elspeth.core.landscape.schema import rows_table

        with db.engine.connect() as conn:
            conn.execute(rows_table.update().where(rows_table.c.row_id == row.row_id).values(source_data_ref=bad_ref))
            conn.commit()

        with pytest.raises(AuditIntegrityError, match="expected JSON object"):
            recorder.explain_row(
                run_id=run.run_id,
                row_id=row.row_id,
            )

    def test_explain_row_rejects_run_id_mismatch(self, tmp_path: Path, payload_store) -> None:
        """explain_row() raises ValueError when row belongs to different run."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.payload_store import FilesystemPayloadStore

        db = LandscapeDB.in_memory()
        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        recorder = LandscapeRecorder(db, payload_store=payload_store)

        # Create two runs
        run1 = recorder.begin_run(config={}, canonical_version="v1")
        run2 = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run1.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Create row in run1 (create_row auto-stores payload)
        row_data = {"name": "test"}
        row = recorder.create_row(
            run_id=run1.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data=row_data,
        )

        # Try to explain using run2's ID — cross-run mismatch raises AuditIntegrityError
        with pytest.raises(AuditIntegrityError, match=f"Row {row.row_id} belongs to run {run1.run_id}, not {run2.run_id}"):
            recorder.explain_row(
                run_id=run2.run_id,  # Wrong run!
                row_id=row.row_id,
            )

        # Same row with correct run_id should work
        lineage_correct = recorder.explain_row(
            run_id=run1.run_id,
            row_id=row.row_id,
        )

        assert lineage_correct is not None
        assert lineage_correct.row_id == row.row_id
