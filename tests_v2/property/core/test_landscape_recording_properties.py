# tests_v2/property/core/test_landscape_recording_properties.py
"""Property-based tests for landscape recording invariants.

The landscape recording system is the audit backbone of ELSPETH. These tests
verify invariants that must hold for the audit trail to be trustworthy:

1. Run lifecycle: begin→get round-trip preserves all fields
2. Token outcome contracts: each RowOutcome requires specific fields
3. Schema contract round-trip: store→retrieve preserves contract content
4. Config hash determinism: same config → same hash
5. Row recording referential integrity: rows link to valid runs
6. Run completion timestamp ordering: completed_at >= started_at

Testing approach:
- Uses LandscapeDB.in_memory() for isolated, fast property tests
- Hypothesis generates varied configs, field names, and outcome types
- Tests verify database-level invariants (not just API-level behavior)
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from elspeth.contracts import (
    NodeType,
    RowOutcome,
    RunStatus,
)
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder

# =============================================================================
# Strategies
# =============================================================================

# Simple config dicts for run creation
simple_configs = st.fixed_dictionaries({
    "source": st.fixed_dictionaries({"plugin": st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz")}),
})

# Canonical version strings
canonical_versions = st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True)

# Valid sink names for token outcomes
sink_names = st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_")

# Dummy group IDs
group_ids = st.text(min_size=8, max_size=32, alphabet="0123456789abcdef")

# Dummy error hashes
error_hashes = st.text(min_size=32, max_size=64, alphabet="0123456789abcdef")

# Row data for testing
row_data = st.fixed_dictionaries({
    "value": st.one_of(st.integers(min_value=-1000, max_value=1000), st.text(min_size=0, max_size=50)),
})

# Field names for schema contracts
field_names = st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_")


def _make_schema_config() -> SchemaConfig:
    """Create a dynamic schema config for testing."""
    return SchemaConfig.from_dict({"mode": "observed"})


# =============================================================================
# Run Lifecycle Round-Trip Properties
# =============================================================================


class TestRunLifecycleProperties:
    """begin_run → get_run must preserve all fields."""

    @given(config=simple_configs, version=canonical_versions)
    @settings(max_examples=100, deadline=None)
    def test_begin_get_round_trip(self, config: dict[str, Any], version: str) -> None:
        """Property: get_run returns the same data that begin_run stored."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(config=config, canonical_version=version)

            retrieved = recorder.get_run(run.run_id)
            assert retrieved is not None
            assert retrieved.run_id == run.run_id
            assert retrieved.config_hash == run.config_hash
            assert retrieved.canonical_version == version
            assert retrieved.status == RunStatus.RUNNING

    @given(config=simple_configs)
    @settings(max_examples=50, deadline=None)
    def test_run_id_uniqueness(self, config: dict[str, Any]) -> None:
        """Property: Auto-generated run IDs are unique across multiple begin_run calls."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            ids = set()
            for _ in range(5):
                run = recorder.begin_run(config=config, canonical_version="1.0")
                assert run.run_id not in ids, f"Duplicate run_id: {run.run_id}"
                ids.add(run.run_id)

    @given(config=simple_configs)
    @settings(max_examples=50, deadline=None)
    def test_config_hash_determinism(self, config: dict[str, Any]) -> None:
        """Property: Same config always produces the same config_hash."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run1 = recorder.begin_run(config=config, canonical_version="1.0")
            run2 = recorder.begin_run(config=config, canonical_version="1.0")
            assert run1.config_hash == run2.config_hash

    @given(config=simple_configs)
    @settings(max_examples=50, deadline=None)
    def test_complete_run_sets_status(self, config: dict[str, Any]) -> None:
        """Property: complete_run transitions status to the specified value."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(config=config, canonical_version="1.0")

            completed = recorder.complete_run(run.run_id, RunStatus.COMPLETED)
            assert completed.status == RunStatus.COMPLETED

    @given(config=simple_configs)
    @settings(max_examples=50, deadline=None)
    def test_complete_run_sets_completed_at(self, config: dict[str, Any]) -> None:
        """Property: complete_run sets completed_at timestamp."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(config=config, canonical_version="1.0")

            completed = recorder.complete_run(run.run_id, RunStatus.COMPLETED)
            assert completed.completed_at is not None

    @given(config=simple_configs)
    @settings(max_examples=30, deadline=None)
    def test_completed_at_after_started_at(self, config: dict[str, Any]) -> None:
        """Property: completed_at >= started_at (temporal ordering)."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(config=config, canonical_version="1.0")

            completed = recorder.complete_run(run.run_id, RunStatus.COMPLETED)
            assert completed.completed_at >= completed.started_at

    @given(config=simple_configs)
    @settings(max_examples=30, deadline=None)
    def test_initial_status_is_running(self, config: dict[str, Any]) -> None:
        """Property: Newly created runs have RUNNING status."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(config=config, canonical_version="1.0")
            assert run.status == RunStatus.RUNNING

    def test_get_nonexistent_run_returns_none(self) -> None:
        """Property: get_run for nonexistent ID returns None, not crash."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            assert recorder.get_run("nonexistent-id") is None

    @given(config=simple_configs)
    @settings(max_examples=30, deadline=None)
    def test_list_runs_includes_created(self, config: dict[str, Any]) -> None:
        """Property: list_runs includes all created runs."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run1 = recorder.begin_run(config=config, canonical_version="1.0")
            run2 = recorder.begin_run(config=config, canonical_version="1.0")

            runs = recorder.list_runs()
            run_ids = {r.run_id for r in runs}
            assert run1.run_id in run_ids
            assert run2.run_id in run_ids

    @given(config=simple_configs)
    @settings(max_examples=30, deadline=None)
    def test_list_runs_filters_by_status(self, config: dict[str, Any]) -> None:
        """Property: list_runs(status=X) returns only runs with that status."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            recorder.begin_run(config=config, canonical_version="1.0")
            run2 = recorder.begin_run(config=config, canonical_version="1.0")
            recorder.complete_run(run2.run_id, RunStatus.COMPLETED)

            running = recorder.list_runs(status=RunStatus.RUNNING)
            assert all(r.status == RunStatus.RUNNING for r in running)

            completed = recorder.list_runs(status=RunStatus.COMPLETED)
            assert all(r.status == RunStatus.COMPLETED for r in completed)


# =============================================================================
# Token Outcome Contract Enforcement Properties
# =============================================================================


class TestTokenOutcomeContractProperties:
    """Each RowOutcome requires specific fields — missing ones must raise ValueError."""

    def _setup(self) -> tuple[LandscapeDB, LandscapeRecorder, str, str]:
        """Create a run with a source row and token for testing outcomes."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(
            config={"source": {"plugin": "test"}},
            canonical_version="1.0",
        )
        source_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="test_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_make_schema_config(),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=source_node.node_id,
            row_index=0,
            data={"value": 1},
        )
        token = recorder.create_token(row_id=row.row_id)
        return db, recorder, run.run_id, token.token_id

    def test_completed_requires_sink_name(self) -> None:
        """Property: COMPLETED without sink_name raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="COMPLETED outcome requires sink_name"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.COMPLETED
            )
        db.close()

    @given(sink=sink_names)
    @settings(max_examples=30, deadline=None)
    def test_completed_with_sink_name_succeeds(self, sink: str) -> None:
        """Property: COMPLETED with valid sink_name succeeds."""
        db, recorder, run_id, token_id = self._setup()
        outcome_id = recorder.record_token_outcome(
            run_id=run_id, token_id=token_id, outcome=RowOutcome.COMPLETED, sink_name=sink
        )
        assert outcome_id is not None
        db.close()

    def test_routed_requires_sink_name(self) -> None:
        """Property: ROUTED without sink_name raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="ROUTED outcome requires sink_name"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.ROUTED
            )
        db.close()

    def test_forked_requires_fork_group_id(self) -> None:
        """Property: FORKED without fork_group_id raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="FORKED outcome requires fork_group_id"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.FORKED
            )
        db.close()

    def test_failed_requires_error_hash(self) -> None:
        """Property: FAILED without error_hash raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="FAILED outcome requires error_hash"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.FAILED
            )
        db.close()

    def test_quarantined_requires_error_hash(self) -> None:
        """Property: QUARANTINED without error_hash raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="QUARANTINED outcome requires error_hash"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.QUARANTINED
            )
        db.close()

    def test_consumed_in_batch_requires_batch_id(self) -> None:
        """Property: CONSUMED_IN_BATCH without batch_id raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="CONSUMED_IN_BATCH outcome requires batch_id"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.CONSUMED_IN_BATCH
            )
        db.close()

    def test_coalesced_requires_join_group_id(self) -> None:
        """Property: COALESCED without join_group_id raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="COALESCED outcome requires join_group_id"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.COALESCED
            )
        db.close()

    def test_expanded_requires_expand_group_id(self) -> None:
        """Property: EXPANDED without expand_group_id raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="EXPANDED outcome requires expand_group_id"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.EXPANDED
            )
        db.close()

    def test_buffered_requires_batch_id(self) -> None:
        """Property: BUFFERED without batch_id raises ValueError."""
        db, recorder, run_id, token_id = self._setup()
        with pytest.raises(ValueError, match="BUFFERED outcome requires batch_id"):
            recorder.record_token_outcome(
                run_id=run_id, token_id=token_id, outcome=RowOutcome.BUFFERED
            )
        db.close()


