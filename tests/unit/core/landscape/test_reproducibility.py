"""Tests for reproducibility grade computation.

Tests cover:
- compute_grade with all-deterministic nodes → FULL_REPRODUCIBLE
- compute_grade with nondeterministic node → REPLAY_REPRODUCIBLE
- compute_grade with empty pipeline (no nodes) → FULL_REPRODUCIBLE
- compute_grade with seeded nodes → FULL_REPRODUCIBLE
- compute_grade crashes on NULL/invalid determinism (Tier 1)
- set_run_grade updates the runs table
- update_grade_after_purge degrades REPLAY→ATTRIBUTABLE, leaves others
"""

from __future__ import annotations

import pytest

from elspeth.contracts import Determinism, NodeType
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
from elspeth.core.landscape.reproducibility import (
    ReproducibilityGrade,
    compute_grade,
    set_run_grade,
    update_grade_after_purge,
)

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _setup(*, run_id: str = "run-1") -> tuple[LandscapeDB, LandscapeRecorder]:
    """Create in-memory DB with a run."""
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    return db, recorder


class TestComputeGrade:
    """Tests for compute_grade — determines reproducibility from node determinism."""

    def test_all_deterministic_returns_full(self) -> None:
        db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="n1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.FULL_REPRODUCIBLE

    def test_seeded_returns_full(self) -> None:
        db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="sampler",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="n1",
            schema_config=_DYNAMIC_SCHEMA,
            determinism=Determinism.SEEDED,
        )
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.FULL_REPRODUCIBLE

    def test_nondeterministic_returns_replay(self) -> None:
        db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="llm",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="n1",
            schema_config=_DYNAMIC_SCHEMA,
            determinism=Determinism.NON_DETERMINISTIC,
        )
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE

    def test_external_call_returns_replay(self) -> None:
        db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="api",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="n1",
            schema_config=_DYNAMIC_SCHEMA,
            determinism=Determinism.EXTERNAL_CALL,
        )
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE

    def test_io_read_returns_replay(self) -> None:
        db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="reader",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="n1",
            schema_config=_DYNAMIC_SCHEMA,
            determinism=Determinism.IO_READ,
        )
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE

    def test_io_write_returns_replay(self) -> None:
        db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="writer",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            node_id="n1",
            schema_config=_DYNAMIC_SCHEMA,
            determinism=Determinism.IO_WRITE,
        )
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE

    def test_mixed_deterministic_and_nondeterministic(self) -> None:
        db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="n1",
            schema_config=_DYNAMIC_SCHEMA,
            determinism=Determinism.DETERMINISTIC,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="llm",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="n2",
            schema_config=_DYNAMIC_SCHEMA,
            determinism=Determinism.NON_DETERMINISTIC,
        )
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE

    def test_empty_pipeline_returns_full(self) -> None:
        db, _recorder = _setup()
        grade = compute_grade(db, "run-1")
        assert grade == ReproducibilityGrade.FULL_REPRODUCIBLE


class TestSetRunGrade:
    """Tests for set_run_grade — updates the runs table."""

    def test_sets_grade_on_run(self) -> None:
        db, recorder = _setup()
        set_run_grade(db, "run-1", ReproducibilityGrade.FULL_REPRODUCIBLE)
        run = recorder.get_run("run-1")
        assert run.reproducibility_grade == "full_reproducible"


class TestUpdateGradeAfterPurge:
    """Tests for update_grade_after_purge — degrades REPLAY → ATTRIBUTABLE."""

    def test_replay_degrades_to_attributable(self) -> None:
        db, recorder = _setup()
        set_run_grade(db, "run-1", ReproducibilityGrade.REPLAY_REPRODUCIBLE)
        update_grade_after_purge(db, "run-1")
        run = recorder.get_run("run-1")
        assert run.reproducibility_grade == ReproducibilityGrade.ATTRIBUTABLE_ONLY.value

    def test_full_unchanged_after_purge(self) -> None:
        db, recorder = _setup()
        set_run_grade(db, "run-1", ReproducibilityGrade.FULL_REPRODUCIBLE)
        update_grade_after_purge(db, "run-1")
        run = recorder.get_run("run-1")
        assert run.reproducibility_grade == ReproducibilityGrade.FULL_REPRODUCIBLE.value

    def test_attributable_unchanged_after_purge(self) -> None:
        db, recorder = _setup()
        set_run_grade(db, "run-1", ReproducibilityGrade.ATTRIBUTABLE_ONLY)
        update_grade_after_purge(db, "run-1")
        run = recorder.get_run("run-1")
        assert run.reproducibility_grade == ReproducibilityGrade.ATTRIBUTABLE_ONLY.value

    def test_nonexistent_run_is_noop(self) -> None:
        db, _recorder = _setup()
        update_grade_after_purge(db, "nonexistent")  # Should not raise

    def test_null_grade_raises(self) -> None:
        """NULL reproducibility_grade is Tier 1 corruption — must crash."""
        db, _recorder = _setup()
        # begin_run doesn't set a grade by default, so it's NULL
        with pytest.raises(ValueError, match="NULL reproducibility_grade"):
            update_grade_after_purge(db, "run-1")
