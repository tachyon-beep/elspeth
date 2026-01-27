# tests/engine/test_audit_sweep.py
"""Explicit audit sweep tests for token outcome contract enforcement.

CI GATE: These tests enforce the Token Outcome Assurance contract.
See docs/audit/tokens/ for the full specification.

These tests run pipelines and then execute the SQL queries from
docs/audit/tokens/02-audit-sweep.md to verify no gaps exist.

This is defense-in-depth: even if individual assertions miss an edge case,
the sweep queries scan the entire audit trail for invariant violations.

Required CI gates enforced here:
1. Audit sweep passes (no missing terminal outcomes)
2. Required fields present for all outcomes
3. Sink node_state <-> COMPLETED outcome consistency
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from elspeth.contracts import SourceRow
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.artifacts import ArtifactDescriptor
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.results import TransformResult
from tests.conftest import _TestSchema, _TestSinkBase, _TestSourceBase
from tests.engine.orchestrator_test_helpers import build_test_graph

if TYPE_CHECKING:
    pass


# =============================================================================
# Audit Sweep Query Definitions (from docs/audit/tokens/02-audit-sweep.md)
# =============================================================================


def run_audit_sweep(db: LandscapeDB, run_id: str) -> dict[str, list[Any]]:
    """Execute all audit sweep queries and return results.

    Returns dict mapping query name to list of gap records.
    Empty lists mean no gaps found (good).
    """
    results = {}

    with db.connection() as conn:
        # Query 1: Tokens missing terminal outcome
        results["1_missing_terminal"] = list(
            conn.execute(
                text("""
                    SELECT t.token_id, t.row_id
                    FROM tokens t
                    JOIN rows r ON r.row_id = t.row_id
                    LEFT JOIN token_outcomes o
                      ON o.token_id = t.token_id AND o.is_terminal = 1
                    WHERE r.run_id = :run_id
                      AND o.token_id IS NULL
                """),
                {"run_id": run_id},
            ).fetchall()
        )

        # Query 2: Duplicate terminal outcomes
        results["2_duplicate_terminal"] = list(
            conn.execute(
                text("""
                    SELECT token_id, COUNT(*) AS terminal_count
                    FROM token_outcomes
                    WHERE is_terminal = 1
                    GROUP BY token_id
                    HAVING COUNT(*) > 1
                """)
            ).fetchall()
        )

        # Query 3: Required fields missing
        results["3_missing_required_fields"] = list(
            conn.execute(
                text("""
                    SELECT outcome_id, token_id, outcome
                    FROM token_outcomes
                    WHERE
                      (outcome IN ('completed','routed') AND sink_name IS NULL)
                      OR (outcome IN ('failed','quarantined') AND error_hash IS NULL)
                      OR (outcome = 'forked' AND fork_group_id IS NULL)
                      OR (outcome = 'coalesced' AND join_group_id IS NULL)
                      OR (outcome = 'expanded' AND expand_group_id IS NULL)
                      OR (outcome IN ('buffered','consumed_in_batch') AND batch_id IS NULL)
                """)
            ).fetchall()
        )

        # Query 4: COMPLETED without completed sink node_state
        # Use EXISTS to check for the presence of a completed sink node_state
        results["4_completed_no_sink_state"] = list(
            conn.execute(
                text("""
                    SELECT o.token_id
                    FROM token_outcomes o
                    WHERE o.run_id = :run_id
                      AND o.outcome = 'completed'
                      AND NOT EXISTS (
                        SELECT 1 FROM node_states ns
                        JOIN nodes n ON n.node_id = ns.node_id AND n.run_id = ns.run_id
                        WHERE ns.token_id = o.token_id
                          AND ns.run_id = o.run_id
                          AND n.node_type = 'sink'
                          AND ns.status = 'completed'
                      )
                """),
                {"run_id": run_id},
            ).fetchall()
        )

        # Query 5: Completed sink node_state without COMPLETED outcome
        results["5_sink_state_no_completed"] = list(
            conn.execute(
                text("""
                    SELECT DISTINCT ns.token_id
                    FROM node_states ns
                    JOIN nodes n
                      ON n.node_id = ns.node_id AND n.run_id = ns.run_id
                    LEFT JOIN token_outcomes o
                      ON o.token_id = ns.token_id AND o.is_terminal = 1 AND o.outcome = 'completed'
                    WHERE ns.run_id = :run_id
                      AND n.node_type = 'sink'
                      AND ns.status = 'completed'
                      AND o.token_id IS NULL
                """),
                {"run_id": run_id},
            ).fetchall()
        )

        # Query 6: Fork children missing parent links
        results["6_fork_missing_parent"] = list(
            conn.execute(
                text("""
                    SELECT t.token_id
                    FROM tokens t
                    LEFT JOIN token_parents p ON p.token_id = t.token_id
                    WHERE t.fork_group_id IS NOT NULL
                      AND p.token_id IS NULL
                """)
            ).fetchall()
        )

        # Query 7: Expand children missing parent links
        results["7_expand_missing_parent"] = list(
            conn.execute(
                text("""
                    SELECT t.token_id
                    FROM tokens t
                    LEFT JOIN token_parents p ON p.token_id = t.token_id
                    WHERE t.expand_group_id IS NOT NULL
                      AND p.token_id IS NULL
                """)
            ).fetchall()
        )

    return results


def assert_audit_sweep_clean(db: LandscapeDB, run_id: str) -> None:
    """Assert all audit sweep queries return empty (no gaps).

    Raises AssertionError with details if any gaps found.
    """
    results = run_audit_sweep(db, run_id)
    gaps = {k: v for k, v in results.items() if v}

    if gaps:
        gap_details = "\n".join(f"  {k}: {v[:5]}{'...' if len(v) > 5 else ''}" for k, v in gaps.items())
        raise AssertionError(
            f"Audit sweep found {sum(len(v) for v in gaps.values())} gaps:\n{gap_details}\n"
            f"See docs/audit/tokens/02-audit-sweep.md for query definitions"
        )


# =============================================================================
# Test Fixtures
# =============================================================================


class _ValueSchema(_TestSchema):
    """Simple schema for tests."""

    value: int


class _ListSource(_TestSourceBase):
    """Source that emits rows from a list."""

    name = "list_source"
    output_schema = _ValueSchema

    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data

    def on_start(self, ctx: Any) -> None:
        pass

    def load(self, ctx: Any) -> Iterator[SourceRow]:
        for row in self._data:
            yield SourceRow.valid(row)

    def close(self) -> None:
        pass


class _PassTransform(BaseTransform):
    """Transform that passes rows through unchanged."""

    name = "pass_transform"
    input_schema = _ValueSchema
    output_schema = _ValueSchema

    def __init__(self) -> None:
        super().__init__({"schema": {"fields": "dynamic"}})

    def process(self, row: Any, ctx: Any) -> TransformResult:
        return TransformResult.success(row)


class _CollectSink(_TestSinkBase):
    """Sink that collects written rows."""

    name = "collect_sink"

    def __init__(self, sink_name: str = "collect_sink") -> None:
        self.name = sink_name
        self.results: list[dict[str, Any]] = []

    def on_start(self, ctx: Any) -> None:
        self.results = []

    def on_complete(self, ctx: Any) -> None:
        pass

    def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
        self.results.extend(rows)
        return ArtifactDescriptor.for_file(
            path=f"memory://{self.name}",
            size_bytes=len(str(rows)),
            content_hash="test_hash",
        )

    def close(self) -> None:
        pass


# =============================================================================
# Audit Sweep Tests
# =============================================================================


class TestAuditSweepSimplePipeline:
    """Audit sweep tests for simple linear pipelines."""

    def test_linear_pipeline_passes_audit_sweep(self) -> None:
        """Simple source -> transform -> sink pipeline passes all sweep queries."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from tests.conftest import as_sink, as_source, as_transform

        db = LandscapeDB.in_memory()

        source = _ListSource([{"value": 1}, {"value": 2}, {"value": 3}])
        transform = _PassTransform()
        sink = _CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run = orchestrator.run(config, graph=build_test_graph(config))

        # Verify rows processed
        assert len(sink.results) == 3

        # Run audit sweep - should pass
        assert_audit_sweep_clean(db, run.run_id)

    def test_empty_source_passes_audit_sweep(self) -> None:
        """Empty source (no rows) still passes audit sweep."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from tests.conftest import as_sink, as_source, as_transform

        db = LandscapeDB.in_memory()

        source = _ListSource([])  # Empty
        transform = _PassTransform()
        sink = _CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run = orchestrator.run(config, graph=build_test_graph(config))

        assert len(sink.results) == 0
        assert_audit_sweep_clean(db, run.run_id)


class TestAuditSweepGateRouting:
    """Audit sweep tests for gate routing scenarios."""

    def test_gate_continue_passes_audit_sweep(self) -> None:
        """Gate with continue routing passes audit sweep.

        Note: Tokens routed to a named sink by a gate get ROUTED outcome.
        Tokens that 'continue' through the pipeline get COMPLETED outcome.
        Both are valid terminal states.
        """
        from elspeth.core.config import GateSettings
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from tests.conftest import as_sink, as_source, as_transform

        db = LandscapeDB.in_memory()

        # All rows will continue through (condition is always false)
        source = _ListSource([{"value": 1}, {"value": 2}, {"value": 3}])
        transform = _PassTransform()
        default_sink = _CollectSink("default")
        routed_sink = _CollectSink("routed")

        # Gate: condition is always false, so all continue to default
        gate = GateSettings(
            name="never_route_gate",
            condition="row['value'] > 100",  # Always false for our data
            routes={"true": "routed", "false": "continue"},
        )

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(default_sink), "routed": as_sink(routed_sink)},
            gates=[gate],
        )

        orchestrator = Orchestrator(db)
        run = orchestrator.run(config, graph=build_test_graph(config))

        # All rows should continue to default (COMPLETED outcome)
        assert len(default_sink.results) == 3
        assert len(routed_sink.results) == 0

        # Audit sweep should pass - all tokens have COMPLETED outcome
        assert_audit_sweep_clean(db, run.run_id)


class TestAuditSweepErrorHandling:
    """Audit sweep tests for error scenarios."""

    def test_quarantined_rows_pass_audit_sweep(self) -> None:
        """Rows routed to quarantine (discard) pass audit sweep."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from tests.conftest import as_sink, as_source, as_transform

        db = LandscapeDB.in_memory()

        class _FailingTransform(BaseTransform):
            """Transform that fails for specific values."""

            name = "failing_transform"
            input_schema = _ValueSchema
            output_schema = _ValueSchema
            _on_error = "discard"  # Route errors to quarantine

            def __init__(self) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                if row["value"] == 2:
                    return TransformResult.error({"reason": "test_error"})
                return TransformResult.success(row)

        source = _ListSource([{"value": 1}, {"value": 2}, {"value": 3}])
        transform = _FailingTransform()
        sink = _CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run = orchestrator.run(config, graph=build_test_graph(config))

        # value=2 should be quarantined, others processed
        assert len(sink.results) == 2

        # Audit sweep should pass - quarantined tokens have QUARANTINED outcome
        assert_audit_sweep_clean(db, run.run_id)


