from __future__ import annotations

import pytest

from elspeth.contracts import BatchStatus, NodeType, TriggerType
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
        plugin_name="aggregator",
        node_type=NodeType.AGGREGATION,
        plugin_version="1.0",
        config={},
        node_id="agg-1",
        schema_config=_DYNAMIC_SCHEMA,
    )
    return db, recorder


def _setup_with_token(
    *, run_id: str = "run-1",
) -> tuple[LandscapeDB, LandscapeRecorder]:
    db, recorder = _setup(run_id=run_id)
    recorder.create_row(run_id, "source-0", 0, {"name": "test"}, row_id="row-1")
    recorder.create_token("row-1", token_id="tok-1")
    recorder.create_row(run_id, "source-0", 1, {"name": "test2"}, row_id="row-2")
    recorder.create_token("row-2", token_id="tok-2")
    return db, recorder


def _setup_with_sink(
    *, run_id: str = "run-1",
) -> tuple[LandscapeDB, LandscapeRecorder]:
    """Setup with token and a sink node for artifact tests."""
    db, recorder = _setup_with_token(run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="csv_sink",
        node_type=NodeType.SINK,
        plugin_version="1.0",
        config={},
        node_id="sink-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    return db, recorder


# ---------------------------------------------------------------------------
# create_batch
# ---------------------------------------------------------------------------


class TestCreateBatch:
    """Tests for BatchRecordingMixin.create_batch."""

    def test_creates_batch_with_draft_status(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.status == BatchStatus.DRAFT

    def test_generates_batch_id_when_not_provided(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.batch_id is not None
        assert isinstance(batch.batch_id, str)
        assert len(batch.batch_id) > 0

    def test_uses_provided_batch_id(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1", batch_id="my-batch-42")

        assert batch.batch_id == "my-batch-42"

    def test_stores_run_id_and_node_id(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.run_id == "run-1"
        assert batch.aggregation_node_id == "agg-1"

    def test_default_attempt_is_zero(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.attempt == 0

    def test_explicit_attempt_number(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1", attempt=3)

        assert batch.attempt == 3

    def test_created_at_is_set(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.created_at is not None

    def test_trigger_fields_initially_none(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.trigger_type is None
        assert batch.trigger_reason is None

    def test_completed_at_initially_none(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.completed_at is None

    def test_aggregation_state_id_initially_none(self):
        _db, recorder = _setup()
        batch = recorder.create_batch("run-1", "agg-1")

        assert batch.aggregation_state_id is None

    def test_multiple_batches_get_unique_ids(self):
        _db, recorder = _setup()
        batch_a = recorder.create_batch("run-1", "agg-1")
        batch_b = recorder.create_batch("run-1", "agg-1")

        assert batch_a.batch_id != batch_b.batch_id


# ---------------------------------------------------------------------------
# add_batch_member / get_batch_members
# ---------------------------------------------------------------------------


class TestAddBatchMember:
    """Tests for BatchRecordingMixin.add_batch_member."""

    def test_adds_member_to_batch(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        member = recorder.add_batch_member("b-1", "tok-1", ordinal=0)

        assert member.batch_id == "b-1"
        assert member.token_id == "tok-1"
        assert member.ordinal == 0

    def test_roundtrip_via_get_batch_members(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.add_batch_member("b-1", "tok-1", ordinal=0)
        recorder.add_batch_member("b-1", "tok-2", ordinal=1)

        members = recorder.get_batch_members("b-1")

        assert len(members) == 2
        assert members[0].token_id == "tok-1"
        assert members[0].ordinal == 0
        assert members[1].token_id == "tok-2"
        assert members[1].ordinal == 1

    def test_multiple_members_different_ordinals(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.add_batch_member("b-1", "tok-1", ordinal=5)
        recorder.add_batch_member("b-1", "tok-2", ordinal=2)

        members = recorder.get_batch_members("b-1")

        assert len(members) == 2
        # Should be ordered by ordinal
        assert members[0].ordinal == 2
        assert members[1].ordinal == 5


# ---------------------------------------------------------------------------
# update_batch_status
# ---------------------------------------------------------------------------


class TestUpdateBatchStatus:
    """Tests for BatchRecordingMixin.update_batch_status."""

    def test_updates_status_to_executing(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        recorder.update_batch_status("b-1", BatchStatus.EXECUTING)

        updated = recorder.get_batch("b-1")
        assert updated.status == BatchStatus.EXECUTING

    def test_sets_completed_at_for_completed(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        recorder.update_batch_status("b-1", BatchStatus.COMPLETED)

        updated = recorder.get_batch("b-1")
        assert updated.status == BatchStatus.COMPLETED
        assert updated.completed_at is not None

    def test_sets_completed_at_for_failed(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        recorder.update_batch_status("b-1", BatchStatus.FAILED)

        updated = recorder.get_batch("b-1")
        assert updated.status == BatchStatus.FAILED
        assert updated.completed_at is not None

    def test_does_not_set_completed_at_for_executing(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        recorder.update_batch_status("b-1", BatchStatus.EXECUTING)

        updated = recorder.get_batch("b-1")
        assert updated.completed_at is None

    def test_sets_trigger_type(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        recorder.update_batch_status(
            "b-1", BatchStatus.COMPLETED, trigger_type=TriggerType.COUNT,
        )

        updated = recorder.get_batch("b-1")
        assert updated.trigger_type == TriggerType.COUNT

    def test_sets_trigger_reason(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        recorder.update_batch_status(
            "b-1",
            BatchStatus.COMPLETED,
            trigger_type=TriggerType.TIMEOUT,
            trigger_reason="30s elapsed",
        )

        updated = recorder.get_batch("b-1")
        assert updated.trigger_type == TriggerType.TIMEOUT
        assert updated.trigger_reason == "30s elapsed"

    def test_sets_state_id(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.begin_node_state(
            "tok-1", "agg-1", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        recorder.update_batch_status(
            "b-1", BatchStatus.COMPLETED, state_id="state-1",
        )

        updated = recorder.get_batch("b-1")
        assert updated.aggregation_state_id == "state-1"


# ---------------------------------------------------------------------------
# complete_batch
# ---------------------------------------------------------------------------


class TestCompleteBatch:
    """Tests for BatchRecordingMixin.complete_batch."""

    def test_returns_updated_batch(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        result = recorder.complete_batch("b-1", BatchStatus.COMPLETED)

        assert result.batch_id == "b-1"
        assert result.status == BatchStatus.COMPLETED

    def test_completed_at_is_populated(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        result = recorder.complete_batch("b-1", BatchStatus.COMPLETED)

        assert result.completed_at is not None

    def test_complete_with_trigger_info(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        result = recorder.complete_batch(
            "b-1",
            BatchStatus.COMPLETED,
            trigger_type=TriggerType.COUNT,
            trigger_reason="reached 10 rows",
        )

        assert result.trigger_type == TriggerType.COUNT
        assert result.trigger_reason == "reached 10 rows"

    def test_complete_as_failed(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        result = recorder.complete_batch("b-1", BatchStatus.FAILED)

        assert result.status == BatchStatus.FAILED
        assert result.completed_at is not None

    def test_complete_with_state_id(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.begin_node_state(
            "tok-1", "agg-1", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        result = recorder.complete_batch(
            "b-1", BatchStatus.COMPLETED, state_id="state-1",
        )

        assert result.aggregation_state_id == "state-1"

    def test_complete_batch_persists_to_database(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.complete_batch(
            "b-1",
            BatchStatus.COMPLETED,
            trigger_type=TriggerType.END_OF_SOURCE,
            trigger_reason="source exhausted",
        )

        fetched = recorder.get_batch("b-1")
        assert fetched.status == BatchStatus.COMPLETED
        assert fetched.trigger_type == TriggerType.END_OF_SOURCE
        assert fetched.trigger_reason == "source exhausted"


# ---------------------------------------------------------------------------
# get_batch
# ---------------------------------------------------------------------------


class TestGetBatch:
    """Tests for BatchRecordingMixin.get_batch."""

    def test_roundtrip(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        fetched = recorder.get_batch("b-1")

        assert fetched is not None
        assert fetched.batch_id == "b-1"
        assert fetched.run_id == "run-1"
        assert fetched.aggregation_node_id == "agg-1"
        assert fetched.status == BatchStatus.DRAFT

    def test_returns_none_for_unknown_id(self):
        _db, recorder = _setup()

        result = recorder.get_batch("nonexistent-batch")

        assert result is None

    def test_reflects_status_updates(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.update_batch_status("b-1", BatchStatus.EXECUTING)

        fetched = recorder.get_batch("b-1")

        assert fetched.status == BatchStatus.EXECUTING


# ---------------------------------------------------------------------------
# get_batches
# ---------------------------------------------------------------------------


class TestGetBatches:
    """Tests for BatchRecordingMixin.get_batches."""

    def test_lists_all_batches_for_run(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.create_batch("run-1", "agg-1", batch_id="b-2")

        batches = recorder.get_batches("run-1")

        assert len(batches) == 2
        batch_ids = {b.batch_id for b in batches}
        assert batch_ids == {"b-1", "b-2"}

    def test_empty_for_unknown_run(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")

        batches = recorder.get_batches("run-unknown")

        assert batches == []

    def test_filter_by_status(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.create_batch("run-1", "agg-1", batch_id="b-2")
        recorder.update_batch_status("b-2", BatchStatus.COMPLETED)

        draft_batches = recorder.get_batches("run-1", status=BatchStatus.DRAFT)
        completed_batches = recorder.get_batches(
            "run-1", status=BatchStatus.COMPLETED,
        )

        assert len(draft_batches) == 1
        assert draft_batches[0].batch_id == "b-1"
        assert len(completed_batches) == 1
        assert completed_batches[0].batch_id == "b-2"

    def test_filter_by_node_id(self):
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="aggregator2",
            node_type=NodeType.AGGREGATION,
            plugin_version="1.0",
            config={},
            node_id="agg-2",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.create_batch("run-1", "agg-2", batch_id="b-2")

        agg1_batches = recorder.get_batches("run-1", node_id="agg-1")
        agg2_batches = recorder.get_batches("run-1", node_id="agg-2")

        assert len(agg1_batches) == 1
        assert agg1_batches[0].batch_id == "b-1"
        assert len(agg2_batches) == 1
        assert agg2_batches[0].batch_id == "b-2"

    def test_filter_by_status_and_node_id(self):
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="aggregator2",
            node_type=NodeType.AGGREGATION,
            plugin_version="1.0",
            config={},
            node_id="agg-2",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.create_batch("run-1", "agg-1", batch_id="b-2")
        recorder.create_batch("run-1", "agg-2", batch_id="b-3")
        recorder.update_batch_status("b-2", BatchStatus.COMPLETED)

        result = recorder.get_batches(
            "run-1", status=BatchStatus.DRAFT, node_id="agg-1",
        )

        assert len(result) == 1
        assert result[0].batch_id == "b-1"

    def test_does_not_return_batches_from_other_runs(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="aggregator",
            node_type=NodeType.AGGREGATION,
            plugin_version="1.0",
            config={},
            node_id="agg-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-2")
        recorder.register_node(
            run_id="run-2",
            plugin_name="aggregator",
            node_type=NodeType.AGGREGATION,
            plugin_version="1.0",
            config={},
            node_id="agg-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.create_batch("run-2", "agg-1", batch_id="b-2")

        run1_batches = recorder.get_batches("run-1")
        run2_batches = recorder.get_batches("run-2")

        assert len(run1_batches) == 1
        assert run1_batches[0].batch_id == "b-1"
        assert len(run2_batches) == 1
        assert run2_batches[0].batch_id == "b-2"


# ---------------------------------------------------------------------------
# get_incomplete_batches
# ---------------------------------------------------------------------------


class TestGetIncompleteBatches:
    """Tests for BatchRecordingMixin.get_incomplete_batches."""

    def test_returns_draft_batches(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-draft")

        incomplete = recorder.get_incomplete_batches("run-1")

        assert len(incomplete) == 1
        assert incomplete[0].batch_id == "b-draft"

    def test_returns_executing_batches(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-exec")
        recorder.update_batch_status("b-exec", BatchStatus.EXECUTING)

        incomplete = recorder.get_incomplete_batches("run-1")

        assert len(incomplete) == 1
        assert incomplete[0].batch_id == "b-exec"
        assert incomplete[0].status == BatchStatus.EXECUTING

    def test_returns_failed_batches(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-fail")
        recorder.update_batch_status("b-fail", BatchStatus.FAILED)

        incomplete = recorder.get_incomplete_batches("run-1")

        assert len(incomplete) == 1
        assert incomplete[0].batch_id == "b-fail"
        assert incomplete[0].status == BatchStatus.FAILED

    def test_excludes_completed_batches(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-done")
        recorder.update_batch_status("b-done", BatchStatus.COMPLETED)

        incomplete = recorder.get_incomplete_batches("run-1")

        assert len(incomplete) == 0

    def test_mixed_statuses(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-draft")
        recorder.create_batch("run-1", "agg-1", batch_id="b-exec")
        recorder.create_batch("run-1", "agg-1", batch_id="b-fail")
        recorder.create_batch("run-1", "agg-1", batch_id="b-done")
        recorder.update_batch_status("b-exec", BatchStatus.EXECUTING)
        recorder.update_batch_status("b-fail", BatchStatus.FAILED)
        recorder.update_batch_status("b-done", BatchStatus.COMPLETED)

        incomplete = recorder.get_incomplete_batches("run-1")

        incomplete_ids = {b.batch_id for b in incomplete}
        assert incomplete_ids == {"b-draft", "b-exec", "b-fail"}

    def test_empty_for_run_with_no_batches(self):
        _db, recorder = _setup()

        incomplete = recorder.get_incomplete_batches("run-1")

        assert incomplete == []


# ---------------------------------------------------------------------------
# get_batch_members (ordering)
# ---------------------------------------------------------------------------


class TestGetBatchMembers:
    """Tests for BatchRecordingMixin.get_batch_members ordering."""

    def test_returns_members_ordered_by_ordinal(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.add_batch_member("b-1", "tok-2", ordinal=10)
        recorder.add_batch_member("b-1", "tok-1", ordinal=5)

        members = recorder.get_batch_members("b-1")

        assert len(members) == 2
        assert members[0].token_id == "tok-1"
        assert members[0].ordinal == 5
        assert members[1].token_id == "tok-2"
        assert members[1].ordinal == 10

    def test_empty_for_batch_with_no_members(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-empty")

        members = recorder.get_batch_members("b-empty")

        assert members == []

    def test_members_only_from_specified_batch(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.create_batch("run-1", "agg-1", batch_id="b-2")
        recorder.add_batch_member("b-1", "tok-1", ordinal=0)
        recorder.add_batch_member("b-2", "tok-2", ordinal=0)

        members_b1 = recorder.get_batch_members("b-1")
        members_b2 = recorder.get_batch_members("b-2")

        assert len(members_b1) == 1
        assert members_b1[0].token_id == "tok-1"
        assert len(members_b2) == 1
        assert members_b2[0].token_id == "tok-2"


# ---------------------------------------------------------------------------
# get_all_batch_members_for_run
# ---------------------------------------------------------------------------


class TestGetAllBatchMembersForRun:
    """Tests for BatchRecordingMixin.get_all_batch_members_for_run."""

    def test_returns_all_members_across_batches(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.create_batch("run-1", "agg-1", batch_id="b-2")
        recorder.add_batch_member("b-1", "tok-1", ordinal=0)
        recorder.add_batch_member("b-2", "tok-2", ordinal=0)

        all_members = recorder.get_all_batch_members_for_run("run-1")

        assert len(all_members) == 2
        token_ids = {m.token_id for m in all_members}
        assert token_ids == {"tok-1", "tok-2"}

    def test_empty_for_run_with_no_batch_members(self):
        _db, recorder = _setup()

        all_members = recorder.get_all_batch_members_for_run("run-1")

        assert all_members == []

    def test_does_not_include_members_from_other_runs(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        # Run 1
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="aggregator",
            node_type=NodeType.AGGREGATION,
            plugin_version="1.0",
            config={},
            node_id="agg-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")
        recorder.create_batch("run-1", "agg-1", batch_id="b-1")
        recorder.add_batch_member("b-1", "tok-1", ordinal=0)

        # Run 2
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-2")
        recorder.register_node(
            run_id="run-2",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-2",
            plugin_name="aggregator",
            node_type=NodeType.AGGREGATION,
            plugin_version="1.0",
            config={},
            node_id="agg-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-2", "source-0", 0, {"x": 2}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.create_batch("run-2", "agg-1", batch_id="b-2")
        recorder.add_batch_member("b-2", "tok-2", ordinal=0)

        run1_members = recorder.get_all_batch_members_for_run("run-1")
        run2_members = recorder.get_all_batch_members_for_run("run-2")

        assert len(run1_members) == 1
        assert run1_members[0].token_id == "tok-1"
        assert len(run2_members) == 1
        assert run2_members[0].token_id == "tok-2"


# ---------------------------------------------------------------------------
# retry_batch
# ---------------------------------------------------------------------------


class TestRetryBatch:
    """Tests for BatchRecordingMixin.retry_batch."""

    def test_creates_new_batch_with_incremented_attempt(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-orig")
        recorder.add_batch_member("b-orig", "tok-1", ordinal=0)
        recorder.add_batch_member("b-orig", "tok-2", ordinal=1)
        recorder.update_batch_status("b-orig", BatchStatus.FAILED)

        retried = recorder.retry_batch("b-orig")

        assert retried.batch_id != "b-orig"
        assert retried.attempt == 1
        assert retried.run_id == "run-1"
        assert retried.aggregation_node_id == "agg-1"
        assert retried.status == BatchStatus.DRAFT

    def test_copies_members_to_new_batch(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-orig")
        recorder.add_batch_member("b-orig", "tok-1", ordinal=0)
        recorder.add_batch_member("b-orig", "tok-2", ordinal=1)
        recorder.update_batch_status("b-orig", BatchStatus.FAILED)

        retried = recorder.retry_batch("b-orig")

        members = recorder.get_batch_members(retried.batch_id)
        assert len(members) == 2
        token_ids = [m.token_id for m in members]
        assert "tok-1" in token_ids
        assert "tok-2" in token_ids

    def test_raises_for_non_failed_batch_draft(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-draft")

        with pytest.raises(ValueError):
            recorder.retry_batch("b-draft")

    def test_raises_for_non_failed_batch_completed(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-done")
        recorder.update_batch_status("b-done", BatchStatus.COMPLETED)

        with pytest.raises(ValueError):
            recorder.retry_batch("b-done")

    def test_raises_for_non_failed_batch_executing(self):
        _db, recorder = _setup()
        recorder.create_batch("run-1", "agg-1", batch_id="b-exec")
        recorder.update_batch_status("b-exec", BatchStatus.EXECUTING)

        with pytest.raises(ValueError):
            recorder.retry_batch("b-exec")

    def test_raises_for_nonexistent_batch(self):
        _db, recorder = _setup()

        with pytest.raises(ValueError):
            recorder.retry_batch("nonexistent")

    def test_retry_increments_from_previous_attempt(self):
        _db, recorder = _setup_with_token()
        recorder.create_batch("run-1", "agg-1", batch_id="b-orig", attempt=0)
        recorder.add_batch_member("b-orig", "tok-1", ordinal=0)
        recorder.update_batch_status("b-orig", BatchStatus.FAILED)

        retry1 = recorder.retry_batch("b-orig")
        assert retry1.attempt == 1

        # Fail the retry and retry again
        recorder.update_batch_status(retry1.batch_id, BatchStatus.FAILED)
        retry2 = recorder.retry_batch(retry1.batch_id)
        assert retry2.attempt == 2


# ---------------------------------------------------------------------------
# register_artifact
# ---------------------------------------------------------------------------


class TestRegisterArtifact:
    """Tests for BatchRecordingMixin.register_artifact."""

    def test_creates_artifact_with_generated_id(self):
        _db, recorder = _setup_with_sink()
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        artifact = recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/output/result.csv",
            content_hash="sha256:abc123",
            size_bytes=1024,
        )

        assert artifact.artifact_id is not None
        assert isinstance(artifact.artifact_id, str)
        assert len(artifact.artifact_id) > 0

    def test_uses_provided_artifact_id(self):
        _db, recorder = _setup_with_sink()
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        artifact = recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/output/result.csv",
            content_hash="sha256:abc123",
            size_bytes=1024,
            artifact_id="art-42",
        )

        assert artifact.artifact_id == "art-42"

    def test_stores_all_fields(self):
        _db, recorder = _setup_with_sink()
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        artifact = recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="json",
            path="/output/data.json",
            content_hash="sha256:def456",
            size_bytes=2048,
        )

        assert artifact.run_id == "run-1"
        assert artifact.produced_by_state_id == "state-1"
        assert artifact.sink_node_id == "sink-0"
        assert artifact.artifact_type == "json"
        assert artifact.path_or_uri == "/output/data.json"
        assert artifact.content_hash == "sha256:def456"
        assert artifact.size_bytes == 2048

    def test_created_at_is_set(self):
        _db, recorder = _setup_with_sink()
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        artifact = recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/output/result.csv",
            content_hash="sha256:abc",
            size_bytes=512,
        )

        assert artifact.created_at is not None

    def test_idempotency_key_default_none(self):
        _db, recorder = _setup_with_sink()
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        artifact = recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/output/result.csv",
            content_hash="sha256:abc",
            size_bytes=512,
        )

        assert artifact.idempotency_key is None

    def test_idempotency_key_explicit(self):
        _db, recorder = _setup_with_sink()
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )

        artifact = recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/output/result.csv",
            content_hash="sha256:abc",
            size_bytes=512,
            idempotency_key="idem-key-1",
        )

        assert artifact.idempotency_key == "idem-key-1"


# ---------------------------------------------------------------------------
# get_artifacts
# ---------------------------------------------------------------------------


class TestGetArtifacts:
    """Tests for BatchRecordingMixin.get_artifacts."""

    def test_lists_all_artifacts_for_run(self):
        _db, recorder = _setup_with_sink()
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )
        recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/output/a.csv",
            content_hash="sha256:a",
            size_bytes=100,
            artifact_id="art-1",
        )
        recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="json",
            path="/output/b.json",
            content_hash="sha256:b",
            size_bytes=200,
            artifact_id="art-2",
        )

        artifacts = recorder.get_artifacts("run-1")

        assert len(artifacts) == 2
        art_ids = {a.artifact_id for a in artifacts}
        assert art_ids == {"art-1", "art-2"}

    def test_empty_for_run_with_no_artifacts(self):
        _db, recorder = _setup()

        artifacts = recorder.get_artifacts("run-1")

        assert artifacts == []

    def test_filter_by_sink_node_id(self):
        _db, recorder = _setup_with_sink()
        recorder.register_node(
            run_id="run-1",
            plugin_name="json_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            node_id="sink-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"data": "test"}, state_id="state-1",
        )
        recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/output/a.csv",
            content_hash="sha256:a",
            size_bytes=100,
            artifact_id="art-csv",
        )
        recorder.register_artifact(
            run_id="run-1",
            state_id="state-1",
            sink_node_id="sink-1",
            artifact_type="json",
            path="/output/b.json",
            content_hash="sha256:b",
            size_bytes=200,
            artifact_id="art-json",
        )

        csv_artifacts = recorder.get_artifacts("run-1", sink_node_id="sink-0")
        json_artifacts = recorder.get_artifacts("run-1", sink_node_id="sink-1")

        assert len(csv_artifacts) == 1
        assert csv_artifacts[0].artifact_id == "art-csv"
        assert len(json_artifacts) == 1
        assert json_artifacts[0].artifact_id == "art-json"

    def test_does_not_return_artifacts_from_other_runs(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        # Run 1
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            node_id="sink-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")
        recorder.begin_node_state(
            "tok-1", "source-0", "run-1", 0, {"x": 1}, state_id="s-1",
        )
        recorder.register_artifact(
            run_id="run-1",
            state_id="s-1",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/r1.csv",
            content_hash="sha256:r1",
            size_bytes=100,
            artifact_id="art-r1",
        )

        # Run 2
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-2")
        recorder.register_node(
            run_id="run-2",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-2",
            plugin_name="csv_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            node_id="sink-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-2", "source-0", 0, {"x": 2}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.begin_node_state(
            "tok-2", "source-0", "run-2", 0, {"x": 2}, state_id="s-2",
        )
        recorder.register_artifact(
            run_id="run-2",
            state_id="s-2",
            sink_node_id="sink-0",
            artifact_type="csv",
            path="/r2.csv",
            content_hash="sha256:r2",
            size_bytes=200,
            artifact_id="art-r2",
        )

        run1_arts = recorder.get_artifacts("run-1")
        run2_arts = recorder.get_artifacts("run-2")

        assert len(run1_arts) == 1
        assert run1_arts[0].artifact_id == "art-r1"
        assert len(run2_arts) == 1
        assert run2_arts[0].artifact_id == "art-r2"
