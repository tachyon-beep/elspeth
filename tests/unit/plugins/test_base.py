# tests/plugins/test_base.py
"""Tests for plugin base classes."""

from typing import Any

import pytest

from elspeth.contracts import PipelineRow
from elspeth.testing import make_pipeline_row


class TestBaseTransform:
    """Base class for transforms."""

    def test_base_transform_creates_tokens_default_false(self) -> None:
        """BaseTransform.creates_tokens defaults to False."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseTransform
        from elspeth.plugins.results import TransformResult

        class SimpleTransform(BaseTransform):
            name = "simple"
            input_schema = None  # type: ignore[assignment]  # Not needed for this test
            output_schema = None  # type: ignore[assignment]

            def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
                return TransformResult.success(row.to_dict(), success_reason={"action": "test"})

        transform = SimpleTransform({})
        assert transform.creates_tokens is False

    def test_base_transform_creates_tokens_settable(self) -> None:
        """BaseTransform.creates_tokens can be overridden to True."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseTransform
        from elspeth.plugins.results import TransformResult

        class ExpandingTransform(BaseTransform):
            name = "expander"
            creates_tokens = True  # Deaggregation transform
            input_schema = None  # type: ignore[assignment]
            output_schema = None  # type: ignore[assignment]

            def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
                row_dict = row.to_dict()
                return TransformResult.success_multi([row_dict, row_dict], success_reason={"action": "expand"})

        transform = ExpandingTransform({})
        assert transform.creates_tokens is True

    def test_base_transform_process_raises_not_implemented(self) -> None:
        """BaseTransform.process() raises NotImplementedError when called directly.

        Note: BaseTransform is no longer fully abstract (commit fb63cc3b) to allow
        batch transforms to override process() with different signatures. Subclasses
        must still implement process() - the base implementation raises NotImplementedError.
        """
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseTransform

        # Create a minimal concrete subclass that doesn't override process()
        class IncompleteTransform(BaseTransform):
            name = "incomplete"
            input_schema = None  # type: ignore[assignment]
            output_schema = None  # type: ignore[assignment]

        transform = IncompleteTransform({})
        ctx = PluginContext(run_id="test", config={})
        row = make_pipeline_row({"x": 1})

        # Calling process() should raise NotImplementedError
        with pytest.raises(NotImplementedError) as exc_info:
            transform.process(row, ctx)

        assert "IncompleteTransform must implement process()" in str(exc_info.value)

    def test_subclass_implementation(self) -> None:
        from elspeth.contracts import PluginSchema
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseTransform
        from elspeth.plugins.results import TransformResult

        class InputSchema(PluginSchema):
            x: int

        class OutputSchema(PluginSchema):
            x: int
            doubled: int

        class DoubleTransform(BaseTransform):
            name = "double"
            input_schema = InputSchema
            output_schema = OutputSchema

            def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
                return TransformResult.success(
                    {
                        "x": row["x"],
                        "doubled": row["x"] * 2,
                    },
                    success_reason={"action": "test"},
                )

        transform = DoubleTransform({"some": "config"})
        ctx = PluginContext(run_id="test", config={})

        result = transform.process(make_pipeline_row({"x": 21}), ctx)
        assert result.row == {"x": 21, "doubled": 42}

    def test_lifecycle_hooks_exist(self) -> None:
        from elspeth.plugins.base import BaseTransform

        # These should exist as no-op methods
        assert hasattr(BaseTransform, "on_start")
        assert hasattr(BaseTransform, "on_complete")


class TestBaseAggregationDeleted:
    """Verify BaseAggregation has been deleted (aggregation is structural now)."""

    def test_base_aggregation_deleted(self) -> None:
        """BaseAggregation should be deleted - use is_batch_aware=True on BaseTransform."""
        import elspeth.plugins.base as base

        assert not hasattr(base, "BaseAggregation"), "BaseAggregation should be deleted - use is_batch_aware=True on BaseTransform"


