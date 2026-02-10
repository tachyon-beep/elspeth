"""Tests for plugin base class PipelineRow signatures."""

from typing import get_type_hints

from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.base import BaseSink, BaseTransform


class TestBaseClassSignatures:
    """Verify base class signatures use PipelineRow."""

    def test_base_transform_process_accepts_pipeline_row(self) -> None:
        """BaseTransform.process() should accept PipelineRow."""
        hints = get_type_hints(BaseTransform.process)
        assert hints["row"] is PipelineRow

    def test_base_sink_write_accepts_list_of_dicts(self) -> None:
        """BaseSink.write() should still accept list[dict] (not PipelineRow)."""
        hints = get_type_hints(BaseSink.write)
        # Sinks receive extracted dicts, not PipelineRow
        assert "dict" in str(hints["rows"]).lower()
