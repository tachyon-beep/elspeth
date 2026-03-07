# tests/unit/core/landscape/test_where_exactness.py
"""WHERE clause exactness tests for landscape query methods.

These tests verify that SQL queries use ``==`` (exact match) rather than
``>=`` / ``<=`` (range) operators.  The multi-run fixture creates three
runs with lexicographically ordered IDs (run-A < run-B < run-C) so that
an inequality operator would silently include data from adjacent runs.

The fixture lives in ``tests/fixtures/multi_run.py`` and is imported as
a pytest fixture via the ``multi_run_landscape`` name.
"""

from __future__ import annotations

from tests.fixtures.multi_run import MultiRunFixture

pytest_plugins = ["tests.fixtures.multi_run"]


class TestGetRowsWhereExactness:
    """get_rows must return only rows belonging to the target run."""

    def test_returns_only_target_run_rows(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        rows = fix.recorder.get_rows(target.run_id)

        assert len(rows) == 2
        assert all(r.run_id == target.run_id for r in rows)
        assert {r.row_id for r in rows} == set(target.row_ids)

    def test_excludes_adjacent_run_rows(self, multi_run_landscape: MultiRunFixture) -> None:
        """Regression guard: ``>=`` on 'run-A' would also return run-B and run-C."""
        fix = multi_run_landscape
        rows = fix.recorder.get_rows("run-A")

        assert len(rows) == 2
        assert all(r.run_id == "run-A" for r in rows)

    def test_excludes_prior_run_rows(self, multi_run_landscape: MultiRunFixture) -> None:
        """Regression guard: ``<=`` on 'run-C' would also return run-A and run-B."""
        fix = multi_run_landscape
        rows = fix.recorder.get_rows("run-C")

        assert len(rows) == 2
        assert all(r.run_id == "run-C" for r in rows)


class TestGetAllTokensForRunWhereExactness:
    """get_all_tokens_for_run must scope tokens to the target run only."""

    def test_returns_only_target_run_tokens(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        tokens = fix.recorder.get_all_tokens_for_run(target.run_id)

        expected_token_ids = {t.token_id for t in target.tokens}
        assert {t.token_id for t in tokens} == expected_token_ids
        assert len(tokens) == 2

    def test_excludes_adjacent_runs(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        tokens_a = fix.recorder.get_all_tokens_for_run("run-A")
        tokens_c = fix.recorder.get_all_tokens_for_run("run-C")

        a_ids = {t.token_id for t in tokens_a}
        c_ids = {t.token_id for t in tokens_c}

        # No overlap between runs
        assert a_ids.isdisjoint(c_ids)
        assert len(tokens_a) == 2
        assert len(tokens_c) == 2


class TestGetAllNodeStatesForRunWhereExactness:
    """get_all_node_states_for_run must scope states to the target run only."""

    def test_returns_only_target_run_states(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        states = fix.recorder.get_all_node_states_for_run(target.run_id)

        expected_state_ids = {t.state_id for t in target.tokens}
        assert {s.state_id for s in states} == expected_state_ids
        assert len(states) == 2

    def test_excludes_adjacent_runs(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        states_a = fix.recorder.get_all_node_states_for_run("run-A")
        states_c = fix.recorder.get_all_node_states_for_run("run-C")

        a_ids = {s.state_id for s in states_a}
        c_ids = {s.state_id for s in states_c}

        assert a_ids.isdisjoint(c_ids)
        assert len(states_a) == 2
        assert len(states_c) == 2


class TestGetAllCallsForRunWhereExactness:
    """get_all_calls_for_run must scope calls to the target run only."""

    def test_returns_only_target_run_calls(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        calls = fix.recorder.get_all_calls_for_run(target.run_id)

        # Only the first token per run has a call
        expected_call_ids = {t.call_id for t in target.tokens if t.call_id is not None}
        assert {c.call_id for c in calls} == expected_call_ids
        assert len(calls) == 1

    def test_excludes_adjacent_runs(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        all_calls: list[str] = []
        for suffix in ("A", "B", "C"):
            calls = fix.recorder.get_all_calls_for_run(fix.run(suffix).run_id)
            call_ids = [c.call_id for c in calls]
            # Each run has exactly 1 call
            assert len(call_ids) == 1
            all_calls.extend(call_ids)

        # All call IDs are distinct across runs
        assert len(set(all_calls)) == 3


class TestGetAllRoutingEventsForRunWhereExactness:
    """get_all_routing_events_for_run must scope events to the target run only."""

    def test_returns_only_target_run_events(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        events = fix.recorder.get_all_routing_events_for_run(target.run_id)

        expected_re_ids = {t.routing_event_id for t in target.tokens if t.routing_event_id is not None}
        assert {e.event_id for e in events} == expected_re_ids
        assert len(events) == 1


class TestGetAllTokenOutcomesForRunWhereExactness:
    """get_all_token_outcomes_for_run must scope outcomes to the target run only."""

    def test_returns_only_target_run_outcomes(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        outcomes = fix.recorder.get_all_token_outcomes_for_run(target.run_id)

        expected_token_ids = {t.token_id for t in target.tokens}
        assert {o.token_id for o in outcomes} == expected_token_ids
        assert len(outcomes) == 2

    def test_excludes_adjacent_runs(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        outcomes_a = fix.recorder.get_all_token_outcomes_for_run("run-A")
        outcomes_c = fix.recorder.get_all_token_outcomes_for_run("run-C")

        a_ids = {o.token_id for o in outcomes_a}
        c_ids = {o.token_id for o in outcomes_c}

        assert a_ids.isdisjoint(c_ids)
        assert len(outcomes_a) == 2
        assert len(outcomes_c) == 2


class TestGetBatchesWhereExactness:
    """get_batches must scope batches to the target run only."""

    def test_returns_only_target_run_batches(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        batches = fix.recorder.get_batches(target.run_id)

        assert len(batches) == 1
        assert batches[0].batch_id == target.batch_id

    def test_excludes_adjacent_runs(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        all_batch_ids: list[str] = []
        for suffix in ("A", "B", "C"):
            batches = fix.recorder.get_batches(fix.run(suffix).run_id)
            assert len(batches) == 1
            all_batch_ids.append(batches[0].batch_id)

        assert len(set(all_batch_ids)) == 3
