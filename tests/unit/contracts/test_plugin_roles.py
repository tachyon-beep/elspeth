"""Low-layer source/sink role helpers."""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.contracts.diversion import SinkWriteResult
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.plugin_roles import (
    sink_declared_required_fields,
    source_declared_guaranteed_fields,
)
from elspeth.contracts.results import SourceRow
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.infrastructure.base import BaseSink, BaseSource


def _contract(fields: tuple[str, ...]) -> SchemaContract:
    return SchemaContract(
        mode="OBSERVED",
        fields=tuple(
            FieldContract(
                normalized_name=name,
                original_name=name,
                python_type=str,
                required=True,
                source="inferred",
                nullable=False,
            )
            for name in fields
        ),
        locked=True,
    )


class _DeclaredSourceBase(BaseSource):
    name = "declared-source-base"
    output_schema = object
    declared_guaranteed_fields = frozenset({"customer_id"})

    def __init__(self) -> None:
        self.config = {}
        self.node_id = None

    def load(self, ctx: PluginContext):
        yield SourceRow.valid({"customer_id": "v"}, contract=_contract(("customer_id",)))

    def close(self) -> None:
        pass


class _InheritedDeclaredSource(_DeclaredSourceBase):
    pass


class _DeclaredSinkBase(BaseSink):
    name = "declared-sink-base"
    input_schema = object
    declared_required_fields = frozenset({"customer_id"})

    def __init__(self) -> None:
        self.config = {}
        self.node_id = None

    def write(self, rows: list[dict[str, Any]], ctx: PluginContext) -> SinkWriteResult:
        raise NotImplementedError

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class _InheritedDeclaredSink(_DeclaredSinkBase):
    pass


def test_source_declared_guaranteed_fields_uses_inherited_source_declaration() -> None:
    assert source_declared_guaranteed_fields(_InheritedDeclaredSource()) == frozenset({"customer_id"})


def test_source_declared_guaranteed_fields_rejects_non_source_even_when_attr_present() -> None:
    class _NotASource:
        name = "not-a-source"
        node_id = None
        declared_guaranteed_fields = frozenset({"customer_id"})

    assert source_declared_guaranteed_fields(_NotASource()) is None


def test_sink_declared_required_fields_uses_inherited_sink_declaration() -> None:
    assert sink_declared_required_fields(_InheritedDeclaredSink()) == frozenset({"customer_id"})


def test_sink_declared_required_fields_rejects_non_sink_even_when_attr_present() -> None:
    class _NotASink:
        name = "not-a-sink"
        node_id = None
        declared_required_fields = frozenset({"customer_id"})

    assert sink_declared_required_fields(_NotASink()) is None


@pytest.mark.parametrize(
    ("plugin", "expected"),
    [
        (_InheritedDeclaredSource(), frozenset({"customer_id"})),
        (_InheritedDeclaredSink(), None),
    ],
)
def test_source_helper_does_not_cross_match_sink_role(
    plugin: object,
    expected: frozenset[str] | None,
) -> None:
    assert source_declared_guaranteed_fields(plugin) == expected


@pytest.mark.parametrize(
    ("plugin", "expected"),
    [
        (_InheritedDeclaredSink(), frozenset({"customer_id"})),
        (_InheritedDeclaredSource(), None),
    ],
)
def test_sink_helper_does_not_cross_match_source_role(
    plugin: object,
    expected: frozenset[str] | None,
) -> None:
    assert sink_declared_required_fields(plugin) == expected