class TestBaseSink:
    """Base class for sinks."""

    def test_base_sink_implementation(self) -> None:
        from elspeth.contracts import ArtifactDescriptor, PluginSchema
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseSink

        class InputSchema(PluginSchema):
            value: int

        class MemorySink(BaseSink):
            name = "memory"
            input_schema = InputSchema
            idempotent = True

            def __init__(self, config: dict[str, Any]) -> None:
                super().__init__(config)
                self.rows: list[dict[str, Any]] = []

            def write(self, rows: list[dict[str, Any]], ctx: PluginContext) -> ArtifactDescriptor:
                self.rows.extend(rows)
                return ArtifactDescriptor.for_file(
                    path="/tmp/memory",
                    content_hash="test",
                    size_bytes=len(str(rows)),
                )

            def flush(self) -> None:
                pass

            def close(self) -> None:
                pass

        sink = MemorySink({})
        ctx = PluginContext(run_id="test", config={})

        artifact = sink.write([{"value": 1}, {"value": 2}], ctx)

        assert len(sink.rows) == 2
        assert sink.rows[0] == {"value": 1}
        assert isinstance(artifact, ArtifactDescriptor)

    def test_base_sink_batch_write_signature(self) -> None:
        """BaseSink.write() accepts batch and returns ArtifactDescriptor."""
        import inspect

        from elspeth.plugins.base import BaseSink

        sig = inspect.signature(BaseSink.write)
        params = list(sig.parameters.keys())

        assert "rows" in params, "write() should accept 'rows' (batch)"
        assert "row" not in params, "write() should NOT have 'row' parameter"

    def test_base_sink_batch_implementation(self) -> None:
        """Test BaseSink subclass with batch write."""
        from elspeth.contracts import ArtifactDescriptor, PluginSchema
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseSink

        class InputSchema(PluginSchema):
            value: int

        class BatchMemorySink(BaseSink):
            name = "batch_memory"
            input_schema = InputSchema
            idempotent = True

            def __init__(self, config: dict[str, Any]) -> None:
                super().__init__(config)
                self.rows: list[dict[str, Any]] = []

            def write(self, rows: list[dict[str, Any]], ctx: PluginContext) -> ArtifactDescriptor:
                self.rows.extend(rows)
                return ArtifactDescriptor.for_file(
                    path="/tmp/batch",
                    content_hash="hash123",
                    size_bytes=100,
                )

            def flush(self) -> None:
                pass

            def close(self) -> None:
                pass

        sink = BatchMemorySink({})
        ctx = PluginContext(run_id="test", config={})

        artifact = sink.write([{"value": 1}, {"value": 2}, {"value": 3}], ctx)

        assert len(sink.rows) == 3
        assert isinstance(artifact, ArtifactDescriptor)
        assert artifact.content_hash == "hash123"

    def test_base_sink_has_io_write_determinism(self) -> None:
        """BaseSink should have IO_WRITE determinism by default."""
        from elspeth.contracts import Determinism
        from elspeth.plugins.base import BaseSink

        assert BaseSink.determinism == Determinism.IO_WRITE


class TestBaseSource:
    """Base class for sources."""

    def test_base_source_implementation(self) -> None:
        from collections.abc import Iterator

        from elspeth.contracts import PluginSchema, SourceRow
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseSource

        class OutputSchema(PluginSchema):
            value: int

        class ListSource(BaseSource):
            name = "list"
            output_schema = OutputSchema

            def __init__(self, config: dict[str, Any]) -> None:
                super().__init__(config)
                self._data = config["data"]

            def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
                for _row in self._data:
                    yield SourceRow.valid(_row)

            def close(self) -> None:
                pass

        source = ListSource({"data": [{"value": 1}, {"value": 2}]})
        ctx = PluginContext(run_id="test", config={})

        rows = list(source.load(ctx))
        assert len(rows) == 2
        # All rows are SourceRow objects now
        assert rows[0].row == {"value": 1}
        assert rows[0].is_quarantined is False

    def test_base_source_has_metadata_attributes(self) -> None:
        from elspeth.contracts import Determinism
        from elspeth.plugins.base import BaseSource

        # Direct attribute access - will fail with AttributeError if missing
        assert BaseSource.determinism == Determinism.IO_READ
        assert BaseSource.plugin_version == "0.0.0"

    def test_subclass_can_override_metadata(self) -> None:
        from collections.abc import Iterator

        from elspeth.contracts import Determinism, PluginSchema
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseSource

        class OutputSchema(PluginSchema):
            value: int

        class CustomSource(BaseSource):
            name = "custom"
            output_schema = OutputSchema
            determinism = Determinism.DETERMINISTIC
            plugin_version = "2.0.0"

            def load(self, ctx: PluginContext) -> Iterator[dict[str, Any]]:  # type: ignore[override]
                yield {"value": 1}

            def close(self) -> None:
                pass

        source = CustomSource({})
        assert source.determinism == Determinism.DETERMINISTIC
        assert source.plugin_version == "2.0.0"


class TestNoValidationEnforcement:
    """Verify validation enforcement has been removed from base classes."""

    def test_plugins_instantiate_without_validation_call(self) -> None:
        """Plugins no longer require _validate_self_consistency() call.

        Validation now happens BEFORE instantiation (in PluginManager),
        not during construction (__init__ calling _validate_self_consistency).
        """
        from elspeth.contracts import PluginSchema
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.plugins.base import BaseTransform
        from elspeth.plugins.results import TransformResult

        class TestSchema(PluginSchema):
            x: int

        class NoValidationTransform(BaseTransform):
            name = "no_validation"
            input_schema = TestSchema
            output_schema = TestSchema

            def __init__(self, config: dict[str, Any]) -> None:
                super().__init__(config)
                # NOT calling self._validate_self_consistency()

            def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
                return TransformResult.success(row.to_dict(), success_reason={"action": "test"})

        # Should instantiate without RuntimeError
        plugin = NoValidationTransform({})
        assert plugin is not None