# =============================================================================
# Schema Contract Round-Trip Properties
# =============================================================================


class TestSchemaContractRoundTripProperties:
    """Schema contracts stored in runs must survive round-trip."""

    @given(
        field_name=field_names,
        field_type=st.sampled_from([str, int, float, bool]),
    )
    @settings(max_examples=50, deadline=None)
    def test_contract_round_trip(self, field_name: str, field_type: type) -> None:
        """Property: update_run_contract → get_run_contract preserves field info."""
        field = FieldContract(
            normalized_name=field_name,
            original_name=field_name,
            python_type=field_type,
            required=True,
            source="declared",
        )
        contract = SchemaContract(mode="FIXED", fields=(field,), locked=True)

        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )

            recorder.update_run_contract(run.run_id, contract)
            restored = recorder.get_run_contract(run.run_id)

            assert restored is not None
            assert restored.mode == "FIXED"
            assert len(restored.fields) == 1
            assert restored.fields[0].normalized_name == field_name
            assert restored.fields[0].python_type == field_type

    @given(
        n_fields=st.integers(min_value=1, max_value=5),
        data=st.data(),
    )
    @settings(max_examples=30, deadline=None)
    def test_multi_field_contract_round_trip(self, n_fields: int, data: st.DataObject) -> None:
        """Property: Multi-field contracts survive round-trip."""
        # Generate unique field names
        names = data.draw(
            st.lists(
                field_names,
                min_size=n_fields,
                max_size=n_fields,
                unique=True,
            )
        )
        fields_list = [
            FieldContract(
                normalized_name=name,
                original_name=name,
                python_type=str,
                required=True,
                source="declared",
            )
            for name in names
        ]
        contract = SchemaContract(
            mode="FIXED", fields=tuple(fields_list), locked=True
        )

        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )

            recorder.update_run_contract(run.run_id, contract)
            restored = recorder.get_run_contract(run.run_id)

            assert restored is not None
            assert len(restored.fields) == n_fields
            restored_names = {f.normalized_name for f in restored.fields}
            for name in names:
                assert name in restored_names

    def test_no_contract_returns_none(self) -> None:
        """Property: get_run_contract returns None when no contract stored."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            assert recorder.get_run_contract(run.run_id) is None


# =============================================================================
# Row-Token Referential Integrity Properties
# =============================================================================


class TestReferentialIntegrityProperties:
    """Tokens must always link to valid rows, rows to valid runs."""

    @given(n_rows=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_all_tokens_have_valid_rows(self, n_rows: int) -> None:
        """Property: Every token's row_id exists in the rows table."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            source = recorder.register_node(
                run_id=run.run_id,
                plugin_name="src",
                node_type=NodeType.SOURCE,
                plugin_version="1.0.0",
                config={},
                schema_config=_make_schema_config(),
            )

            for i in range(n_rows):
                row = recorder.create_row(
                    run_id=run.run_id,
                    source_node_id=source.node_id,
                    row_index=i,
                    data={"i": i},
                )
                recorder.create_token(row_id=row.row_id)

            # Verify no orphan tokens
            with db.connection() as conn:
                orphans = conn.execute(
                    text("""
                        SELECT COUNT(*) FROM tokens t
                        LEFT JOIN rows r ON r.row_id = t.row_id
                        WHERE r.row_id IS NULL
                    """)
                ).scalar()
                assert orphans == 0

    @given(n_rows=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_all_rows_have_valid_runs(self, n_rows: int) -> None:
        """Property: Every row's run_id exists in the runs table."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            source = recorder.register_node(
                run_id=run.run_id,
                plugin_name="src",
                node_type=NodeType.SOURCE,
                plugin_version="1.0.0",
                config={},
                schema_config=_make_schema_config(),
            )

            for i in range(n_rows):
                recorder.create_row(
                    run_id=run.run_id,
                    source_node_id=source.node_id,
                    row_index=i,
                    data={"i": i},
                )

            # Verify no orphan rows
            with db.connection() as conn:
                orphans = conn.execute(
                    text("""
                        SELECT COUNT(*) FROM rows r
                        LEFT JOIN runs ru ON ru.run_id = r.run_id
                        WHERE ru.run_id IS NULL
                    """)
                ).scalar()
                assert orphans == 0

    @given(branch_count=st.integers(min_value=2, max_value=5))
    @settings(max_examples=30, deadline=None)
    def test_fork_children_share_row_id(self, branch_count: int) -> None:
        """Property: All fork children reference the same row_id as parent."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            source = recorder.register_node(
                run_id=run.run_id,
                plugin_name="src",
                node_type=NodeType.SOURCE,
                plugin_version="1.0.0",
                config={},
                schema_config=_make_schema_config(),
            )

            row = recorder.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=0,
                data={"v": 1},
            )
            parent = recorder.create_token(row_id=row.row_id)

            branches = [f"b_{i}" for i in range(branch_count)]
            children, _fork_group_id = recorder.fork_token(
                parent_token_id=parent.token_id,
                row_id=row.row_id,
                branches=branches,
                run_id=run.run_id,
            )

            assert len(children) == branch_count
            for child in children:
                assert child.row_id == row.row_id

    def test_fork_with_empty_branches_raises(self) -> None:
        """Property: fork_token rejects empty branch list."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            source = recorder.register_node(
                run_id=run.run_id,
                plugin_name="src",
                node_type=NodeType.SOURCE,
                plugin_version="1.0.0",
                config={},
                schema_config=_make_schema_config(),
            )
            row = recorder.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=0,
                data={"v": 1},
            )
            parent = recorder.create_token(row_id=row.row_id)

            with pytest.raises(ValueError, match="at least one branch"):
                recorder.fork_token(
                    parent_token_id=parent.token_id,
                    row_id=row.row_id,
                    branches=[],
                    run_id=run.run_id,
                )

    @given(count=st.integers(min_value=1, max_value=5))
    @settings(max_examples=30, deadline=None)
    def test_expand_creates_correct_children(self, count: int) -> None:
        """Property: expand_token creates exactly N children."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            source = recorder.register_node(
                run_id=run.run_id,
                plugin_name="src",
                node_type=NodeType.SOURCE,
                plugin_version="1.0.0",
                config={},
                schema_config=_make_schema_config(),
            )
            row = recorder.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=0,
                data={"v": 1},
            )
            parent = recorder.create_token(row_id=row.row_id)

            children, expand_group_id = recorder.expand_token(
                parent_token_id=parent.token_id,
                row_id=row.row_id,
                count=count,
                run_id=run.run_id,
            )

            assert len(children) == count
            assert expand_group_id is not None
            for child in children:
                assert child.row_id == row.row_id
                assert child.expand_group_id == expand_group_id


