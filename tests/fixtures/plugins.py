# tests/fixtures/plugins.py
"""Consolidated test plugins — one canonical definition per plugin.

Eliminates the 3 duplicate ListSource/CollectSink definitions from v1.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from pydantic import ConfigDict

from elspeth.contracts import ArtifactDescriptor, PluginSchema, SourceRow
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.results import TransformResult
from tests.fixtures.base_classes import _TestSchema, _TestSinkBase, _TestSourceBase


class _EngineTestSchema(PluginSchema):
    """Dynamic schema for engine-level test plugins."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class ListSource(_TestSourceBase):
    """Source that yields rows from a list.

    Usage:
        source = ListSource([{"value": 1}, {"value": 2}])
        source = ListSource([{"value": 1}], name="my_source")
    """

    output_schema = _EngineTestSchema

    def __init__(self, data: list[dict[str, Any]], name: str = "list_source") -> None:
        super().__init__()
        self._data = data
        self.name = name

    def on_start(self, ctx: Any) -> None:
        pass

    def load(self, ctx: Any) -> Iterator[SourceRow]:
        yield from self.wrap_rows(self._data)

    def close(self) -> None:
        pass


class CollectSink(_TestSinkBase):
    """Sink that collects results into a list.

    Usage:
        sink = CollectSink()
        sink = CollectSink("output_sink")
        sink = CollectSink("output", node_id="sink_node_123")
    """

    def __init__(self, name: str = "collect", *, node_id: str | None = None) -> None:
        self.name = name
        self.node_id = node_id
        self.results: list[dict[str, Any]] = []
        self._artifact_counter = 0

    @property
    def rows_written(self) -> list[dict[str, Any]]:
        """Alias for results — some tests use this name."""
        return self.results

    def on_start(self, ctx: Any) -> None:
        pass

    def on_complete(self, ctx: Any) -> None:
        pass

    def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
        self.results.extend(rows)
        self._artifact_counter += 1
        return ArtifactDescriptor.for_file(
            path=f"memory://{self.name}_{self._artifact_counter}",
            size_bytes=len(str(rows)),
            content_hash=f"hash_{self._artifact_counter}",
        )

    def close(self) -> None:
        pass


class PassTransform(BaseTransform):
    """Identity transform — passes rows through unchanged."""

    name = "pass_transform"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def __init__(self) -> None:
        super().__init__({"schema": {"mode": "observed"}})

    def process(self, row: Any, ctx: Any) -> TransformResult:
        return TransformResult.success(row, success_reason={"action": "passthrough"})


class FailTransform(BaseTransform):
    """Transform that always returns an error result."""

    name = "fail_transform"
    input_schema = _TestSchema
    output_schema = _TestSchema
    _on_error = "discard"

    def __init__(self, error_reason: str = "always_fail") -> None:
        super().__init__({"schema": {"mode": "observed"}})
        self._error_reason = error_reason

    def process(self, row: Any, ctx: Any) -> TransformResult:
        return TransformResult.error({"reason": self._error_reason})


class ConditionalErrorTransform(BaseTransform):
    """Transform that errors on rows where 'fail' key is truthy."""

    name = "conditional_error"
    input_schema = _TestSchema
    output_schema = _TestSchema
    _on_error = "discard"

    def __init__(self) -> None:
        super().__init__({"schema": {"mode": "observed"}})

    def process(self, row: Any, ctx: Any) -> TransformResult:
        if row["fail"]:
            return TransformResult.error({"reason": "conditional_error"})
        return TransformResult.success(row, success_reason={"action": "test"})


class CountingTransform(BaseTransform):
    """Transform that counts invocations (for retry testing)."""

    name = "counting_transform"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def __init__(self) -> None:
        super().__init__({"schema": {"mode": "observed"}})
        self.call_count = 0

    def process(self, row: Any, ctx: Any) -> TransformResult:
        self.call_count += 1
        return TransformResult.success(row, success_reason={"action": "counted"})


class SlowTransform(BaseTransform):
    """Transform with configurable delay (for timeout testing)."""

    name = "slow_transform"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def __init__(self, delay_seconds: float = 0.1) -> None:
        super().__init__({"schema": {"mode": "observed"}})
        self._delay = delay_seconds

    def process(self, row: Any, ctx: Any) -> TransformResult:
        import time

        time.sleep(self._delay)
        return TransformResult.success(row, success_reason={"action": "delayed"})


class ErrorOnNthTransform(BaseTransform):
    """Transform that errors on the Nth invocation (for retry integration)."""

    name = "error_on_nth"
    input_schema = _TestSchema
    output_schema = _TestSchema
    _on_error = "discard"

    def __init__(self, error_on: int = 1) -> None:
        super().__init__({"schema": {"mode": "observed"}})
        self._error_on = error_on
        self._call_count = 0

    def process(self, row: Any, ctx: Any) -> TransformResult:
        self._call_count += 1
        if self._call_count == self._error_on:
            return TransformResult.error({"reason": "nth_error", "n": self._error_on}, retryable=True)
        return TransformResult.success(row, success_reason={"action": "passed"})


class RoutingGate:
    """Gate that routes based on a field value.

    Usage:
        gate = RoutingGate("category", {"A": "sink_a", "B": "sink_b"})
    """

    name = "routing_gate"
    input_schema = _TestSchema
    output_schema = _TestSchema
    config: ClassVar[dict[str, Any]] = {"schema": {"mode": "observed"}}
    node_id: str | None = None
    determinism = "deterministic"
    plugin_version = "1.0.0"

    def __init__(self, field: str, route_map: dict[str, str], default: str = "continue") -> None:
        self._field = field
        self._route_map = route_map
        self._default = default

    def evaluate(self, row: Any, ctx: Any) -> Any:
        from elspeth.contracts.results import GateResult
        from elspeth.contracts.routing import RoutingAction

        value = row[self._field] if isinstance(row, dict) else row.to_dict()[self._field]
        sink = self._route_map.get(str(value))
        if sink:
            pipeline_row = row if not isinstance(row, dict) else None
            if pipeline_row is None:
                from elspeth.testing import make_row

                pipeline_row = make_row(row if isinstance(row, dict) else row.to_dict())
            return GateResult(row=pipeline_row, action=RoutingAction.route_to_sink(sink))
        pipeline_row = row if not isinstance(row, dict) else None
        if pipeline_row is None:
            from elspeth.testing import make_row

            pipeline_row = make_row(row if isinstance(row, dict) else row.to_dict())
        return GateResult(row=pipeline_row, action=RoutingAction.continue_())

    def on_start(self, ctx: Any) -> None:
        pass

    def on_complete(self, ctx: Any) -> None:
        pass

    def close(self) -> None:
        pass
