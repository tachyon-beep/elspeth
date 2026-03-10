# tests/unit/core/landscape/test_where_exactness_execution.py
"""WHERE clause exactness tests for ExecutionRepository query methods.

These tests verify that SQL queries use ``==`` (exact match) rather than
``>=`` / ``<=`` (range) operators.  The multi-run fixture creates three
runs with lexicographically ordered IDs (run-A < run-B < run-C) so that
an inequality operator would silently include data from adjacent runs.

Targets methods accessed through ``recorder`` that live in
``ExecutionRepository`` and ``QueryRepository``:

- get_node_state (single state by ID)
- get_node_states_for_token (token-scoped states)
- get_calls (state-scoped calls — "get_calls_for_state")
- find_call_by_request_hash (run+hash scoped — LLM cache safety)
- get_routing_events (state-scoped — "get_routing_events_for_state")
- get_batch (single batch by ID)
- get_batch_members (batch-scoped members)
- get_operation / get_operation_calls (operation-scoped)

The fixture lives in ``tests/fixtures/multi_run.py`` and is imported as
a pytest fixture via the ``multi_run_landscape`` name.
"""

from __future__ import annotations

from elspeth.contracts import CallType
from tests.fixtures.multi_run import MultiRunFixture

pytest_plugins = ["tests.fixtures.multi_run"]