# =============================================================================
# Source Field Resolution Round-Trip Properties
# =============================================================================


class TestFieldResolutionProperties:
    """Source field resolution must survive round-trip."""

    @given(
        data=st.data(),
        n_fields=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=30, deadline=None)
    def test_resolution_mapping_round_trip(self, data: st.DataObject, n_fields: int) -> None:
        """Property: record→get field resolution preserves mapping."""
        originals = data.draw(
            st.lists(field_names, min_size=n_fields, max_size=n_fields, unique=True)
        )
        finals = data.draw(
            st.lists(field_names, min_size=n_fields, max_size=n_fields, unique=True)
        )
        mapping = dict(zip(originals, finals, strict=False))

        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )

            recorder.record_source_field_resolution(
                run_id=run.run_id,
                resolution_mapping=mapping,
                normalization_version="v1",
            )

            retrieved = recorder.get_source_field_resolution(run.run_id)
            assert retrieved == mapping

    def test_no_resolution_returns_none(self) -> None:
        """Property: get_source_field_resolution returns None when not recorded."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            assert recorder.get_source_field_resolution(run.run_id) is None


# =============================================================================
# Row Data Hash Determinism Properties
# =============================================================================


class TestRowHashProperties:
    """Row data hashes must be deterministic and unique for different data."""

    @given(data=row_data)
    @settings(max_examples=50, deadline=None)
    def test_same_data_same_hash(self, data: dict[str, Any]) -> None:
        """Property: Identical data produces identical source_data_hash."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            source = recorder.register_node(
                run_id=run.run_id,
                plugin_name="src",
                node_type=NodeType.SOURCE,
                plugin_version="1.0.0",
                config={},
                schema_config=_make_schema_config(),
            )

            row1 = recorder.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=0,
                data=data,
            )
            row2 = recorder.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=1,
                data=data,
            )

            assert row1.source_data_hash == row2.source_data_hash

    @given(
        data1=st.fixed_dictionaries({"value": st.just(1)}),
        data2=st.fixed_dictionaries({"value": st.just(2)}),
    )
    @settings(max_examples=10, deadline=None)
    def test_different_data_different_hash(
        self, data1: dict[str, Any], data2: dict[str, Any]
    ) -> None:
        """Property: Different data produces different source_data_hash."""
        with LandscapeDB.in_memory() as db:
            recorder = LandscapeRecorder(db)
            run = recorder.begin_run(
                config={"source": {"plugin": "test"}},
                canonical_version="1.0",
            )
            source = recorder.register_node(
                run_id=run.run_id,
                plugin_name="src",
                node_type=NodeType.SOURCE,
                plugin_version="1.0.0",
                config={},
                schema_config=_make_schema_config(),
            )

            row1 = recorder.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=0,
                data=data1,
            )
            row2 = recorder.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=1,
                data=data2,
            )

            assert row1.source_data_hash != row2.source_data_hash
