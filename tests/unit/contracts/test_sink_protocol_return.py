"""Tests for SinkProtocol.write() returning SinkWriteResult."""

from __future__ import annotations

from typing import get_type_hints

import elspeth.contracts.plugin_protocols as proto_mod
from elspeth.contracts.contexts import SinkContext
from elspeth.contracts.diversion import SinkWriteResult
from elspeth.contracts.plugin_protocols import SinkProtocol
from elspeth.contracts.results import ArtifactDescriptor


def _resolve_write_hints() -> dict[str, type]:
    """Resolve type hints for SinkProtocol.write(), including TYPE_CHECKING imports."""
    ns = {
        **vars(proto_mod),
        "SinkContext": SinkContext,
        "ArtifactDescriptor": ArtifactDescriptor,
        "SinkWriteResult": SinkWriteResult,
    }
    return get_type_hints(SinkProtocol.write, globalns=ns)


class TestSinkProtocolReturn:
    def test_write_return_annotation_is_sink_write_result(self) -> None:
        """SinkProtocol.write() must be annotated to return SinkWriteResult."""
        hints = _resolve_write_hints()
        assert hints["return"] is SinkWriteResult