class TestGetNodeStateWhereExactness:
    """get_node_state must return only the targeted state, not neighbours."""

    def test_returns_only_target_state(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")
        target_state_id = target.tokens[0].state_id  # st-B-0

        state = fix.recorder.get_node_state(target_state_id)

        assert state is not None
        assert state.state_id == target_state_id

    def test_does_not_return_adjacent_state(self, multi_run_landscape: MultiRunFixture) -> None:
        """If == mutated to >=, querying st-B-0 could also match st-B-1 or st-C-*."""
        fix = multi_run_landscape
        target_state_id = fix.run("B").tokens[0].state_id

        state = fix.recorder.get_node_state(target_state_id)

        assert state is not None
        # Verify it is exactly the target, not a neighbour
        assert state.state_id == target_state_id
        assert state.state_id != fix.run("A").tokens[0].state_id
        assert state.state_id != fix.run("C").tokens[0].state_id

    def test_returns_none_for_nonexistent(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        assert fix.recorder.get_node_state("st-NONEXISTENT") is None


class TestGetNodeStatesForTokenWhereExactness:
    """get_node_states_for_token must return only states for the target token."""

    def test_returns_only_target_token_states(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")
        target_token = target.tokens[0]

        states = fix.recorder.get_node_states_for_token(target_token.token_id)

        assert len(states) == 1
        assert states[0].state_id == target_token.state_id

    def test_excludes_other_runs_tokens(self, multi_run_landscape: MultiRunFixture) -> None:
        """tok-B-0 < tok-C-0 — a >= mutation would include run-C states."""
        fix = multi_run_landscape
        states_b0 = fix.recorder.get_node_states_for_token(fix.run("B").tokens[0].token_id)
        states_c0 = fix.recorder.get_node_states_for_token(fix.run("C").tokens[0].token_id)

        b0_ids = {s.state_id for s in states_b0}
        c0_ids = {s.state_id for s in states_c0}

        assert b0_ids.isdisjoint(c0_ids)

    def test_excludes_same_run_other_token(self, multi_run_landscape: MultiRunFixture) -> None:
        """tok-B-0 < tok-B-1 — a >= mutation would include tok-B-1's states."""
        fix = multi_run_landscape
        target = fix.run("B")
        states_0 = fix.recorder.get_node_states_for_token(target.tokens[0].token_id)
        states_1 = fix.recorder.get_node_states_for_token(target.tokens[1].token_id)

        ids_0 = {s.state_id for s in states_0}
        ids_1 = {s.state_id for s in states_1}

        assert ids_0.isdisjoint(ids_1)


class TestGetCallsWhereExactness:
    """get_calls (state-scoped) must return only calls for the target state."""

    def test_returns_only_target_state_calls(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")
        target_state_id = target.tokens[0].state_id  # st-B-0 has a call

        calls = fix.recorder.get_calls(target_state_id)

        assert len(calls) == 1
        assert calls[0].call_id == target.tokens[0].call_id

    def test_excludes_other_run_calls(self, multi_run_landscape: MultiRunFixture) -> None:
        """st-B-0 < st-C-0 — a >= mutation would include run-C's call."""
        fix = multi_run_landscape
        calls_b = fix.recorder.get_calls(fix.run("B").tokens[0].state_id)
        calls_c = fix.recorder.get_calls(fix.run("C").tokens[0].state_id)

        b_ids = {c.call_id for c in calls_b}
        c_ids = {c.call_id for c in calls_c}

        assert b_ids.isdisjoint(c_ids)
        assert len(calls_b) == 1
        assert len(calls_c) == 1

    def test_returns_empty_for_state_without_calls(self, multi_run_landscape: MultiRunFixture) -> None:
        """Second token in each run has no call — verify empty, not leaking."""
        fix = multi_run_landscape
        target = fix.run("B")
        calls = fix.recorder.get_calls(target.tokens[1].state_id)  # st-B-1 has no call

        assert calls == []


class TestFindCallByRequestHashWhereExactness:
    """find_call_by_request_hash is the MOST DANGEROUS mutation target.

    This method is used for LLM response caching.  If ``==`` becomes ``>=``
    on run_id, it could return a cached response from a *different* run,
    silently corrupting pipeline results.
    """

    def test_returns_only_target_run_call(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        # Get the request hash from run-B's call
        target_call_id = target.tokens[0].call_id
        assert target_call_id is not None
        calls_b = fix.recorder.get_calls(target.tokens[0].state_id)
        assert len(calls_b) == 1
        request_hash = calls_b[0].request_hash

        # Look up by run-B's run_id — must return run-B's call
        result = fix.recorder.find_call_by_request_hash(target.run_id, CallType.HTTP, request_hash)

        assert result is not None
        assert result.call_id == target_call_id

    def test_does_not_leak_across_runs(self, multi_run_landscape: MultiRunFixture) -> None:
        """Each run has a different request URL, so hashes differ.

        Even if hashes happened to match, the run_id filter must be exact.
        Query with run-A's run_id and run-B's hash — must return None.
        """
        fix = multi_run_landscape
        run_b = fix.run("B")

        # Get run-B's request hash
        calls_b = fix.recorder.get_calls(run_b.tokens[0].state_id)
        request_hash_b = calls_b[0].request_hash

        # Query with run-A's run_id — must NOT find run-B's call
        result = fix.recorder.find_call_by_request_hash(fix.run("A").run_id, CallType.HTTP, request_hash_b)

        assert result is None

    def test_each_run_has_unique_request_hash(self, multi_run_landscape: MultiRunFixture) -> None:
        """Verify fixture produces distinct hashes so cross-run leaks are detectable."""
        fix = multi_run_landscape
        hashes = {}
        for suffix in ("A", "B", "C"):
            run = fix.run(suffix)
            calls = fix.recorder.get_calls(run.tokens[0].state_id)
            assert len(calls) == 1
            hashes[suffix] = calls[0].request_hash

        # All three hashes must be distinct (different request URLs per run)
        assert len(set(hashes.values())) == 3


class TestGetRoutingEventsWhereExactness:
    """get_routing_events (state-scoped) must return only events for the target state."""

    def test_returns_only_target_state_events(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")
        target_state_id = target.tokens[0].state_id  # st-B-0 has a routing event

        events = fix.recorder.get_routing_events(target_state_id)

        assert len(events) == 1
        assert events[0].event_id == target.tokens[0].routing_event_id

    def test_excludes_other_run_events(self, multi_run_landscape: MultiRunFixture) -> None:
        """st-B-0 < st-C-0 — a >= mutation would include run-C's event."""
        fix = multi_run_landscape
        events_b = fix.recorder.get_routing_events(fix.run("B").tokens[0].state_id)
        events_c = fix.recorder.get_routing_events(fix.run("C").tokens[0].state_id)

        b_ids = {e.event_id for e in events_b}
        c_ids = {e.event_id for e in events_c}

        assert b_ids.isdisjoint(c_ids)
        assert len(events_b) == 1
        assert len(events_c) == 1

    def test_returns_empty_for_state_without_events(self, multi_run_landscape: MultiRunFixture) -> None:
        """Second token in each run has no routing event."""
        fix = multi_run_landscape
        events = fix.recorder.get_routing_events(fix.run("B").tokens[1].state_id)

        assert events == []


class TestGetBatchWhereExactness:
    """get_batch must return only the targeted batch, not neighbours."""

    def test_returns_only_target_batch(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        batch = fix.recorder.get_batch(target.batch_id)

        assert batch is not None
        assert batch.batch_id == target.batch_id

    def test_does_not_return_adjacent_batch(self, multi_run_landscape: MultiRunFixture) -> None:
        """batch-B < batch-C — a >= mutation would also match batch-C."""
        fix = multi_run_landscape
        batch = fix.recorder.get_batch(fix.run("B").batch_id)

        assert batch is not None
        assert batch.batch_id == fix.run("B").batch_id
        assert batch.batch_id != fix.run("A").batch_id
        assert batch.batch_id != fix.run("C").batch_id

    def test_returns_none_for_nonexistent(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        assert fix.recorder.get_batch("batch-NONEXISTENT") is None


class TestGetBatchMembersWhereExactness:
    """get_batch_members must return only members for the target batch."""

    def test_returns_only_target_batch_members(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        members = fix.recorder.get_batch_members(target.batch_id)

        assert len(members) == 2
        member_token_ids = {m.token_id for m in members}
        expected_token_ids = {t.token_id for t in target.tokens}
        assert member_token_ids == expected_token_ids

    def test_excludes_other_run_batch_members(self, multi_run_landscape: MultiRunFixture) -> None:
        """batch-B < batch-C — a >= mutation would include batch-C's members."""
        fix = multi_run_landscape
        members_b = fix.recorder.get_batch_members(fix.run("B").batch_id)
        members_c = fix.recorder.get_batch_members(fix.run("C").batch_id)

        b_tokens = {m.token_id for m in members_b}
        c_tokens = {m.token_id for m in members_c}

        assert b_tokens.isdisjoint(c_tokens)
        assert len(members_b) == 2
        assert len(members_c) == 2

    def test_members_ordered_by_ordinal(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        members = fix.recorder.get_batch_members(fix.run("B").batch_id)

        ordinals = [m.ordinal for m in members]
        assert ordinals == sorted(ordinals)


class TestGetOperationWhereExactness:
    """get_operation must return only the targeted operation, not neighbours.

    The multi-run fixture does not create operations, so this test creates
    them inline to verify the WHERE clause exactness.
    """

    def test_returns_only_target_operation(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Create operations in two runs so IDs are ordered
        op_b = fix.recorder.begin_operation(
            fix.run("B").run_id,
            fix.run("B").source_node_id,
            "source_load",
        )
        op_c = fix.recorder.begin_operation(
            fix.run("C").run_id,
            fix.run("C").source_node_id,
            "source_load",
        )

        result = fix.recorder.get_operation(op_b.operation_id)

        assert result is not None
        assert result.operation_id == op_b.operation_id
        assert result.operation_id != op_c.operation_id

    def test_returns_none_for_nonexistent(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        assert fix.recorder.get_operation("op-NONEXISTENT") is None


class TestGetOperationCallsWhereExactness:
    """get_operation_calls must return only calls for the target operation."""

    def test_returns_only_target_operation_calls(self, multi_run_landscape: MultiRunFixture) -> None:
        from elspeth.contracts import CallStatus
        from elspeth.contracts.call_data import RawCallPayload

        fix = multi_run_landscape

        # Create operations and calls in two runs
        op_b = fix.recorder.begin_operation(
            fix.run("B").run_id,
            fix.run("B").source_node_id,
            "source_load",
        )
        call_b = fix.recorder.record_operation_call(
            op_b.operation_id,
            CallType.HTTP,
            CallStatus.SUCCESS,
            RawCallPayload({"url": "https://b.example.com"}),
            RawCallPayload({"ok": True}),
            latency_ms=10.0,
        )

        op_c = fix.recorder.begin_operation(
            fix.run("C").run_id,
            fix.run("C").source_node_id,
            "source_load",
        )
        fix.recorder.record_operation_call(
            op_c.operation_id,
            CallType.HTTP,
            CallStatus.SUCCESS,
            RawCallPayload({"url": "https://c.example.com"}),
            RawCallPayload({"ok": True}),
            latency_ms=10.0,
        )

        calls = fix.recorder.get_operation_calls(op_b.operation_id)

        assert len(calls) == 1
        assert calls[0].call_id == call_b.call_id
