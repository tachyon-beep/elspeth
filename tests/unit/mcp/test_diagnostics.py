# tests/unit/mcp/test_diagnostics.py
"""Tests for MCP diagnostics analyzer behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from elspeth.contracts import NodeType, RowOutcome, RunStatus
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.landscape.schema import runs_table
from elspeth.mcp.analyzers.diagnostics import diagnose
from elspeth.mcp.types import DiagnosticProblem, DiagnosticReport
from tests.fixtures.landscape import make_landscape_db, make_recorder

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _set_run_started_at(db: LandscapeDB, run_id: str, started_at: datetime) -> None:
    with db.connection() as conn:
        conn.execute(runs_table.update().where(runs_table.c.run_id == run_id).values(started_at=started_at))


def _create_running_run(recorder: LandscapeRecorder) -> str:
    run = recorder.begin_run(
        config={"source": {"plugin": "csv"}},
        canonical_version="v1",
        status=RunStatus.RUNNING,
    )
    return run.run_id


def _create_completed_run_with_quarantine(
    db: LandscapeDB,
    recorder: LandscapeRecorder,
    *,
    run_id: str,
    started_at: datetime | None = None,
) -> str:
    """Create a completed run with one quarantined token."""
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="csv",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id=f"source-{run_id}",
        schema_config=_DYNAMIC_SCHEMA,
    )
    row = recorder.create_row(
        run_id=run_id,
        source_node_id=f"source-{run_id}",
        row_index=0,
        data={"col": "bad-value"},
    )
    token = recorder.create_token(row.row_id)
    recorder.record_token_outcome(
        run_id=run_id,
        token_id=token.token_id,
        outcome=RowOutcome.QUARANTINED,
        error_hash="deadbeef" * 8,
    )
    recorder.complete_run(run_id, RunStatus.COMPLETED)
    if started_at is not None:
        _set_run_started_at(db, run_id, started_at)
    return run_id


def _get_problem(report: DiagnosticReport, problem_type: str) -> DiagnosticProblem | None:
    for problem in report["problems"]:
        if problem.get("type") == problem_type:
            return problem
    return None


def test_diagnose_does_not_flag_recent_running_run_as_stuck() -> None:
    """A newly started run should not appear in stuck_runs."""
    db = make_landscape_db()
    recorder = make_recorder(db)
    _create_running_run(recorder)

    report = diagnose(db, recorder)

    assert _get_problem(report, "stuck_runs") is None


def test_diagnose_flags_old_running_run_as_stuck() -> None:
    """A running run older than one hour should appear in stuck_runs."""
    db = make_landscape_db()
    recorder = make_recorder(db)
    run_id = _create_running_run(recorder)

    _set_run_started_at(db, run_id, datetime.now(UTC) - timedelta(hours=2))
    report = diagnose(db, recorder)

    stuck_runs = _get_problem(report, "stuck_runs")
    assert stuck_runs is not None
    assert stuck_runs["count"] == 1
    assert stuck_runs["run_ids"] == [run_id]


def test_diagnose_reports_only_old_runs_in_mixed_running_set() -> None:
    """Only runs beyond the stuck threshold should be reported."""
    db = make_landscape_db()
    recorder = make_recorder(db)
    recent_run_id = _create_running_run(recorder)
    old_run_id = _create_running_run(recorder)

    _set_run_started_at(db, old_run_id, datetime.now(UTC) - timedelta(hours=2))
    report = diagnose(db, recorder)

    stuck_runs = _get_problem(report, "stuck_runs")
    assert stuck_runs is not None
    assert stuck_runs["count"] == 1
    assert stuck_runs["run_ids"] == [old_run_id]
    assert recent_run_id not in stuck_runs["run_ids"]


# --- T5: Quarantine count scoping ---


def test_diagnose_quarantine_count_excludes_old_runs() -> None:
    """Quarantine count should only reflect recent runs, not all history."""
    db = make_landscape_db()
    recorder = make_recorder(db)

    # Old run (30 days ago) with quarantined row
    _create_completed_run_with_quarantine(
        db,
        recorder,
        run_id="old-run",
        started_at=datetime.now(UTC) - timedelta(days=30),
    )
    # Recent run (1 hour ago) — no quarantines
    recorder.begin_run(config={}, canonical_version="v1", run_id="recent-run")
    recorder.complete_run("recent-run", RunStatus.COMPLETED)

    report = diagnose(db, recorder)

    # Old quarantines should NOT appear in the report
    quarantined = _get_problem(report, "quarantined_rows")
    assert quarantined is None, (
        f"Old quarantined rows from 30 days ago should not appear in diagnose(), but got count={quarantined['count']}"
    )


def test_diagnose_quarantine_count_includes_recent_runs() -> None:
    """Quarantine count should include quarantines from recent runs."""
    db = make_landscape_db()
    recorder = make_recorder(db)

    # Recent run with quarantined row
    _create_completed_run_with_quarantine(
        db,
        recorder,
        run_id="recent-run",
    )

    report = diagnose(db, recorder)

    quarantined = _get_problem(report, "quarantined_rows")
    assert quarantined is not None
    assert quarantined["count"] == 1


def test_diagnose_quarantine_count_scoped_to_recent_runs_only() -> None:
    """With both old and recent quarantines, only recent ones counted."""
    db = make_landscape_db()
    recorder = make_recorder(db)

    # Old run with 1 quarantine
    _create_completed_run_with_quarantine(
        db,
        recorder,
        run_id="old-run",
        started_at=datetime.now(UTC) - timedelta(days=30),
    )
    # Recent run with 1 quarantine
    _create_completed_run_with_quarantine(
        db,
        recorder,
        run_id="recent-run",
    )

    report = diagnose(db, recorder)

    quarantined = _get_problem(report, "quarantined_rows")
    assert quarantined is not None
    # Should only count the recent run's quarantine, not the old one
    assert quarantined["count"] == 1, f"Expected 1 quarantined row (recent only), got {quarantined['count']}"
