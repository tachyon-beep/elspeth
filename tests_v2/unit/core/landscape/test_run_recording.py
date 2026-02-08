"""Tests for RunRecordingMixin — run lifecycle recording.

Tests cover:
- begin_run (creates run, generates ID, stores config hash, settings JSON)
- complete_run (sets status and completed_at)
- get_run (retrieves run by ID, returns None for unknown)
- get_source_schema (retrieves/validates source schema JSON)
- record/get_source_field_resolution (roundtrip, Tier 1 validation)
- update_run_status (intermediate status changes)
- record/get_secret_resolutions (roundtrip)
- list_runs (with status filter)
- set_export_status (COMPLETED clears error, PENDING clears error)
- finalize_run (computes grade + completes)
"""

from __future__ import annotations

import json

import pytest

from elspeth.contracts import ExportStatus, NodeType, RunStatus
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _setup(*, run_id: str = "run-1") -> tuple[LandscapeDB, LandscapeRecorder]:
    """Create in-memory DB with a run."""
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    recorder.begin_run(config={"key": "value"}, canonical_version="v1", run_id=run_id)
    return db, recorder


class TestBeginRun:
    """Tests for begin_run — creates a new run record."""

    def test_returns_run_with_id(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1", run_id="my-run")
        assert run.run_id == "my-run"

    def test_generates_id_if_not_provided(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        assert run.run_id is not None
        assert len(run.run_id) == 32  # UUID hex

    def test_stores_config_hash(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={"key": "value"}, canonical_version="v1", run_id="r1")
        assert run.config_hash is not None
        assert len(run.config_hash) > 0

    def test_stores_settings_json(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={"key": "value"}, canonical_version="v1", run_id="r1")
        settings = json.loads(run.settings_json)
        assert settings == {"key": "value"}

    def test_initial_status_is_running(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        assert run.status == RunStatus.RUNNING

    def test_stores_reproducibility_grade(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(
            config={}, canonical_version="v1",
            reproducibility_grade="full_reproducible",
        )
        assert run.reproducibility_grade == "full_reproducible"


class TestGetRun:
    """Tests for get_run — retrieves run by ID."""

    def test_returns_run(self) -> None:
        _db, recorder = _setup()
        run = recorder.get_run("run-1")
        assert run is not None
        assert run.run_id == "run-1"

    def test_returns_none_for_unknown(self) -> None:
        _db, recorder = _setup()
        assert recorder.get_run("nonexistent") is None


class TestCompleteRun:
    """Tests for complete_run — finalizes a run."""

    def test_sets_completed_status(self) -> None:
        _db, recorder = _setup()
        run = recorder.complete_run("run-1", RunStatus.COMPLETED)
        assert run.status == RunStatus.COMPLETED
        assert run.completed_at is not None

    def test_sets_failed_status(self) -> None:
        _db, recorder = _setup()
        run = recorder.complete_run("run-1", RunStatus.FAILED)
        assert run.status == RunStatus.FAILED

    def test_stores_reproducibility_grade(self) -> None:
        _db, recorder = _setup()
        run = recorder.complete_run(
            "run-1", RunStatus.COMPLETED,
            reproducibility_grade="full_reproducible",
        )
        assert run.reproducibility_grade == "full_reproducible"


class TestGetSourceSchema:
    """Tests for get_source_schema — retrieves source schema for resume."""

    def test_returns_schema_json(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        schema_json = '{"type": "object", "properties": {"id": {"type": "integer"}}}'
        recorder.begin_run(
            config={}, canonical_version="v1", run_id="r1",
            source_schema_json=schema_json,
        )
        result = recorder.get_source_schema("r1")
        assert result == schema_json

    def test_raises_for_unknown_run(self) -> None:
        _db, recorder = _setup()
        with pytest.raises(ValueError, match="Run nonexistent not found"):
            recorder.get_source_schema("nonexistent")

    def test_raises_for_missing_schema(self) -> None:
        _db, recorder = _setup()
        with pytest.raises(ValueError, match="no source schema stored"):
            recorder.get_source_schema("run-1")


class TestSourceFieldResolution:
    """Tests for record/get_source_field_resolution — header mapping roundtrip."""

    def test_roundtrip(self) -> None:
        _db, recorder = _setup()
        mapping = {"Customer ID": "customer_id", "Amount ($)": "amount"}
        recorder.record_source_field_resolution("run-1", mapping, normalization_version="v1")
        result = recorder.get_source_field_resolution("run-1")
        assert result == mapping

    def test_returns_none_when_not_recorded(self) -> None:
        _db, recorder = _setup()
        result = recorder.get_source_field_resolution("run-1")
        assert result is None

    def test_raises_for_unknown_run(self) -> None:
        _db, recorder = _setup()
        with pytest.raises(ValueError, match="not found"):
            recorder.get_source_field_resolution("nonexistent")


class TestUpdateRunStatus:
    """Tests for update_run_status — intermediate status changes."""

    def test_updates_status(self) -> None:
        _db, recorder = _setup()
        recorder.update_run_status("run-1", RunStatus.FAILED)
        run = recorder.get_run("run-1")
        assert run.status == RunStatus.FAILED

    def test_does_not_set_completed_at(self) -> None:
        _db, recorder = _setup()
        recorder.update_run_status("run-1", RunStatus.FAILED)
        run = recorder.get_run("run-1")
        assert run.completed_at is None


class TestSecretResolutions:
    """Tests for record/get_secret_resolutions — Key Vault audit records."""

    def test_roundtrip(self) -> None:
        _db, recorder = _setup()
        resolutions = [
            {
                "env_var_name": "API_KEY",
                "source": "keyvault",
                "vault_url": "https://vault.example.com",
                "secret_name": "api-key",
                "timestamp": 1705320000.0,
                "latency_ms": 150.0,
                "fingerprint": "fp-hash-123",
            },
        ]
        recorder.record_secret_resolutions("run-1", resolutions)
        results = recorder.get_secret_resolutions_for_run("run-1")
        assert len(results) == 1
        assert results[0].env_var_name == "API_KEY"
        assert results[0].fingerprint == "fp-hash-123"
        assert results[0].vault_url == "https://vault.example.com"

    def test_empty_resolutions(self) -> None:
        _db, recorder = _setup()
        results = recorder.get_secret_resolutions_for_run("run-1")
        assert results == []


class TestListRuns:
    """Tests for list_runs — lists runs with optional filter."""

    def test_lists_all_runs(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="r1")
        recorder.begin_run(config={}, canonical_version="v1", run_id="r2")
        runs = recorder.list_runs()
        assert len(runs) == 2

    def test_filter_by_status(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="r1")
        recorder.begin_run(config={}, canonical_version="v1", run_id="r2")
        recorder.complete_run("r1", RunStatus.COMPLETED)
        running = recorder.list_runs(status=RunStatus.RUNNING)
        assert len(running) == 1
        assert running[0].run_id == "r2"


class TestSetExportStatus:
    """Tests for set_export_status — export status management."""

    def test_sets_completed_status(self) -> None:
        _db, recorder = _setup()
        recorder.set_export_status("run-1", ExportStatus.COMPLETED, export_format="json")
        run = recorder.get_run("run-1")
        assert run.export_status == ExportStatus.COMPLETED
        assert run.exported_at is not None
        assert run.export_format == "json"

    def test_sets_failed_with_error(self) -> None:
        _db, recorder = _setup()
        recorder.set_export_status("run-1", ExportStatus.FAILED, error="disk full")
        run = recorder.get_run("run-1")
        assert run.export_status == ExportStatus.FAILED
        assert run.export_error == "disk full"

    def test_completed_clears_stale_error(self) -> None:
        _db, recorder = _setup()
        recorder.set_export_status("run-1", ExportStatus.FAILED, error="first attempt failed")
        recorder.set_export_status("run-1", ExportStatus.COMPLETED)
        run = recorder.get_run("run-1")
        assert run.export_status == ExportStatus.COMPLETED
        assert run.export_error is None

    def test_pending_clears_stale_error(self) -> None:
        _db, recorder = _setup()
        recorder.set_export_status("run-1", ExportStatus.FAILED, error="old error")
        recorder.set_export_status("run-1", ExportStatus.PENDING)
        run = recorder.get_run("run-1")
        assert run.export_error is None


class TestFinalizeRun:
    """Tests for finalize_run — computes grade + completes."""

    def test_finalize_deterministic_run(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1", plugin_name="csv", node_type=NodeType.SOURCE,
            plugin_version="1.0", config={}, node_id="n1", schema_config=_DYNAMIC_SCHEMA,
        )
        run = recorder.finalize_run("run-1", RunStatus.COMPLETED)
        assert run.status == RunStatus.COMPLETED
        assert run.reproducibility_grade == "full_reproducible"
        assert run.completed_at is not None
