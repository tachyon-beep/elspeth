# tests/fixtures/base_classes.py
"""Protocol-compliant test base classes.

Single canonical definition of base classes for test sources, sinks,
and transforms. Migrated from tests/conftest.py with no behavioral changes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, cast

from elspeth.contracts import Determinism, PluginSchema, SourceRow

if TYPE_CHECKING:
    from elspeth.contracts import TransformResult
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.plugins.protocols import (
        BatchTransformProtocol,
        GateProtocol,
        SinkProtocol,
        SourceProtocol,
        TransformProtocol,
    )


class _TestSchema(PluginSchema):
    """Minimal schema for test fixtures."""

    pass


class _TestSourceBase:
    """Base class for test sources implementing SourceProtocol.

    Provides all required Protocol attributes and lifecycle methods.
    Child classes must provide: name, output_schema, load(ctx).
    """

    name: str
    output_schema: type[PluginSchema]
    node_id: str | None = None
    determinism = Determinism.DETERMINISTIC
    plugin_version = "1.0.0"
    _on_validation_failure: str = "discard"
    on_success: str = "default"

    def __init__(self) -> None:
        self.config: dict[str, Any] = {"schema": {"mode": "observed"}}
        self._schema_contract: SchemaContract | None = None

    def wrap_rows(self, rows: list[dict[str, Any]]) -> Iterator[SourceRow]:
        """Wrap plain dicts in SourceRow.valid() as required by source protocol."""
        from elspeth.contracts.schema_contract import FieldContract, SchemaContract

        for row in rows:
            fields = tuple(
                FieldContract(
                    normalized_name=key,
                    original_name=key,
                    python_type=object,
                    required=False,
                    source="inferred",
                )
                for key in row
            )
            contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
            if self._schema_contract is None:
                self._schema_contract = contract
            yield SourceRow.valid(row, contract=contract)

    def on_start(self, ctx: Any) -> None:
        pass

    def on_complete(self, ctx: Any) -> None:
        pass

    def close(self) -> None:
        pass

    def get_field_resolution(self) -> tuple[dict[str, str], str | None] | None:
        return None

    def get_schema_contract(self) -> SchemaContract | None:
        return self._schema_contract


class CallbackSource(_TestSourceBase):
    """Source with callbacks for deterministic MockClock testing.

    Enables tests to advance a MockClock between row yields.
    """

    name: str = "callback_source"
    output_schema: type[PluginSchema] = _TestSchema

    def __init__(
        self,
        rows: list[dict[str, Any]],
        output_schema: type[PluginSchema] | None = None,
        after_yield_callback: Callable[[int], None] | None = None,
        source_name: str = "callback_source",
        on_success: str = "default",
    ) -> None:
        super().__init__()
        self._rows = rows
        self._after_yield_callback = after_yield_callback
        self.name = source_name
        self.on_success = on_success
        if output_schema is not None:
            self.output_schema = output_schema

    def load(self, ctx: Any) -> Iterator[SourceRow]:
        from elspeth.contracts.schema_contract import FieldContract, SchemaContract

        for i, row in enumerate(self._rows):
            fields = tuple(
                FieldContract(
                    normalized_name=key,
                    original_name=key,
                    python_type=object,
                    required=False,
                    source="inferred",
                )
                for key in row
            )
            contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
            yield SourceRow.valid(row, contract=contract)
            if self._after_yield_callback is not None:
                self._after_yield_callback(i)


class _TestSinkBase:
    """Base class for test sinks implementing SinkProtocol."""

    name: str
    input_schema: type[PluginSchema] = _TestSchema
    idempotent: bool = True
    node_id: str | None = None
    determinism = Determinism.DETERMINISTIC
    plugin_version = "1.0.0"

    def __init__(self) -> None:
        self.config: dict[str, Any] = {"schema": {"mode": "observed"}}

    def on_start(self, ctx: Any) -> None:
        pass

    def on_complete(self, ctx: Any) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class _TestTransformBase:
    """Base class for test transforms implementing TransformProtocol."""

    name: str
    input_schema: type[PluginSchema] = _TestSchema
    output_schema: type[PluginSchema] = _TestSchema
    node_id: str | None = None
    determinism = Determinism.DETERMINISTIC
    plugin_version = "1.0.0"
    is_batch_aware: bool = False
    creates_tokens: bool = False
    transforms_adds_fields: bool = False
    _on_error: str | None = None
    _on_success: str | None = None

    @property
    def on_error(self) -> str | None:
        """Error routing destination for this transform."""
        return self._on_error

    @property
    def on_success(self) -> str | None:
        """Success routing destination for this transform."""
        return self._on_success

    def __init__(self) -> None:
        self.config: dict[str, Any] = {"schema": {"mode": "observed"}}

    def on_start(self, ctx: Any) -> None:
        pass

    def on_complete(self, ctx: Any) -> None:
        pass

    def close(self) -> None:
        pass


# ─────────────────────────────────────────────────────────────────────────
# Type Cast Helpers
# ─────────────────────────────────────────────────────────────────────────


def as_source(source: Any) -> SourceProtocol:
    """Cast a test source to SourceProtocol."""
    return cast("SourceProtocol", source)


def as_transform(transform: Any) -> TransformProtocol:
    """Cast a test transform to TransformProtocol."""
    return cast("TransformProtocol", transform)


def as_batch_transform(transform: Any) -> BatchTransformProtocol:
    """Cast a test batch transform to BatchTransformProtocol."""
    return cast("BatchTransformProtocol", transform)


def as_sink(sink: Any) -> SinkProtocol:
    """Cast a test sink to SinkProtocol."""
    return cast("SinkProtocol", sink)


def as_gate(gate: Any) -> GateProtocol:
    """Cast a test gate to GateProtocol."""
    return cast("GateProtocol", gate)


def create_observed_contract(row: dict[str, Any]) -> SchemaContract:
    """Create an OBSERVED schema contract from a row."""
    from elspeth.contracts.schema_contract import FieldContract, SchemaContract

    fields = tuple(
        FieldContract(
            normalized_name=key,
            original_name=key,
            python_type=object,
            required=False,
            source="inferred",
        )
        for key in row
    )
    return SchemaContract(mode="OBSERVED", fields=fields, locked=True)


def as_transform_result(result: Any) -> TransformResult:
    """Assert and cast a result to TransformResult."""
    from elspeth.engine.batch_adapter import ExceptionResult

    if isinstance(result, ExceptionResult):
        raise AssertionError(f"Expected TransformResult but got ExceptionResult: {result.exception}\n{result.traceback}")
    return cast("TransformResult", result)
