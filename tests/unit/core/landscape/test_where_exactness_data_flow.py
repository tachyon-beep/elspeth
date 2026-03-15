# tests/unit/core/landscape/test_where_exactness_data_flow.py
"""WHERE clause exactness tests for DataFlowRepository query methods.

These tests verify that SQL queries use ``==`` (exact match) rather than
``>=`` / ``<=`` (range) operators.  The multi-run fixture creates three
runs with lexicographically ordered IDs (run-A < run-B < run-C) so that
an inequality operator would silently include data from adjacent runs.

Targets: get_node, get_edges, get_token_outcome, get_token_outcomes_for_row,
record_validation_error / get_validation_errors_for_run,
record_transform_error / get_transform_errors_for_run.
"""

from __future__ import annotations

from tests.fixtures.multi_run import MultiRunFixture

pytest_plugins = ["tests.fixtures.multi_run"]


class TestGetNodeWhereExactness:
    """get_node must return exactly the target node by composite PK."""

    def test_returns_target_node_for_run_b(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        node = fix.recorder.get_node(target.source_node_id, target.run_id)

        assert node is not None
        assert node.node_id == target.source_node_id
        assert node.run_id == target.run_id

    def test_excludes_run_a_node_when_querying_run_b(self, multi_run_landscape: MultiRunFixture) -> None:
        """If run_id filter used ``>=`` on 'run-A', it would also match run-B."""
        fix = multi_run_landscape
        run_a = fix.run("A")
        run_b = fix.run("B")

        # Query run-B's source node with run-A's run_id — must return None
        result = fix.recorder.get_node(run_b.source_node_id, run_a.run_id)
        assert result is None

    def test_excludes_run_c_node_when_querying_run_b(self, multi_run_landscape: MultiRunFixture) -> None:
        """If run_id filter used ``<=`` on 'run-C', it would also match run-B."""
        fix = multi_run_landscape
        run_b = fix.run("B")
        run_c = fix.run("C")

        result = fix.recorder.get_node(run_b.source_node_id, run_c.run_id)
        assert result is None

    def test_node_id_filter_is_exact(self, multi_run_landscape: MultiRunFixture) -> None:
        """Verify node_id equality is exact — src-A < src-B, so ``>=`` would leak."""
        fix = multi_run_landscape
        run_b = fix.run("B")

        # Query with run-B's run_id but run-A's node_id
        result = fix.recorder.get_node(fix.run("A").source_node_id, run_b.run_id)
        assert result is None

    def test_each_run_returns_its_own_transform_node(self, multi_run_landscape: MultiRunFixture) -> None:
        """All three runs have distinct transform nodes; each resolves exactly."""
        fix = multi_run_landscape
        for suffix in ("A", "B", "C"):
            run = fix.run(suffix)
            node = fix.recorder.get_node(run.transform_node_id, run.run_id)
            assert node is not None
            assert node.node_id == run.transform_node_id
            assert node.run_id == run.run_id


class TestGetEdgesWhereExactness:
    """get_edges must return only edges for the target run."""

    def test_returns_only_target_run_edges(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")

        edges = fix.recorder.get_edges(target.run_id)

        assert len(edges) == 2
        edge_ids = {e.edge_id for e in edges}
        assert edge_ids == {target.edge_id_source_to_transform, target.edge_id_transform_to_sink}

    def test_excludes_adjacent_run_edges(self, multi_run_landscape: MultiRunFixture) -> None:
        """Regression: ``>=`` on 'run-A' would include run-B/C edges."""
        fix = multi_run_landscape
        edges_a = fix.recorder.get_edges("run-A")
        edges_c = fix.recorder.get_edges("run-C")

        a_ids = {e.edge_id for e in edges_a}
        c_ids = {e.edge_id for e in edges_c}
        b_ids = {e.edge_id for e in fix.recorder.get_edges("run-B")}

        # No overlap between any runs
        assert a_ids.isdisjoint(b_ids)
        assert a_ids.isdisjoint(c_ids)
        assert b_ids.isdisjoint(c_ids)

    def test_exact_count_per_run(self, multi_run_landscape: MultiRunFixture) -> None:
        """Each run has exactly 2 edges; inequality would inflate the count."""
        fix = multi_run_landscape
        for suffix in ("A", "B", "C"):
            edges = fix.recorder.get_edges(fix.run(suffix).run_id)
            assert len(edges) == 2


class TestGetTokenOutcomeWhereExactness:
    """get_token_outcome must return exactly the outcome for the target token."""

    def test_returns_target_token_outcome(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")
        tok = target.tokens[0]

        outcome = fix.recorder.get_token_outcome(tok.token_id)

        assert outcome is not None
        assert outcome.token_id == tok.token_id

    def test_does_not_return_adjacent_token_outcome(self, multi_run_landscape: MultiRunFixture) -> None:
        """tok-A-0 < tok-B-0 < tok-C-0: ``>=`` on tok-A-0 would leak tok-B-0."""
        fix = multi_run_landscape
        tok_a = fix.run("A").tokens[0]
        tok_b = fix.run("B").tokens[0]

        outcome_a = fix.recorder.get_token_outcome(tok_a.token_id)
        outcome_b = fix.recorder.get_token_outcome(tok_b.token_id)

        assert outcome_a is not None
        assert outcome_b is not None
        assert outcome_a.token_id == tok_a.token_id
        assert outcome_b.token_id == tok_b.token_id
        assert outcome_a.token_id != outcome_b.token_id

    def test_each_token_resolves_independently(self, multi_run_landscape: MultiRunFixture) -> None:
        """All 6 tokens (2 per run x 3 runs) each resolve to their own outcome."""
        fix = multi_run_landscape
        seen_token_ids: set[str] = set()
        for suffix in ("A", "B", "C"):
            for tok in fix.run(suffix).tokens:
                outcome = fix.recorder.get_token_outcome(tok.token_id)
                assert outcome is not None
                assert outcome.token_id == tok.token_id
                seen_token_ids.add(outcome.token_id)
        assert len(seen_token_ids) == 6


class TestGetTokenOutcomesForRowWhereExactness:
    """get_token_outcomes_for_row must return only outcomes for the target row in the target run."""

    def test_returns_only_target_row_outcomes(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        target = fix.run("B")
        row_id = target.row_ids[0]

        outcomes = fix.recorder.get_token_outcomes_for_row(target.run_id, row_id)

        assert len(outcomes) == 1
        assert outcomes[0].token_id == target.tokens[0].token_id

    def test_excludes_other_rows_in_same_run(self, multi_run_landscape: MultiRunFixture) -> None:
        """row-B-0 and row-B-1 each have their own outcome; no cross-contamination."""
        fix = multi_run_landscape
        target = fix.run("B")

        outcomes_0 = fix.recorder.get_token_outcomes_for_row(target.run_id, target.row_ids[0])
        outcomes_1 = fix.recorder.get_token_outcomes_for_row(target.run_id, target.row_ids[1])

        tok_ids_0 = {o.token_id for o in outcomes_0}
        tok_ids_1 = {o.token_id for o in outcomes_1}
        assert tok_ids_0.isdisjoint(tok_ids_1)

    def test_excludes_adjacent_run_outcomes(self, multi_run_landscape: MultiRunFixture) -> None:
        """run_id filter must be exact — ``>=`` on run-A would leak run-B/C."""
        fix = multi_run_landscape
        # row-A-0 queried with run-B's run_id should return nothing
        outcomes = fix.recorder.get_token_outcomes_for_row("run-B", fix.run("A").row_ids[0])
        assert len(outcomes) == 0

    def test_run_id_and_row_id_both_exact(self, multi_run_landscape: MultiRunFixture) -> None:
        """Both WHERE filters must be exact for correct scoping."""
        fix = multi_run_landscape
        for suffix in ("A", "B", "C"):
            run = fix.run(suffix)
            for i, row_id in enumerate(run.row_ids):
                outcomes = fix.recorder.get_token_outcomes_for_row(run.run_id, row_id)
                assert len(outcomes) == 1
                assert outcomes[0].token_id == run.tokens[i].token_id


class TestValidationErrorsWhereExactness:
    """record_validation_error + get_validation_errors_for_run must scope by run."""

    def test_returns_only_target_run_errors(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Record validation errors in all three runs
        for suffix in ("A", "B", "C"):
            run = fix.run(suffix)
            fix.recorder.record_validation_error(
                run_id=run.run_id,
                node_id=run.source_node_id,
                row_data={"bad_field": f"val-{suffix}"},
                error=f"schema violation in {suffix}",
                schema_mode="fixed",
                destination="discard",
            )

        # Query only run-B
        errors = fix.recorder.get_validation_errors_for_run("run-B")

        assert len(errors) == 1
        assert errors[0].run_id == "run-B"
        assert errors[0].error == "schema violation in B"

    def test_excludes_adjacent_run_errors(self, multi_run_landscape: MultiRunFixture) -> None:
        """``>=`` on run-A would leak run-B/C errors; ``<=`` on run-C would leak A/B."""
        fix = multi_run_landscape

        for suffix in ("A", "B", "C"):
            run = fix.run(suffix)
            fix.recorder.record_validation_error(
                run_id=run.run_id,
                node_id=run.source_node_id,
                row_data={"x": suffix},
                error=f"err-{suffix}",
                schema_mode="observed",
                destination="discard",
            )

        errors_a = fix.recorder.get_validation_errors_for_run("run-A")
        errors_c = fix.recorder.get_validation_errors_for_run("run-C")

        assert len(errors_a) == 1
        assert errors_a[0].run_id == "run-A"
        assert len(errors_c) == 1
        assert errors_c[0].run_id == "run-C"

    def test_multiple_errors_in_one_run_all_returned(self, multi_run_landscape: MultiRunFixture) -> None:
        """Multiple errors in the same run are all returned; others excluded."""
        fix = multi_run_landscape
        run_b = fix.run("B")

        fix.recorder.record_validation_error(
            run_id=run_b.run_id,
            node_id=run_b.source_node_id,
            row_data={"a": 1},
            error="err-1",
            schema_mode="fixed",
            destination="discard",
        )
        fix.recorder.record_validation_error(
            run_id=run_b.run_id,
            node_id=run_b.source_node_id,
            row_data={"b": 2},
            error="err-2",
            schema_mode="fixed",
            destination="discard",
        )
        # Decoy in run-C
        fix.recorder.record_validation_error(
            run_id="run-C",
            node_id=fix.run("C").source_node_id,
            row_data={"c": 3},
            error="err-c",
            schema_mode="fixed",
            destination="discard",
        )

        errors = fix.recorder.get_validation_errors_for_run("run-B")
        assert len(errors) == 2
        assert all(e.run_id == "run-B" for e in errors)


class TestTransformErrorsWhereExactness:
    """record_transform_error + get_transform_errors_for_run must scope by run."""

    def test_returns_only_target_run_errors(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Record transform errors in all three runs (using first token of each)
        for suffix in ("A", "B", "C"):
            run = fix.run(suffix)
            tok = run.tokens[0]
            fix.recorder.record_transform_error(
                run_id=run.run_id,
                token_id=tok.token_id,
                transform_id=run.transform_node_id,
                row_data={"val": f"err-{suffix}"},
                error_details={"reason": f"failed-{suffix}"},
                destination="discard",
            )

        # Query only run-B
        errors = fix.recorder.get_transform_errors_for_run("run-B")

        assert len(errors) == 1
        assert errors[0].run_id == "run-B"
        assert errors[0].token_id == fix.run("B").tokens[0].token_id

    def test_excludes_adjacent_run_errors(self, multi_run_landscape: MultiRunFixture) -> None:
        """``>=`` on run-A would leak run-B/C errors."""
        fix = multi_run_landscape

        for suffix in ("A", "B", "C"):
            run = fix.run(suffix)
            tok = run.tokens[0]
            fix.recorder.record_transform_error(
                run_id=run.run_id,
                token_id=tok.token_id,
                transform_id=run.transform_node_id,
                row_data={"v": suffix},
                error_details={"reason": f"r-{suffix}"},
                destination="discard",
            )

        errors_a = fix.recorder.get_transform_errors_for_run("run-A")
        errors_c = fix.recorder.get_transform_errors_for_run("run-C")

        assert len(errors_a) == 1
        assert errors_a[0].run_id == "run-A"
        assert len(errors_c) == 1
        assert errors_c[0].run_id == "run-C"

    def test_multiple_errors_in_one_run_all_returned(self, multi_run_landscape: MultiRunFixture) -> None:
        """Multiple errors in the same run are all returned; others excluded."""
        fix = multi_run_landscape
        run_b = fix.run("B")

        # Two errors in run-B (one per token)
        for tok in run_b.tokens:
            fix.recorder.record_transform_error(
                run_id=run_b.run_id,
                token_id=tok.token_id,
                transform_id=run_b.transform_node_id,
                row_data={"t": tok.token_id},
                error_details={"reason": f"fail-{tok.token_id}"},
                destination="discard",
            )

        # Decoy in run-A
        run_a = fix.run("A")
        fix.recorder.record_transform_error(
            run_id=run_a.run_id,
            token_id=run_a.tokens[0].token_id,
            transform_id=run_a.transform_node_id,
            row_data={"t": "decoy"},
            error_details={"reason": "decoy"},
            destination="discard",
        )

        errors = fix.recorder.get_transform_errors_for_run("run-B")
        assert len(errors) == 2
        assert all(e.run_id == "run-B" for e in errors)
