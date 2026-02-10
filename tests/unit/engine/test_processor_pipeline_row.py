# tests/unit/engine/test_processor_pipeline_row.py
"""Tests for RowProcessor with PipelineRow support (Task 6)."""

from unittest.mock import MagicMock, Mock

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.contracts.types import NodeID
from elspeth.engine.processor import DAGTraversalContext
from elspeth.testing import make_field, make_row, make_source_row


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        fields=(
            make_field(
                "amount",
                python_type=int,
                original_name="'Amount'",
                required=True,
                source="declared",
            ),
        ),
        mode="OBSERVED",
        locked=True,
    )


def _make_mock_recorder() -> MagicMock:
    """Create a mock LandscapeRecorder."""
    recorder = MagicMock()
    recorder.create_row.return_value = Mock(row_id="row_001")
    recorder.create_token.return_value = Mock(token_id="token_001")
    return recorder


def _make_mock_span_factory() -> MagicMock:
    """Create a mock SpanFactory."""
    span_factory = MagicMock()
    span_factory.row_span.return_value.__enter__ = Mock()
    # Never suppress processor exceptions in tests.
    span_factory.row_span.return_value.__exit__ = Mock(return_value=False)
    return span_factory


def _empty_traversal(source_node_id: str = "source_001") -> DAGTraversalContext:
    source_node = NodeID(source_node_id)
    return DAGTraversalContext(
        node_step_map={source_node: 0},
        node_to_plugin={},
        first_transform_node_id=None,
        node_to_next={source_node: None},
        coalesce_node_map={},
    )


class TestRowProcessorPipelineRow:
    """Tests for RowProcessor.process_row() with SourceRow."""

    def test_process_row_accepts_source_row(self) -> None:
        """process_row should accept SourceRow and pass it to create_initial_token."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        contract = _make_contract()
        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
            source_on_success="default",
            traversal=_empty_traversal(),
        )

        source_row = make_source_row({"amount": 100}, contract=contract)
        ctx = PluginContext(run_id="run_001", config={})

        # No transforms - token should be created and completed immediately
        processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )

        # Should have created a row and token via recorder
        recorder.create_row.assert_called_once()
        recorder.create_token.assert_called_once()

    def test_process_row_creates_pipeline_row(self) -> None:
        """process_row should create token with PipelineRow containing contract."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        contract = _make_contract()
        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
            source_on_success="default",
            traversal=_empty_traversal(),
        )

        source_row = make_source_row({"amount": 100}, contract=contract)
        ctx = PluginContext(run_id="run_001", config={})

        results = processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )

        # Result should have token with PipelineRow
        assert len(results) >= 1
        result = results[0]
        assert isinstance(result.token.row_data, PipelineRow)
        assert result.token.row_data["amount"] == 100
        assert result.token.row_data.contract is contract

    def test_process_row_requires_contract_on_source_row(self) -> None:
        """process_row should raise if SourceRow has no contract.

        The error propagates from TokenManager.create_initial_token(),
        which enforces this requirement.
        """
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
            source_on_success="default",
            traversal=_empty_traversal(),
        )

        # SourceRow without contract -- uses SourceRow.valid directly because
        # make_source_row auto-creates a contract when contract=None
        from elspeth.contracts import SourceRow

        source_row = SourceRow.valid({"amount": 100}, contract=None)
        ctx = PluginContext(run_id="run_001", config={})

        with pytest.raises(ValueError, match="must have contract"):
            processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[],
                ctx=ctx,
            )


class TestRowProcessorExistingRow:
    """Tests for RowProcessor.process_existing_row() with PipelineRow."""

    def test_process_existing_row_accepts_pipeline_row(self) -> None:
        """process_existing_row should accept PipelineRow for resume scenarios."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        contract = _make_contract()
        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
            source_on_success="default",
            traversal=_empty_traversal(),
        )

        # PipelineRow for resume (row already exists in database)
        row_data = make_row({"amount": 100}, contract=contract)
        ctx = PluginContext(run_id="run_001", config={})

        results = processor.process_existing_row(
            row_id="existing_row_001",
            row_data=row_data,
            transforms=[],
            ctx=ctx,
        )

        # Should create token for existing row (NOT create_row)
        recorder.create_token.assert_called_once()
        recorder.create_row.assert_not_called()

        # Result should have token with PipelineRow
        assert len(results) >= 1
        result = results[0]
        assert isinstance(result.token.row_data, PipelineRow)
        assert result.token.row_data.contract is contract