class TestAuditSweepMetrics:
    """Test audit sweep metrics collection."""

    def test_run_audit_sweep_returns_all_query_results(self) -> None:
        """run_audit_sweep returns results for all 7 queries."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from tests.conftest import as_sink, as_source, as_transform

        db = LandscapeDB.in_memory()

        source = _ListSource([{"value": 1}])
        transform = _PassTransform()
        sink = _CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run = orchestrator.run(config, graph=build_test_graph(config))

        results = run_audit_sweep(db, run.run_id)

        # All 7 queries should be present
        assert "1_missing_terminal" in results
        assert "2_duplicate_terminal" in results
        assert "3_missing_required_fields" in results
        assert "4_completed_no_sink_state" in results
        assert "5_sink_state_no_completed" in results
        assert "6_fork_missing_parent" in results
        assert "7_expand_missing_parent" in results

        # All should be empty (clean)
        for name, gaps in results.items():
            assert gaps == [], f"Query {name} found unexpected gaps: {gaps}"


class TestAuditSweepForkCoalesce:
    """Audit sweep tests for fork/coalesce pipelines.

    These tests verify that merged tokens from coalesce operations have
    proper terminal outcomes recorded in the audit trail.

    BUG: P1 fix - merged coalesce tokens were missing terminal outcomes.
    """

    def test_fork_coalesce_merged_token_has_terminal_outcome(self) -> None:
        """Merged token from coalesce MUST have a terminal outcome.

        This is a P1 audit completeness requirement: every token must reach
        exactly one terminal state. The merged token from a coalesce is no
        exception - it must have either COMPLETED (if it reaches a sink) or
        COALESCED (if consumed by an outer coalesce).

        For a terminal coalesce (at end of pipeline), the merged token
        should have an outcome recorded so audit queries can trace its fate.
        """
        from elspeth.cli_helpers import instantiate_plugins_from_config
        from elspeth.core.config import CoalesceSettings, ElspethSettings, GateSettings
        from elspeth.core.dag import ExecutionGraph
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from tests.conftest import as_sink, as_source

        db = LandscapeDB.in_memory()

        # Simple fork -> coalesce -> sink pipeline
        source = _ListSource([{"value": 42}])
        sink = _CollectSink()

        settings = ElspethSettings(
            source={"plugin": "null"},
            gates=[
                GateSettings(
                    name="fork_gate",
                    condition="True",  # Always fork
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["branch_a", "branch_b"],
                ),
            ],
            sinks={
                "output": {
                    "plugin": "json",
                    "options": {"path": "/dev/null", "schema": {"fields": "dynamic"}},
                },
            },
            coalesce=[
                CoalesceSettings(
                    name="merge_branches",
                    branches=["branch_a", "branch_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
            default_sink="output",
        )

        plugins = instantiate_plugins_from_config(settings)
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"output": as_sink(sink)},
            gates=list(settings.gates),
        )

        orchestrator = Orchestrator(db)
        run = orchestrator.run(config, graph=graph, settings=settings)

        # Verify the pipeline ran correctly
        assert run.rows_processed == 1
        assert run.rows_forked == 1
        assert run.rows_coalesced == 1
        assert len(sink.results) == 1, "Merged token should have been written to sink"

        # THE CRITICAL ASSERTION: Audit sweep MUST pass
        # This will fail if merged token is missing terminal outcome
        assert_audit_sweep_clean(db, run.run_id)

    def test_fork_coalesce_all_tokens_have_correct_outcomes(self) -> None:
        """Verify each token type in fork/coalesce has correct outcome.

        Expected outcomes:
        - Parent token: FORKED (terminal)
        - Fork children (consumed by coalesce): COALESCED (terminal)
        - Merged token: COMPLETED (terminal) when it reaches sink
        """
        from sqlalchemy import text

        from elspeth.cli_helpers import instantiate_plugins_from_config
        from elspeth.core.config import CoalesceSettings, ElspethSettings, GateSettings
        from elspeth.core.dag import ExecutionGraph
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from tests.conftest import as_sink, as_source

        db = LandscapeDB.in_memory()

        source = _ListSource([{"value": 42}])
        sink = _CollectSink()

        settings = ElspethSettings(
            source={"plugin": "null"},
            gates=[
                GateSettings(
                    name="fork_gate",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["branch_a", "branch_b"],
                ),
            ],
            sinks={
                "output": {
                    "plugin": "json",
                    "options": {"path": "/dev/null", "schema": {"fields": "dynamic"}},
                },
            },
            coalesce=[
                CoalesceSettings(
                    name="merge_branches",
                    branches=["branch_a", "branch_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
            default_sink="output",
        )

        plugins = instantiate_plugins_from_config(settings)
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"output": as_sink(sink)},
            gates=list(settings.gates),
        )

        orchestrator = Orchestrator(db)
        run = orchestrator.run(config, graph=graph, settings=settings)

        # Analyze all tokens and their outcomes
        with db.connection() as conn:
            # Get all tokens for this run
            all_tokens = conn.execute(
                text("""
                    SELECT t.token_id, t.fork_group_id, t.join_group_id, t.branch_name
                    FROM tokens t
                    JOIN rows r ON r.row_id = t.row_id
                    WHERE r.run_id = :run_id
                """),
                {"run_id": run.run_id},
            ).fetchall()

            # Get all outcomes for this run
            all_outcomes = conn.execute(
                text("""
                    SELECT token_id, outcome, is_terminal, fork_group_id, join_group_id, sink_name
                    FROM token_outcomes
                    WHERE run_id = :run_id
                """),
                {"run_id": run.run_id},
            ).fetchall()

        # Build outcome lookup
        outcomes_by_token = {o[0]: o for o in all_outcomes}

        # Verify each token has an outcome
        for token in all_tokens:
            token_id = token[0]
            fork_group_id = token[1]
            join_group_id = token[2]
            branch_name = token[3]

            assert token_id in outcomes_by_token, (
                f"Token {token_id} (fork_group={fork_group_id}, join_group={join_group_id}, "
                f"branch={branch_name}) has NO terminal outcome! "
                f"Every token must reach exactly one terminal state."
            )

            outcome_row = outcomes_by_token[token_id]
            outcome = outcome_row[1]
            is_terminal = outcome_row[2]

            assert is_terminal == 1, (
                f"Token {token_id} has outcome {outcome} but is_terminal={is_terminal}. Expected is_terminal=1 for all final outcomes."
            )
