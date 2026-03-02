"""Tests for plugin base class signatures and phase-based protocol alignment.

Uses localns to resolve TYPE_CHECKING-only annotations (protocol types
are not in the runtime namespace due to from __future__ import annotations).
"""

from typing import Any, get_origin, get_type_hints

from elspeth.contracts.contexts import (
    LifecycleContext,
    SinkContext,
    SourceContext,
    TransformContext,
)
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.infrastructure.base import BaseSink, BaseSource, BaseTransform
from elspeth.plugins.infrastructure.results import TransformResult


class TestBaseClassSignatures:
    """Verify base class signatures use PipelineRow and phase-based protocols."""

    def _get_hints(self, method: object) -> dict[str, Any]:
        """Resolve type hints with protocol types available."""
        return get_type_hints(
            method,
            localns={
                "TransformContext": TransformContext,
                "LifecycleContext": LifecycleContext,
                "SinkContext": SinkContext,
                "SourceContext": SourceContext,
                "TransformResult": TransformResult,
            },
        )

    # --- BaseTransform ---

    def test_base_transform_process_accepts_pipeline_row(self) -> None:
        """BaseTransform.process() should accept PipelineRow."""
        hints = self._get_hints(BaseTransform.process)
        assert hints["row"] is PipelineRow

    def test_base_transform_process_accepts_transform_context(self) -> None:
        """BaseTransform.process() should accept TransformContext (not PluginContext)."""
        hints = self._get_hints(BaseTransform.process)
        assert hints["ctx"] is TransformContext

    def test_base_transform_on_start_accepts_lifecycle_context(self) -> None:
        """BaseTransform.on_start() should accept LifecycleContext."""
        hints = self._get_hints(BaseTransform.on_start)
        assert hints["ctx"] is LifecycleContext

    def test_base_transform_on_complete_accepts_lifecycle_context(self) -> None:
        """BaseTransform.on_complete() should accept LifecycleContext."""
        hints = self._get_hints(BaseTransform.on_complete)
        assert hints["ctx"] is LifecycleContext

    # --- BaseSink ---

    def test_base_sink_write_accepts_list_of_dicts(self) -> None:
        """BaseSink.write() should accept list[dict[str, Any]] (not PipelineRow)."""
        hints = self._get_hints(BaseSink.write)
        assert get_origin(hints["rows"]) is list

    def test_base_sink_write_accepts_sink_context(self) -> None:
        """BaseSink.write() should accept SinkContext (not PluginContext)."""
        hints = self._get_hints(BaseSink.write)
        assert hints["ctx"] is SinkContext

    def test_base_sink_on_start_accepts_lifecycle_context(self) -> None:
        """BaseSink.on_start() should accept LifecycleContext."""
        hints = self._get_hints(BaseSink.on_start)
        assert hints["ctx"] is LifecycleContext

    def test_base_sink_on_complete_accepts_lifecycle_context(self) -> None:
        """BaseSink.on_complete() should accept LifecycleContext."""
        hints = self._get_hints(BaseSink.on_complete)
        assert hints["ctx"] is LifecycleContext

    # --- BaseSource ---

    def test_base_source_load_accepts_source_context(self) -> None:
        """BaseSource.load() should accept SourceContext (not PluginContext)."""
        hints = self._get_hints(BaseSource.load)
        assert hints["ctx"] is SourceContext

    def test_base_source_on_start_accepts_lifecycle_context(self) -> None:
        """BaseSource.on_start() should accept LifecycleContext."""
        hints = self._get_hints(BaseSource.on_start)
        assert hints["ctx"] is LifecycleContext

    def test_base_source_on_complete_accepts_lifecycle_context(self) -> None:
        """BaseSource.on_complete() should accept LifecycleContext."""
        hints = self._get_hints(BaseSource.on_complete)
        assert hints["ctx"] is LifecycleContext
