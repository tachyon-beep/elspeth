from __future__ import annotations

import pytest

from elspeth.contracts import NodeType, RowOutcome
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _setup(*, run_id: str = "run-1") -> tuple[LandscapeDB, LandscapeRecorder]:
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="csv",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id="source-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.register_node(
        run_id=run_id,
        plugin_name="count_agg",
        node_type=NodeType.AGGREGATION,
        plugin_version="1.0",
        config={},
        node_id="agg-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    return db, recorder


def _make_batch(recorder: LandscapeRecorder, *, run_id: str = "run-1", batch_id: str = "batch-1") -> str:
    """Helper to create a batch and return its batch_id."""
    batch = recorder.create_batch(
        run_id=run_id,
        aggregation_node_id="agg-0",
        batch_id=batch_id,
    )
    return batch.batch_id


def _make_row(recorder: LandscapeRecorder, *, run_id: str = "run-1", row_index: int = 0):
    """Helper to create a row and its initial token."""
    row = recorder.create_row(
        run_id=run_id,
        source_node_id="source-0",
        row_index=row_index,
        data={"col": f"value-{row_index}"},
    )
    token = recorder.create_token(row.row_id)
    return row, token


class TestCreateRow:
    """Tests for TokenRecordingMixin.create_row."""

    def test_creates_row_with_generated_id(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"name": "Alice"},
        )
        assert row.row_id is not None
        assert row.run_id == "run-1"
        assert row.source_node_id == "source-0"
        assert row.row_index == 0

    def test_creates_row_with_explicit_id(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"name": "Alice"},
            row_id="custom-row-id",
        )
        assert row.row_id == "custom-row-id"

    def test_stores_source_data_hash(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"name": "Alice"},
        )
        assert row.source_data_hash is not None
        assert len(row.source_data_hash) > 0

    def test_deterministic_hash_for_same_data(self):
        _db, recorder = _setup()
        row_a = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"name": "Alice"},
        )
        row_b = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=1,
            data={"name": "Alice"},
        )
        assert row_a.source_data_hash == row_b.source_data_hash

    def test_different_hash_for_different_data(self):
        _db, recorder = _setup()
        row_a = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"name": "Alice"},
        )
        row_b = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=1,
            data={"name": "Bob"},
        )
        assert row_a.source_data_hash != row_b.source_data_hash

    def test_roundtrip_via_get_row(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"name": "Alice"},
        )
        fetched = recorder.get_row(row.row_id)
        assert fetched is not None
        assert fetched.row_id == row.row_id
        assert fetched.run_id == row.run_id
        assert fetched.source_node_id == row.source_node_id
        assert fetched.row_index == row.row_index
        assert fetched.source_data_hash == row.source_data_hash

    def test_created_at_is_set(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        assert row.created_at is not None

    def test_multiple_rows_get_unique_ids(self):
        _db, recorder = _setup()
        rows = [
            recorder.create_row(
                run_id="run-1",
                source_node_id="source-0",
                row_index=i,
                data={"i": i},
            )
            for i in range(5)
        ]
        row_ids = [r.row_id for r in rows]
        assert len(set(row_ids)) == 5


class TestCreateToken:
    """Tests for TokenRecordingMixin.create_token."""

    def test_creates_token_with_generated_id(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        token = recorder.create_token(row.row_id)
        assert token.token_id is not None
        assert token.row_id == row.row_id

    def test_creates_token_with_explicit_id(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        token = recorder.create_token(row.row_id, token_id="custom-token-id")
        assert token.token_id == "custom-token-id"

    def test_creates_token_with_branch_name(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        token = recorder.create_token(row.row_id, branch_name="path-a")
        assert token.branch_name == "path-a"

    def test_creates_token_with_fork_group_id(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        token = recorder.create_token(row.row_id, fork_group_id="fg-1")
        assert token.fork_group_id == "fg-1"

    def test_creates_token_with_join_group_id(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        token = recorder.create_token(row.row_id, join_group_id="jg-1")
        assert token.join_group_id == "jg-1"

    def test_created_at_is_set(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        token = recorder.create_token(row.row_id)
        assert token.created_at is not None

    def test_multiple_tokens_for_same_row(self):
        _db, recorder = _setup()
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "val"},
        )
        tokens = [recorder.create_token(row.row_id) for _ in range(3)]
        token_ids = [t.token_id for t in tokens]
        assert len(set(token_ids)) == 3
        assert all(t.row_id == row.row_id for t in tokens)


class TestForkToken:
    """Tests for TokenRecordingMixin.fork_token."""

    def test_creates_children_for_each_branch(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, _fork_group_id = recorder.fork_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            branches=["path-a", "path-b", "path-c"],
            run_id="run-1",
        )
        assert len(children) == 3
        branch_names = [c.branch_name for c in children]
        assert "path-a" in branch_names
        assert "path-b" in branch_names
        assert "path-c" in branch_names

    def test_children_share_fork_group_id(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, fork_group_id = recorder.fork_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            branches=["path-a", "path-b"],
            run_id="run-1",
        )
        assert fork_group_id is not None
        assert all(c.fork_group_id == fork_group_id for c in children)

    def test_children_linked_to_same_row(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, _fg = recorder.fork_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            branches=["path-a", "path-b"],
            run_id="run-1",
        )
        assert all(c.row_id == row.row_id for c in children)

    def test_records_parent_forked_outcome(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        _children, fork_group_id = recorder.fork_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            branches=["path-a", "path-b"],
            run_id="run-1",
        )
        outcome = recorder.get_token_outcome(token.token_id)
        assert outcome is not None
        assert outcome.outcome == RowOutcome.FORKED
        assert outcome.is_terminal is True
        assert outcome.fork_group_id == fork_group_id

    def test_empty_branches_raises_value_error(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        with pytest.raises(ValueError):
            recorder.fork_token(
                parent_token_id=token.token_id,
                row_id=row.row_id,
                branches=[],
                run_id="run-1",
            )

    def test_children_have_unique_token_ids(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, _fg = recorder.fork_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            branches=["path-a", "path-b", "path-c"],
            run_id="run-1",
        )
        token_ids = [c.token_id for c in children]
        assert len(set(token_ids)) == 3

    def test_fork_with_step_in_pipeline(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, _fg = recorder.fork_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            branches=["path-a", "path-b"],
            run_id="run-1",
            step_in_pipeline=3,
        )
        assert all(c.step_in_pipeline == 3 for c in children)


class TestCoalesceTokens:
    """Tests for TokenRecordingMixin.coalesce_tokens."""

    def test_creates_merged_token(self):
        _db, recorder = _setup()
        row, token_a = _make_row(recorder, row_index=0)
        token_b = recorder.create_token(row.row_id)
        merged = recorder.coalesce_tokens(
            parent_token_ids=[token_a.token_id, token_b.token_id],
            row_id=row.row_id,
        )
        assert merged.token_id is not None
        assert merged.row_id == row.row_id

    def test_merged_token_has_join_group_id(self):
        _db, recorder = _setup()
        row, token_a = _make_row(recorder, row_index=0)
        token_b = recorder.create_token(row.row_id)
        merged = recorder.coalesce_tokens(
            parent_token_ids=[token_a.token_id, token_b.token_id],
            row_id=row.row_id,
        )
        assert merged.join_group_id is not None

    def test_coalesce_three_tokens(self):
        _db, recorder = _setup()
        row, token_a = _make_row(recorder, row_index=0)
        token_b = recorder.create_token(row.row_id)
        token_c = recorder.create_token(row.row_id)
        merged = recorder.coalesce_tokens(
            parent_token_ids=[
                token_a.token_id,
                token_b.token_id,
                token_c.token_id,
            ],
            row_id=row.row_id,
        )
        assert merged.token_id is not None
        assert merged.join_group_id is not None

    def test_coalesce_with_step_in_pipeline(self):
        _db, recorder = _setup()
        row, token_a = _make_row(recorder, row_index=0)
        token_b = recorder.create_token(row.row_id)
        merged = recorder.coalesce_tokens(
            parent_token_ids=[token_a.token_id, token_b.token_id],
            row_id=row.row_id,
            step_in_pipeline=5,
        )
        assert merged.step_in_pipeline == 5


class TestExpandToken:
    """Tests for TokenRecordingMixin.expand_token."""

    def test_creates_n_children(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, expand_group_id = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=4,
            run_id="run-1",
        )
        assert len(children) == 4
        assert expand_group_id is not None

    def test_children_share_expand_group_id(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, expand_group_id = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=3,
            run_id="run-1",
        )
        assert all(c.expand_group_id == expand_group_id for c in children)

    def test_children_linked_to_same_row(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, _eg = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=2,
            run_id="run-1",
        )
        assert all(c.row_id == row.row_id for c in children)

    def test_records_parent_expanded_outcome(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        _children, expand_group_id = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=3,
            run_id="run-1",
        )
        outcome = recorder.get_token_outcome(token.token_id)
        assert outcome is not None
        assert outcome.outcome == RowOutcome.EXPANDED
        assert outcome.is_terminal is True
        assert outcome.expand_group_id == expand_group_id

    def test_count_less_than_one_raises_value_error(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        with pytest.raises(ValueError):
            recorder.expand_token(
                parent_token_id=token.token_id,
                row_id=row.row_id,
                count=0,
                run_id="run-1",
            )

    def test_count_negative_raises_value_error(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        with pytest.raises(ValueError):
            recorder.expand_token(
                parent_token_id=token.token_id,
                row_id=row.row_id,
                count=-1,
                run_id="run-1",
            )

    def test_record_parent_outcome_false_skips_outcome(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        _children, _eg = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=2,
            run_id="run-1",
            record_parent_outcome=False,
        )
        outcome = recorder.get_token_outcome(token.token_id)
        assert outcome is None

    def test_children_have_unique_token_ids(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, _eg = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=5,
            run_id="run-1",
        )
        token_ids = [c.token_id for c in children]
        assert len(set(token_ids)) == 5

    def test_expand_with_step_in_pipeline(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, _eg = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=2,
            run_id="run-1",
            step_in_pipeline=7,
        )
        assert all(c.step_in_pipeline == 7 for c in children)

    def test_expand_count_one(self):
        _db, recorder = _setup()
        row, token = _make_row(recorder)
        children, expand_group_id = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=1,
            run_id="run-1",
        )
        assert len(children) == 1
        assert expand_group_id is not None


class TestValidateOutcomeFields:
    """Tests for TokenRecordingMixin._validate_outcome_fields."""

    def _validate(self, recorder, outcome, **kwargs):
        defaults = {
            "sink_name": None,
            "batch_id": None,
            "fork_group_id": None,
            "join_group_id": None,
            "expand_group_id": None,
            "error_hash": None,
        }
        defaults.update(kwargs)
        recorder._validate_outcome_fields(outcome, **defaults)

    def test_completed_requires_sink_name(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.COMPLETED)

    def test_completed_accepts_sink_name(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.COMPLETED, sink_name="output")

    def test_routed_requires_sink_name(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.ROUTED)

    def test_routed_accepts_sink_name(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.ROUTED, sink_name="reject-sink")

    def test_forked_requires_fork_group_id(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.FORKED)

    def test_forked_accepts_fork_group_id(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.FORKED, fork_group_id="fg-1")

    def test_failed_requires_error_hash(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.FAILED)

    def test_failed_accepts_error_hash(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.FAILED, error_hash="abc123")

    def test_quarantined_requires_error_hash(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.QUARANTINED)

    def test_quarantined_accepts_error_hash(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.QUARANTINED, error_hash="abc123")

    def test_consumed_in_batch_requires_batch_id(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.CONSUMED_IN_BATCH)

    def test_consumed_in_batch_accepts_batch_id(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.CONSUMED_IN_BATCH, batch_id="batch-1")

    def test_coalesced_requires_join_group_id(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.COALESCED)

    def test_coalesced_accepts_join_group_id(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.COALESCED, join_group_id="jg-1")

    def test_expanded_requires_expand_group_id(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.EXPANDED)

    def test_expanded_accepts_expand_group_id(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.EXPANDED, expand_group_id="eg-1")

    def test_buffered_requires_batch_id(self):
        _db, recorder = _setup()
        with pytest.raises((ValueError, TypeError)):
            self._validate(recorder, RowOutcome.BUFFERED)

    def test_buffered_accepts_batch_id(self):
        _db, recorder = _setup()
        self._validate(recorder, RowOutcome.BUFFERED, batch_id="batch-1")


class TestRecordTokenOutcome:
    """Tests for TokenRecordingMixin.record_token_outcome."""

    def test_records_completed_outcome(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        outcome_id = recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        assert outcome_id is not None

    def test_returns_outcome_id_string(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        outcome_id = recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        assert isinstance(outcome_id, str)
        assert len(outcome_id) > 0

    def test_roundtrip_via_get_token_outcome(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        outcome_id = recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome_id == outcome_id
        assert fetched.token_id == token.token_id
        assert fetched.outcome == RowOutcome.COMPLETED
        assert fetched.sink_name == "output"
        assert fetched.is_terminal is True

    def test_records_failed_outcome_with_error_hash(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.FAILED,
            error_hash="err-hash-abc",
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.FAILED
        assert fetched.error_hash == "err-hash-abc"
        assert fetched.is_terminal is True

    def test_records_quarantined_outcome(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.QUARANTINED,
            error_hash="quarantine-hash",
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.QUARANTINED
        assert fetched.is_terminal is True

    def test_records_routed_outcome(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.ROUTED,
            sink_name="reject",
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.ROUTED
        assert fetched.sink_name == "reject"

    def test_records_consumed_in_batch_outcome(self):
        _db, recorder = _setup()
        batch_id = _make_batch(recorder, batch_id="batch-42")
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.CONSUMED_IN_BATCH,
            batch_id=batch_id,
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.CONSUMED_IN_BATCH
        assert fetched.batch_id == "batch-42"

    def test_records_buffered_outcome(self):
        _db, recorder = _setup()
        batch_id = _make_batch(recorder, batch_id="batch-pending")
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.BUFFERED,
            batch_id=batch_id,
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.BUFFERED
        assert fetched.is_terminal is False

    def test_records_outcome_with_context(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
            context={"reason": "all good"},
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.context_json is not None

    def test_recorded_at_is_set(self):
        _db, recorder = _setup()
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.recorded_at is not None


class TestGetTokenOutcome:
    """Tests for TokenRecordingMixin.get_token_outcome."""

    def test_returns_none_for_unknown_token(self):
        _db, recorder = _setup()
        result = recorder.get_token_outcome("nonexistent-token-id")
        assert result is None

    def test_returns_terminal_preferred_over_non_terminal(self):
        _db, recorder = _setup()
        batch_id = _make_batch(recorder)
        _row, token = _make_row(recorder)
        # Record non-terminal first
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.BUFFERED,
            batch_id=batch_id,
        )
        # Then record terminal
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.COMPLETED
        assert fetched.is_terminal is True

    def test_returns_non_terminal_when_no_terminal_exists(self):
        _db, recorder = _setup()
        batch_id = _make_batch(recorder)
        _row, token = _make_row(recorder)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.BUFFERED,
            batch_id=batch_id,
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.BUFFERED
        assert fetched.is_terminal is False

    def test_terminal_preferred_regardless_of_insertion_order(self):
        _db, recorder = _setup()
        batch_id = _make_batch(recorder)
        _row, token = _make_row(recorder)
        # Record terminal first
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        # Then record non-terminal
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.BUFFERED,
            batch_id=batch_id,
        )
        fetched = recorder.get_token_outcome(token.token_id)
        assert fetched is not None
        assert fetched.outcome == RowOutcome.COMPLETED
        assert fetched.is_terminal is True


class TestGetTokenOutcomesForRow:
    """Tests for TokenRecordingMixin.get_token_outcomes_for_row."""

    def test_returns_empty_list_when_no_outcomes(self):
        _db, recorder = _setup()
        row, _token = _make_row(recorder)
        outcomes = recorder.get_token_outcomes_for_row(run_id="run-1", row_id=row.row_id)
        assert outcomes == []

    def test_returns_all_outcomes_for_row(self):
        _db, recorder = _setup()
        row, token_a = _make_row(recorder, row_index=0)
        token_b = recorder.create_token(row.row_id)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token_a.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token_b.token_id,
            outcome=RowOutcome.ROUTED,
            sink_name="reject",
        )
        outcomes = recorder.get_token_outcomes_for_row(run_id="run-1", row_id=row.row_id)
        assert len(outcomes) == 2
        outcome_types = {o.outcome for o in outcomes}
        assert RowOutcome.COMPLETED in outcome_types
        assert RowOutcome.ROUTED in outcome_types

    def test_does_not_return_outcomes_from_other_rows(self):
        _db, recorder = _setup()
        row_a, token_a = _make_row(recorder, row_index=0)
        _row_b, token_b = _make_row(recorder, row_index=1)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token_a.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token_b.token_id,
            outcome=RowOutcome.FAILED,
            error_hash="err-hash",
        )
        outcomes_a = recorder.get_token_outcomes_for_row(run_id="run-1", row_id=row_a.row_id)
        assert len(outcomes_a) == 1
        assert outcomes_a[0].outcome == RowOutcome.COMPLETED

    def test_returns_empty_for_nonexistent_row(self):
        _db, recorder = _setup()
        outcomes = recorder.get_token_outcomes_for_row(run_id="run-1", row_id="no-such-row")
        assert outcomes == []

    def test_returns_multiple_outcomes_per_token(self):
        _db, recorder = _setup()
        batch_id = _make_batch(recorder)
        row, token = _make_row(recorder, row_index=0)
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.BUFFERED,
            batch_id=batch_id,
        )
        recorder.record_token_outcome(
            run_id="run-1",
            token_id=token.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        outcomes = recorder.get_token_outcomes_for_row(run_id="run-1", row_id=row.row_id)
        assert len(outcomes) == 2

    def test_does_not_return_outcomes_from_other_runs(self):
        _db_a, recorder_a = _setup(run_id="run-A")
        row_a, token_a = _make_row(recorder_a, run_id="run-A", row_index=0)
        recorder_a.record_token_outcome(
            run_id="run-A",
            token_id=token_a.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        # Query with a different run_id
        outcomes = recorder_a.get_token_outcomes_for_row(run_id="run-B", row_id=row_a.row_id)
        assert outcomes == []


# ===========================================================================
# Regression tests: P1-2026-02-14 cross-run contamination prevention
# ===========================================================================


def _setup_two_runs() -> tuple[LandscapeDB, LandscapeRecorder]:
    """Set up a shared database with two runs, each with a source and aggregation node."""
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)

    # Run A
    recorder.begin_run(config={}, canonical_version="v1", run_id="run-A")
    recorder.register_node(
        run_id="run-A",
        plugin_name="csv",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id="source-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.register_node(
        run_id="run-A",
        plugin_name="count_agg",
        node_type=NodeType.AGGREGATION,
        plugin_version="1.0",
        config={},
        node_id="agg-0",
        schema_config=_DYNAMIC_SCHEMA,
    )

    # Run B
    recorder.begin_run(config={}, canonical_version="v1", run_id="run-B")
    recorder.register_node(
        run_id="run-B",
        plugin_name="csv",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id="source-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.register_node(
        run_id="run-B",
        plugin_name="count_agg",
        node_type=NodeType.AGGREGATION,
        plugin_version="1.0",
        config={},
        node_id="agg-0",
        schema_config=_DYNAMIC_SCHEMA,
    )

    return db, recorder


class TestCrossRunContaminationPrevention:
    """P1-2026-02-14: Token lifecycle methods must crash on cross-run contamination.

    These tests verify that recording audit records under the wrong run_id
    raises AuditIntegrityError immediately, rather than silently corrupting
    the audit trail.
    """

    def test_record_token_outcome_rejects_wrong_run_id(self):
        """record_token_outcome must crash if token belongs to a different run."""
        _db, recorder = _setup_two_runs()

        # Create row and token in run-A
        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)

        # Attempt to record outcome under run-B -- must crash
        with pytest.raises(AuditIntegrityError, match="Cross-run contamination"):
            recorder.record_token_outcome(
                run_id="run-B",
                token_id=token_a.token_id,
                outcome=RowOutcome.COMPLETED,
                sink_name="output",
            )

    def test_record_token_outcome_accepts_correct_run_id(self):
        """record_token_outcome must succeed when run_id matches token ownership."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)

        # Recording with the correct run_id should succeed
        outcome_id = recorder.record_token_outcome(
            run_id="run-A",
            token_id=token_a.token_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )
        assert outcome_id is not None

    def test_fork_token_rejects_wrong_run_id(self):
        """fork_token must crash if parent token belongs to a different run."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)

        with pytest.raises(AuditIntegrityError, match="Cross-run contamination"):
            recorder.fork_token(
                parent_token_id=token_a.token_id,
                row_id=row_a.row_id,
                branches=["path-a", "path-b"],
                run_id="run-B",
            )

    def test_fork_token_rejects_wrong_row_id(self):
        """fork_token must crash if parent token belongs to a different row."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value-a"},
        )
        row_b = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=1,
            data={"col": "value-b"},
        )
        token_a = recorder.create_token(row_a.row_id)

        with pytest.raises(AuditIntegrityError, match="Cross-row lineage"):
            recorder.fork_token(
                parent_token_id=token_a.token_id,
                row_id=row_b.row_id,
                branches=["path-a"],
                run_id="run-A",
            )

    def test_fork_token_accepts_correct_ownership(self):
        """fork_token must succeed when run_id and row_id match parent token."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)

        children, fg = recorder.fork_token(
            parent_token_id=token_a.token_id,
            row_id=row_a.row_id,
            branches=["path-a", "path-b"],
            run_id="run-A",
        )
        assert len(children) == 2
        assert fg is not None

    def test_expand_token_rejects_wrong_run_id(self):
        """expand_token must crash if parent token belongs to a different run."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)

        with pytest.raises(AuditIntegrityError, match="Cross-run contamination"):
            recorder.expand_token(
                parent_token_id=token_a.token_id,
                row_id=row_a.row_id,
                count=3,
                run_id="run-B",
            )

    def test_expand_token_rejects_wrong_row_id(self):
        """expand_token must crash if parent token belongs to a different row."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value-a"},
        )
        row_b = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=1,
            data={"col": "value-b"},
        )
        token_a = recorder.create_token(row_a.row_id)

        with pytest.raises(AuditIntegrityError, match="Cross-row lineage"):
            recorder.expand_token(
                parent_token_id=token_a.token_id,
                row_id=row_b.row_id,
                count=2,
                run_id="run-A",
            )

    def test_expand_token_accepts_correct_ownership(self):
        """expand_token must succeed when run_id and row_id match parent token."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)

        children, eg = recorder.expand_token(
            parent_token_id=token_a.token_id,
            row_id=row_a.row_id,
            count=3,
            run_id="run-A",
        )
        assert len(children) == 3
        assert eg is not None

    def test_coalesce_tokens_rejects_cross_run_parents(self):
        """coalesce_tokens must crash if parent tokens belong to different runs."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value-a"},
        )
        token_a = recorder.create_token(row_a.row_id)

        row_b = recorder.create_row(
            run_id="run-B",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value-b"},
        )
        token_b = recorder.create_token(row_b.row_id)

        # token_a belongs to run-A, token_b belongs to run-B
        # coalesce requires row_id match, so this will fail on row ownership first
        with pytest.raises(AuditIntegrityError):
            recorder.coalesce_tokens(
                parent_token_ids=[token_a.token_id, token_b.token_id],
                row_id=row_a.row_id,
            )

    def test_coalesce_tokens_rejects_wrong_row_id(self):
        """coalesce_tokens must crash if parent token belongs to a different row."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value-a"},
        )
        row_b = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=1,
            data={"col": "value-b"},
        )
        token_a = recorder.create_token(row_a.row_id)
        token_b = recorder.create_token(row_a.row_id)

        # Both tokens belong to row_a, but we say row_b
        with pytest.raises(AuditIntegrityError, match="Cross-row lineage"):
            recorder.coalesce_tokens(
                parent_token_ids=[token_a.token_id, token_b.token_id],
                row_id=row_b.row_id,
            )

    def test_coalesce_tokens_accepts_correct_ownership(self):
        """coalesce_tokens must succeed when all parents belong to the same row/run."""
        _db, recorder = _setup_two_runs()

        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)
        token_b = recorder.create_token(row_a.row_id)

        merged = recorder.coalesce_tokens(
            parent_token_ids=[token_a.token_id, token_b.token_id],
            row_id=row_a.row_id,
        )
        assert merged.token_id is not None
        assert merged.run_id == "run-A"


class TestTokenRunIdConsistency:
    """P1-2026-02-14: Tokens must store run_id and derive it from their row.

    These tests verify that create_token correctly derives run_id from the
    row record and stores it, ensuring schema-level enforcement via composite FKs.
    """

    def test_create_token_stores_run_id(self):
        """create_token must derive and store run_id from the row's run."""
        _db, recorder = _setup(run_id="run-1")
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token = recorder.create_token(row.row_id)
        assert token.run_id == "run-1"

    def test_create_token_for_nonexistent_row_crashes(self):
        """create_token must crash if the row_id does not exist (Tier 1 violation)."""
        _db, recorder = _setup(run_id="run-1")
        with pytest.raises(AuditIntegrityError, match="does not exist"):
            recorder.create_token("nonexistent-row-id")

    def test_fork_children_have_run_id(self):
        """Forked child tokens must inherit run_id from parent."""
        _db, recorder = _setup(run_id="run-1")
        row, token = _make_row(recorder)
        children, _fg = recorder.fork_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            branches=["path-a", "path-b"],
            run_id="run-1",
        )
        assert all(c.run_id == "run-1" for c in children)

    def test_expand_children_have_run_id(self):
        """Expanded child tokens must inherit run_id from parent."""
        _db, recorder = _setup(run_id="run-1")
        row, token = _make_row(recorder)
        children, _eg = recorder.expand_token(
            parent_token_id=token.token_id,
            row_id=row.row_id,
            count=3,
            run_id="run-1",
        )
        assert all(c.run_id == "run-1" for c in children)

    def test_coalesced_token_has_run_id(self):
        """Coalesced token must inherit run_id from parents."""
        _db, recorder = _setup(run_id="run-1")
        row, token_a = _make_row(recorder, row_index=0)
        token_b = recorder.create_token(row.row_id)
        merged = recorder.coalesce_tokens(
            parent_token_ids=[token_a.token_id, token_b.token_id],
            row_id=row.row_id,
        )
        assert merged.run_id == "run-1"

    def test_token_roundtrip_preserves_run_id(self):
        """Token run_id should survive DB roundtrip via get_token."""
        _db, recorder = _setup(run_id="run-1")
        row = recorder.create_row(
            run_id="run-1",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token = recorder.create_token(row.row_id)
        fetched = recorder.get_token(token.token_id)
        assert fetched is not None
        assert fetched.run_id == "run-1"

    def test_schema_composite_fk_prevents_cross_run_outcome(self):
        """Schema composite FK on token_outcomes must reject mismatched (token_id, run_id).

        Even if the application-level check were bypassed, the database constraint
        should reject the insert.
        """
        from sqlalchemy.exc import IntegrityError

        from elspeth.core.landscape._helpers import generate_id, now
        from elspeth.core.landscape.schema import token_outcomes_table

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        # Set up run-A with row + token
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-A")
        recorder.register_node(
            run_id="run-A",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        row_a = recorder.create_row(
            run_id="run-A",
            source_node_id="source-0",
            row_index=0,
            data={"col": "value"},
        )
        token_a = recorder.create_token(row_a.row_id)

        # Set up run-B (but don't create any tokens in it)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-B")
        recorder.register_node(
            run_id="run-B",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )

        # Try to insert directly into token_outcomes with mismatched (token_id, run_id)
        # token_a belongs to run-A, but we try to record under run-B
        # The composite FK should reject this
        with pytest.raises(IntegrityError), db.connection() as conn:
            conn.execute(
                token_outcomes_table.insert().values(
                    outcome_id=f"out_{generate_id()[:12]}",
                    run_id="run-B",
                    token_id=token_a.token_id,
                    outcome=RowOutcome.COMPLETED.value,
                    is_terminal=1,
                    recorded_at=now(),
                    sink_name="output",
                )
            )
