"""Tests for lineage query functionality."""

from datetime import UTC, datetime

from elspeth.contracts.schema import SchemaConfig

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"fields": "dynamic"})


class TestLineageResult:
    """Tests for LineageResult data structure."""

    def test_lineage_result_exists(self) -> None:
        """LineageResult can be imported."""
        from elspeth.core.landscape.lineage import LineageResult

        assert LineageResult is not None

    def test_lineage_result_fields(self) -> None:
        """LineageResult has expected fields."""
        from elspeth.contracts import RowLineage, Token
        from elspeth.core.landscape.lineage import LineageResult

        now = datetime.now(UTC)
        result = LineageResult(
            token=Token(
                token_id="t1",
                row_id="r1",
                created_at=now,
            ),
            source_row=RowLineage(
                row_id="r1",
                run_id="run1",
                source_node_id="src",
                row_index=0,
                source_data_hash="abc",
                created_at=now,
                source_data={"field": "value"},
                payload_available=True,
            ),
            node_states=[],
            routing_events=[],
            calls=[],
            parent_tokens=[],
        )
        assert result.token.token_id == "t1"
        assert result.source_row.row_id == "r1"
        assert result.source_row.payload_available is True


class TestExplainFunction:
    """Tests for explain() lineage query function."""

    def test_explain_exists(self) -> None:
        """explain function can be imported."""
        from elspeth.core.landscape.lineage import explain

        assert callable(explain)

    def test_explain_returns_lineage_result(self) -> None:
        """explain returns LineageResult."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import LineageResult, explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        # Setup: create a minimal run with one row
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="sha256-rfc8785-v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={"id": 1},
        )
        token = recorder.create_token(row_id=row.row_id)
        recorder.complete_run(run.run_id, status="completed")

        # Query lineage
        result = explain(recorder, run_id=run.run_id, token_id=token.token_id)

        assert isinstance(result, LineageResult)
        assert result.token.token_id == token.token_id
        assert result.source_row.row_id == row.row_id

    def test_explain_by_row_id(self) -> None:
        """explain can query by row_id instead of token_id."""
        from elspeth.contracts.enums import RowOutcome
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="sha256-rfc8785-v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={"id": 1},
        )
        token = recorder.create_token(row_id=row.row_id)

        # Record terminal outcome (required for explain to work)
        recorder.record_token_outcome(
            token_id=token.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )

        recorder.complete_run(run.run_id, status="completed")

        # Query by row_id (token must exist but we don't use it directly)
        result = explain(recorder, run_id=run.run_id, row_id=row.row_id)

        assert result is not None
        assert result.source_row.row_id == row.row_id

    def test_explain_nonexistent_returns_none(self) -> None:
        """explain returns None for nonexistent token."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        result = explain(recorder, run_id="fake", token_id="fake")
        assert result is None

    def test_explain_fork_with_sink_disambiguation(self) -> None:
        """explain can disambiguate forked tokens by sink name."""
        import pytest

        from elspeth.contracts.enums import RowOutcome
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        # Setup: create run with one source row
        run = recorder.begin_run(config={}, canonical_version="sha256-rfc8785-v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={"id": 1},
        )

        # Fork the row to two sinks
        token_a = recorder.create_token(row_id=row.row_id)
        token_b = recorder.create_token(row_id=row.row_id)

        # Record terminal outcomes for both tokens at different sinks
        recorder.record_token_outcome(
            token_id=token_a.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.ROUTED,
            sink_name="sink_a",
        )
        recorder.record_token_outcome(
            token_id=token_b.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.ROUTED,
            sink_name="sink_b",
        )

        recorder.complete_run(run.run_id, status="completed")

        # Query with sink disambiguation should work
        result_a = explain(recorder, run_id=run.run_id, row_id=row.row_id, sink="sink_a")
        assert result_a is not None
        assert result_a.token.token_id == token_a.token_id

        result_b = explain(recorder, run_id=run.run_id, row_id=row.row_id, sink="sink_b")
        assert result_b is not None
        assert result_b.token.token_id == token_b.token_id

        # Query without sink should raise ValueError (ambiguous)
        with pytest.raises(ValueError, match="has 2 terminal tokens"):
            explain(recorder, run_id=run.run_id, row_id=row.row_id)

    def test_explain_single_terminal_path_works_without_sink(self) -> None:
        """explain by row_id works when row has single terminal token."""
        from elspeth.contracts.enums import RowOutcome
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="sha256-rfc8785-v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={"id": 1},
        )
        token = recorder.create_token(row_id=row.row_id)

        # Record single terminal outcome
        recorder.record_token_outcome(
            token_id=token.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )

        recorder.complete_run(run.run_id, status="completed")

        # Query without sink should work (only one terminal token)
        result = explain(recorder, run_id=run.run_id, row_id=row.row_id)
        assert result is not None
        assert result.token.token_id == token.token_id

    def test_explain_nonexistent_sink_returns_none(self) -> None:
        """explain returns None when specified sink has no tokens."""
        from elspeth.contracts.enums import RowOutcome
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="sha256-rfc8785-v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={"id": 1},
        )
        token = recorder.create_token(row_id=row.row_id)

        recorder.record_token_outcome(
            token_id=token.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="actual_sink",
        )

        recorder.complete_run(run.run_id, status="completed")

        # Query for sink that doesn't exist
        result = explain(recorder, run_id=run.run_id, row_id=row.row_id, sink="nonexistent")
        assert result is None

    def test_explain_buffered_tokens_returns_none(self) -> None:
        """explain returns None when all tokens are buffered (non-terminal)."""
        from elspeth.contracts.enums import RowOutcome
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="sha256-rfc8785-v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={"id": 1},
        )
        token = recorder.create_token(row_id=row.row_id)

        # Record non-terminal outcome (BUFFERED)
        recorder.record_token_outcome(
            token_id=token.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.BUFFERED,
            sink_name=None,
        )

        # Query should return None (row still processing)
        result = explain(recorder, run_id=run.run_id, row_id=row.row_id)
        assert result is None

    def test_explain_multiple_tokens_same_sink_raises(self) -> None:
        """explain raises when multiple tokens reach the same sink (expand scenario)."""
        import pytest

        from elspeth.contracts.enums import RowOutcome
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.lineage import explain
        from elspeth.core.landscape.recorder import LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="sha256-rfc8785-v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={"id": 1},
        )

        # Create multiple tokens that all go to the same sink (expand scenario)
        token_1 = recorder.create_token(row_id=row.row_id)
        token_2 = recorder.create_token(row_id=row.row_id)
        token_3 = recorder.create_token(row_id=row.row_id)

        for token in [token_1, token_2, token_3]:
            recorder.record_token_outcome(
                token_id=token.token_id,
                run_id=run.run_id,
                outcome=RowOutcome.COMPLETED,
                sink_name="same_sink",
            )

        # Should raise ValueError listing the ambiguous tokens
        with pytest.raises(ValueError, match="has 3 tokens at sink 'same_sink'"):
            explain(recorder, run_id=run.run_id, row_id=row.row_id, sink="same_sink")
