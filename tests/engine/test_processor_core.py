# tests/engine/test_processor_core.py
"""Core RowProcessor tests for basic processing, token identity, and type handling.

This module contains foundational tests for RowProcessor:
- Basic row processing through transforms
- Error handling with on_error configuration
- Token identity preservation and accessibility
- Unknown plugin type detection

Test plugins inherit from base classes (BaseTransform) because the processor
uses isinstance() for type-safe plugin detection.
"""

from typing import Any

from elspeth.plugins.base import BaseTransform
from elspeth.plugins.context import PluginContext
from elspeth.plugins.results import (
    RowOutcome,
    TransformResult,
)
from tests.engine.conftest import DYNAMIC_SCHEMA, _TestSchema


class TestRowProcessor:
    """Row processing through pipeline."""

    def test_process_through_transforms(self) -> None:
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Register nodes
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform1 = recorder.register_node(
            run_id=run.run_id,
            plugin_name="double",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform2 = recorder.register_node(
            run_id=run.run_id,
            plugin_name="add_one",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class DoubleTransform(BaseTransform):
            name = "double"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                return TransformResult.success({"value": row["value"] * 2})

        class AddOneTransform(BaseTransform):
            name = "add_one"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                return TransformResult.success({"value": row["value"] + 1})

        ctx = PluginContext(run_id=run.run_id, config={})
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        results = processor.process_row(
            row_index=0,
            row_data={"value": 10},
            transforms=[
                DoubleTransform(transform1.node_id),
                AddOneTransform(transform2.node_id),
            ],
            ctx=ctx,
        )

        # Single result - no forks
        assert len(results) == 1
        result = results[0]

        # 10 * 2 = 20, 20 + 1 = 21
        assert result.final_data == {"value": 21}
        assert result.outcome == RowOutcome.COMPLETED

        # === P1: Audit trail verification ===
        # Note: COMPLETED token_outcomes are recorded by the orchestrator at sink level,
        # not by the processor. The processor records node_states for each transform.
        # Verify node_states for each transform
        states = recorder.get_node_states_for_token(result.token_id)
        assert len(states) == 2, "Should have 2 node_states (one per transform)"

        # Verify hashes for each state
        for state in states:
            assert state.input_hash is not None, "Input hash should be recorded"
            assert state.output_hash is not None, "Output hash should be recorded"
            assert state.status.value == "completed", "State should be completed"

        # Verify correct step indices (source is 0, transforms start at 1)
        step_indices = {s.step_index for s in states}
        assert step_indices == {1, 2}, "Steps should be 1 and 2"

    def test_process_single_transform(self) -> None:
        """Single transform processes correctly."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform = recorder.register_node(
            run_id=run.run_id,
            plugin_name="enricher",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class EnricherTransform(BaseTransform):
            name = "enricher"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                return TransformResult.success({**row, "enriched": True})

        ctx = PluginContext(run_id=run.run_id, config={})
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        results = processor.process_row(
            row_index=0,
            row_data={"name": "test"},
            transforms=[EnricherTransform(transform.node_id)],
            ctx=ctx,
        )

        # Single result - no forks
        assert len(results) == 1
        result = results[0]

        assert result.final_data == {"name": "test", "enriched": True}
        assert result.outcome == RowOutcome.COMPLETED
        # Check identity preserved
        assert result.token_id is not None
        assert result.row_id is not None

    def test_process_no_transforms(self) -> None:
        """No transforms passes through data unchanged."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        ctx = PluginContext(run_id=run.run_id, config={})
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        results = processor.process_row(
            row_index=0,
            row_data={"passthrough": True},
            transforms=[],
            ctx=ctx,
        )

        # Single result - no forks
        assert len(results) == 1
        result = results[0]

        assert result.final_data == {"passthrough": True}
        assert result.outcome == RowOutcome.COMPLETED

    def test_transform_error_without_on_error_raises(self) -> None:
        """Transform returning error without on_error configured raises RuntimeError."""
        import pytest

        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform = recorder.register_node(
            run_id=run.run_id,
            plugin_name="validator",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class ValidatorTransform(BaseTransform):
            name = "validator"
            input_schema = _TestSchema
            output_schema = _TestSchema
            # No _on_error configured - errors are bugs

            def __init__(self, node_id: str) -> None:
                super().__init__({})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                if row.get("value", 0) < 0:
                    return TransformResult.error({"message": "negative values not allowed"})
                return TransformResult.success(row)

        ctx = PluginContext(run_id=run.run_id, config={}, landscape=recorder)
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        # Without on_error configured, returning error is a bug - should raise
        with pytest.raises(RuntimeError) as exc_info:
            processor.process_row(
                row_index=0,
                row_data={"value": -5},
                transforms=[ValidatorTransform(transform.node_id)],
                ctx=ctx,
            )

        assert "no on_error configured" in str(exc_info.value)

    def test_transform_error_with_discard_returns_quarantined(self) -> None:
        """Transform error with on_error='discard' should return QUARANTINED."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform = recorder.register_node(
            run_id=run.run_id,
            plugin_name="validator",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class DiscardingValidator(BaseTransform):
            """Validator that discards errors (on_error='discard')."""

            name = "validator"
            input_schema = _TestSchema
            output_schema = _TestSchema
            _on_error = "discard"  # Intentionally discard errors

            def __init__(self, node_id: str) -> None:
                super().__init__({})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                if row.get("value", 0) < 0:
                    return TransformResult.error({"message": "negative values not allowed"})
                return TransformResult.success(row)

        ctx = PluginContext(run_id=run.run_id, config={}, landscape=recorder)
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        results = processor.process_row(
            row_index=0,
            row_data={"value": -5},
            transforms=[DiscardingValidator(transform.node_id)],
            ctx=ctx,
        )

        # Single result - no forks
        assert len(results) == 1
        result = results[0]

        # With on_error='discard', error becomes QUARANTINED (intentional rejection)
        assert result.outcome == RowOutcome.QUARANTINED
        # Original data preserved
        assert result.final_data == {"value": -5}

        # === P1: Audit trail verification for QUARANTINED ===
        # Verify token outcome was recorded with error_hash
        outcome = recorder.get_token_outcome(result.token_id)
        assert outcome is not None, "Token outcome should be recorded"
        assert outcome.outcome == RowOutcome.QUARANTINED, "Outcome should be QUARANTINED"
        assert outcome.error_hash is not None, "Error hash should be recorded for quarantined rows"
        assert outcome.is_terminal is True, "QUARANTINED is terminal"

        # Verify node_state was recorded as failed
        states = recorder.get_node_states_for_token(result.token_id)
        assert len(states) == 1, "Should have 1 node_state for the validator"
        state = states[0]
        assert state.status.value == "failed", "State should be failed"

    def test_transform_error_with_sink_returns_routed(self) -> None:
        """Transform error with on_error=sink_name should return ROUTED."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform = recorder.register_node(
            run_id=run.run_id,
            plugin_name="validator",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class RoutingValidator(BaseTransform):
            """Validator that routes errors to error_sink."""

            name = "validator"
            input_schema = _TestSchema
            output_schema = _TestSchema
            _on_error = "error_sink"  # Route errors to named sink

            def __init__(self, node_id: str) -> None:
                super().__init__({})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                if row.get("value", 0) < 0:
                    return TransformResult.error({"message": "negative values not allowed"})
                return TransformResult.success(row)

        ctx = PluginContext(run_id=run.run_id, config={}, landscape=recorder)
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        results = processor.process_row(
            row_index=0,
            row_data={"value": -5},
            transforms=[RoutingValidator(transform.node_id)],
            ctx=ctx,
        )

        # Single result - no forks
        assert len(results) == 1
        result = results[0]

        # With on_error='error_sink', error becomes ROUTED to that sink
        assert result.outcome == RowOutcome.ROUTED
        assert result.sink_name == "error_sink"
        # Original data preserved
        assert result.final_data == {"value": -5}

        # === P1: Audit trail verification for ROUTED ===
        # Verify token outcome was recorded with sink_name
        outcome = recorder.get_token_outcome(result.token_id)
        assert outcome is not None, "Token outcome should be recorded"
        assert outcome.outcome == RowOutcome.ROUTED, "Outcome should be ROUTED"
        assert outcome.sink_name == "error_sink", "Sink name should be recorded"
        assert outcome.is_terminal is True, "ROUTED is terminal"


class TestRowProcessorTokenIdentity:
    """Token identity is preserved and accessible."""

    def test_token_accessible_on_result(self) -> None:
        """RowResult provides access to full token info."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        ctx = PluginContext(run_id=run.run_id, config={})
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        results = processor.process_row(
            row_index=0,
            row_data={"test": "data"},
            transforms=[],
            ctx=ctx,
        )

        # Single result - no forks
        assert len(results) == 1
        result = results[0]

        # Can access token identity
        assert result.token is not None
        assert result.token.token_id is not None
        assert result.token.row_id is not None
        assert result.token.row_data == {"test": "data"}

        # Convenience properties work
        assert result.token_id == result.token.token_id
        assert result.row_id == result.token.row_id

    def test_step_counting_correct(self) -> None:
        """Step position is tracked correctly through pipeline."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform1 = recorder.register_node(
            run_id=run.run_id,
            plugin_name="t1",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform2 = recorder.register_node(
            run_id=run.run_id,
            plugin_name="t2",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class IdentityTransform(BaseTransform):
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, name: str, node_id: str) -> None:
                super().__init__({})
                self.name = name  # type: ignore[misc]
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                return TransformResult.success(row)

        ctx = PluginContext(run_id=run.run_id, config={})
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        results = processor.process_row(
            row_index=0,
            row_data={"value": 1},
            transforms=[
                IdentityTransform("t1", transform1.node_id),
                IdentityTransform("t2", transform2.node_id),
            ],
            ctx=ctx,
        )

        # Single result - no forks
        assert len(results) == 1
        result = results[0]

        assert result.outcome == RowOutcome.COMPLETED

        # Verify node states recorded with correct step indices
        states = recorder.get_node_states_for_token(result.token_id)
        assert len(states) == 2
        # Steps should be 1 and 2 (source is 0, transforms start at 1)
        step_indices = {s.step_index for s in states}
        assert step_indices == {1, 2}


class TestRowProcessorUnknownType:
    """Test handling of unknown plugin types."""

    def test_unknown_type_raises_type_error(self) -> None:
        """Unknown plugin types raise TypeError with helpful message."""
        import pytest

        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class NotAPlugin:
            """A class that doesn't inherit from any base class."""

            name = "fake"
            node_id = "fake_id"

            def process(self, row: dict[str, Any], ctx: PluginContext) -> None:
                pass

        ctx = PluginContext(run_id=run.run_id, config={})
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=source.node_id,
        )

        with pytest.raises(TypeError) as exc_info:
            processor.process_row(
                row_index=0,
                row_data={"value": 1},
                transforms=[NotAPlugin()],
                ctx=ctx,
            )

        assert "Unknown transform type: NotAPlugin" in str(exc_info.value)
        assert "BaseTransform" in str(exc_info.value)
        assert "BaseGate" in str(exc_info.value)
        # NOTE: BaseAggregation assertion removed in aggregation structural cleanup
