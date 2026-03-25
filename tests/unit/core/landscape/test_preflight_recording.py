"""Tests for pre-flight result recording in Landscape audit trail."""

from __future__ import annotations

import json

import pytest

from elspeth.core.dependency_config import (
    CommencementGateResult,
    DependencyRunResult,
    PreflightResult,
)
from elspeth.core.landscape import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.landscape.schema import preflight_results_table
from elspeth.core.payload_store import FilesystemPayloadStore


@pytest.fixture()
def recorder(tmp_path):
    """Create a recorder with a fresh in-memory database."""
    db = LandscapeDB.from_url("sqlite:///:memory:")
    payload_store = FilesystemPayloadStore(tmp_path / "payloads")
    rec = LandscapeRecorder(db, payload_store=payload_store)
    run = rec.begin_run(config={"test": True}, canonical_version="sha256-rfc8785-v1")
    yield rec, run.run_id, db
    db.close()


class TestRecordPreflightResults:
    def test_dependency_run_recorded_and_readable(self, recorder) -> None:
        rec, run_id, db = recorder
        preflight = PreflightResult(
            dependency_runs=(
                DependencyRunResult(
                    name="indexer",
                    run_id="dep-abc",
                    settings_hash="sha256:deadbeef",
                    duration_ms=1500,
                    indexed_at="2026-03-25T12:00:00Z",
                ),
            ),
            gate_results=(),
        )

        rec.record_preflight_results(run_id=run_id, preflight=preflight)

        # Read back from database
        with db.connection() as conn:
            rows = conn.execute(preflight_results_table.select().where(preflight_results_table.c.run_id == run_id)).fetchall()

        assert len(rows) == 1
        row = rows[0]
        assert row.result_type == "dependency_run"
        assert row.name == "indexer"
        data = json.loads(row.result_json)
        assert data["run_id"] == "dep-abc"
        assert data["settings_hash"] == "sha256:deadbeef"
        assert data["duration_ms"] == 1500

    def test_gate_result_with_nested_snapshot_recorded(self, recorder) -> None:
        """Nested MappingProxyType in context_snapshot must serialize correctly (bug #1)."""
        rec, run_id, db = recorder
        preflight = PreflightResult(
            dependency_runs=(),
            gate_results=(
                CommencementGateResult(
                    name="corpus_ready",
                    condition="collections['test']['count'] > 0",
                    result=True,
                    context_snapshot={
                        "collections": {"test": {"count": 42, "reachable": True}},
                        "dependency_runs": {"indexer": {"run_id": "dep-abc"}},
                    },
                ),
            ),
        )

        rec.record_preflight_results(run_id=run_id, preflight=preflight)

        with db.connection() as conn:
            rows = conn.execute(preflight_results_table.select().where(preflight_results_table.c.run_id == run_id)).fetchall()

        assert len(rows) == 1
        row = rows[0]
        assert row.result_type == "commencement_gate"
        assert row.name == "corpus_ready"
        data = json.loads(row.result_json)
        assert data["condition"] == "collections['test']['count'] > 0"
        assert data["result"] is True
        # Nested snapshot must round-trip correctly
        assert data["context_snapshot"]["collections"]["test"]["count"] == 42

    def test_empty_preflight_is_noop(self, recorder) -> None:
        rec, run_id, db = recorder
        preflight = PreflightResult(dependency_runs=(), gate_results=())

        rec.record_preflight_results(run_id=run_id, preflight=preflight)

        with db.connection() as conn:
            rows = conn.execute(preflight_results_table.select().where(preflight_results_table.c.run_id == run_id)).fetchall()

        assert len(rows) == 0

    def test_mixed_deps_and_gates(self, recorder) -> None:
        rec, run_id, db = recorder
        preflight = PreflightResult(
            dependency_runs=(
                DependencyRunResult(name="dep1", run_id="r1", settings_hash="h1", duration_ms=100, indexed_at="t1"),
                DependencyRunResult(name="dep2", run_id="r2", settings_hash="h2", duration_ms=200, indexed_at="t2"),
            ),
            gate_results=(CommencementGateResult(name="gate1", condition="True", result=True, context_snapshot={}),),
        )

        rec.record_preflight_results(run_id=run_id, preflight=preflight)

        with db.connection() as conn:
            rows = conn.execute(
                preflight_results_table.select().where(preflight_results_table.c.run_id == run_id).order_by(preflight_results_table.c.name)
            ).fetchall()

        assert len(rows) == 3
        types = {r.result_type for r in rows}
        assert types == {"dependency_run", "commencement_gate"}
        names = [r.name for r in rows]
        assert "dep1" in names
        assert "dep2" in names
        assert "gate1" in names


class TestPreflightResult:
    def test_construction(self) -> None:
        dep = DependencyRunResult(name="x", run_id="r", settings_hash="h", duration_ms=0, indexed_at="t")
        gate = CommencementGateResult(name="g", condition="True", result=True, context_snapshot={})
        pf = PreflightResult(dependency_runs=(dep,), gate_results=(gate,))
        assert len(pf.dependency_runs) == 1
        assert len(pf.gate_results) == 1

    def test_empty_tuples(self) -> None:
        pf = PreflightResult(dependency_runs=(), gate_results=())
        assert pf.dependency_runs == ()
        assert pf.gate_results == ()

    def test_frozen(self) -> None:
        pf = PreflightResult(dependency_runs=(), gate_results=())
        with pytest.raises(AttributeError):
            pf.dependency_runs = ()  # type: ignore[misc]
