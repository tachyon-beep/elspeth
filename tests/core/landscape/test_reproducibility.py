# tests/core/landscape/test_reproducibility.py
"""Tests for reproducibility grade management."""

import pytest

from elspeth.contracts import RunStatus


class TestReproducibilityGradeComparison:
    """Verify reproducibility uses proper enum comparison."""

    def test_update_grade_after_purge_uses_enum(self) -> None:
        """update_grade_after_purge compares enums, not strings."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import (
            ReproducibilityGrade,
            set_run_grade,
            update_grade_after_purge,
        )

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        recorder.complete_run(run.run_id, status=RunStatus.COMPLETED)

        # Set to REPLAY_REPRODUCIBLE
        set_run_grade(db, run.run_id, ReproducibilityGrade.REPLAY_REPRODUCIBLE)

        # After purge, should degrade to ATTRIBUTABLE_ONLY
        update_grade_after_purge(db, run.run_id)

        updated_run = recorder.get_run(run.run_id)
        assert updated_run is not None
        assert updated_run.reproducibility_grade == ReproducibilityGrade.ATTRIBUTABLE_ONLY.value

    def test_update_grade_after_purge_full_reproducible_unchanged(self) -> None:
        """FULL_REPRODUCIBLE grade is not degraded after purge."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import (
            ReproducibilityGrade,
            set_run_grade,
            update_grade_after_purge,
        )

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        recorder.complete_run(run.run_id, status=RunStatus.COMPLETED)

        # Set to FULL_REPRODUCIBLE
        set_run_grade(db, run.run_id, ReproducibilityGrade.FULL_REPRODUCIBLE)

        # After purge, should remain FULL_REPRODUCIBLE
        update_grade_after_purge(db, run.run_id)

        updated_run = recorder.get_run(run.run_id)
        assert updated_run is not None
        assert updated_run.reproducibility_grade == ReproducibilityGrade.FULL_REPRODUCIBLE.value

    def test_update_grade_after_purge_attributable_only_unchanged(self) -> None:
        """ATTRIBUTABLE_ONLY grade is not degraded further."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import (
            ReproducibilityGrade,
            set_run_grade,
            update_grade_after_purge,
        )

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        recorder.complete_run(run.run_id, status=RunStatus.COMPLETED)

        # Set to ATTRIBUTABLE_ONLY
        set_run_grade(db, run.run_id, ReproducibilityGrade.ATTRIBUTABLE_ONLY)

        # After purge, should remain ATTRIBUTABLE_ONLY
        update_grade_after_purge(db, run.run_id)

        updated_run = recorder.get_run(run.run_id)
        assert updated_run is not None
        assert updated_run.reproducibility_grade == ReproducibilityGrade.ATTRIBUTABLE_ONLY.value

    def test_update_grade_after_purge_null_grade_raises(self) -> None:
        """NULL reproducibility_grade in audit data causes fail-fast error.

        Per Data Manifesto: "Bad data in the audit trail = crash immediately"
        """
        from sqlalchemy import text

        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import update_grade_after_purge

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        recorder.complete_run(run.run_id, status=RunStatus.COMPLETED)

        # Directly set grade to NULL to simulate corruption
        with db.connection() as conn:
            conn.execute(
                text("UPDATE runs SET reproducibility_grade = NULL WHERE run_id = :run_id"),
                {"run_id": run.run_id},
            )

        # Should raise ValueError on NULL grade (audit data corruption)
        with pytest.raises(ValueError, match="NULL reproducibility_grade"):
            update_grade_after_purge(db, run.run_id)

    def test_update_grade_after_purge_invalid_grade_raises(self) -> None:
        """Invalid reproducibility_grade in audit data causes fail-fast error.

        Per Data Manifesto: "invalid enum value = crash"
        """
        from sqlalchemy import text

        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import update_grade_after_purge

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        recorder.complete_run(run.run_id, status=RunStatus.COMPLETED)

        # Directly set grade to invalid value to simulate corruption
        with db.connection() as conn:
            conn.execute(
                text("UPDATE runs SET reproducibility_grade = 'garbage_value' WHERE run_id = :run_id"),
                {"run_id": run.run_id},
            )

        # Should raise ValueError on invalid enum value (audit data corruption)
        with pytest.raises(ValueError, match="garbage_value"):
            update_grade_after_purge(db, run.run_id)

    def test_update_grade_after_purge_nonexistent_run_is_noop(self) -> None:
        """Non-existent run ID is handled gracefully (no error)."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.reproducibility import update_grade_after_purge

        db = LandscapeDB.in_memory()

        # Should not raise - just returns silently
        update_grade_after_purge(db, "nonexistent_run_id")


class TestComputeGradeValidation:
    """Verify compute_grade validates determinism enum values (Tier-1 crash-on-corruption)."""

    def test_compute_grade_crashes_on_invalid_determinism_value(self) -> None:
        """compute_grade raises ValueError when node has invalid determinism enum.

        Per Data Manifesto (Tier-1): "Bad data in the audit trail = crash immediately"
        Invalid enum values must crash, not be silently treated as reproducible.
        """
        from sqlalchemy import text

        from elspeth.contracts import Determinism, NodeType
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import compute_grade

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Register a node with valid determinism
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="field_mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=SchemaConfig.from_dict({"mode": "observed"}),
            determinism=Determinism.DETERMINISTIC,
        )

        # Corrupt the determinism value in the audit database
        with db.connection() as conn:
            conn.execute(
                text("UPDATE nodes SET determinism = 'garbage_value' WHERE node_id = :node_id"),
                {"node_id": node.node_id},
            )

        # compute_grade should crash on invalid determinism enum value
        with pytest.raises(ValueError, match="garbage_value"):
            compute_grade(db, run.run_id)

    def test_compute_grade_io_read_requires_replay(self) -> None:
        """Runs with IO_READ nodes are graded REPLAY_REPRODUCIBLE, not FULL_REPRODUCIBLE.

        Per determinism contract: IO_READ is external/side-effectful, requires capture/replay.
        """
        from elspeth.contracts import Determinism, NodeType
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import (
            ReproducibilityGrade,
            compute_grade,
        )

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Register a node with IO_READ determinism
        recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=SchemaConfig.from_dict({"mode": "observed"}),
            determinism=Determinism.IO_READ,
        )

        grade = compute_grade(db, run.run_id)
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE

    def test_compute_grade_io_write_requires_replay(self) -> None:
        """Runs with IO_WRITE nodes are graded REPLAY_REPRODUCIBLE, not FULL_REPRODUCIBLE.

        Per determinism contract: IO_WRITE is external/side-effectful, requires capture/replay.
        """
        from elspeth.contracts import Determinism, NodeType
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.reproducibility import (
            ReproducibilityGrade,
            compute_grade,
        )

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Register a node with IO_WRITE determinism
        recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=SchemaConfig.from_dict({"mode": "observed"}),
            determinism=Determinism.IO_WRITE,
        )

        grade = compute_grade(db, run.run_id)
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE
