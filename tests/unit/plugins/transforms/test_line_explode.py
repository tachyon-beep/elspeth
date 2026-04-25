"""Tests for line_explode deaggregation transform."""

from __future__ import annotations

import pytest

from elspeth.contracts.plugin_context import PluginContext
from elspeth.testing import make_pipeline_row
from tests.fixtures.factories import make_context

DYNAMIC_SCHEMA = {"mode": "observed"}


@pytest.fixture
def ctx() -> PluginContext:
    return make_context()


def test_line_explode_splits_string_into_indexed_rows(ctx: PluginContext) -> None:
    from elspeth.plugins.transforms.line_explode import LineExplode

    transform = LineExplode(
        {
            "schema": DYNAMIC_SCHEMA,
            "source_field": "html",
            "output_field": "html_line",
        }
    )

    result = transform.process(
        make_pipeline_row(
            {
                "source_url": "https://www.wardline.dev/",
                "html": "<html>\n<body>\n<h1>Wardline</h1>",
            }
        ),
        ctx,
    )

    assert result.status == "success"
    assert result.is_multi_row
    assert result.rows is not None
    assert [row.to_dict() for row in result.rows] == [
        {"source_url": "https://www.wardline.dev/", "html_line": "<html>", "line_index": 0},
        {"source_url": "https://www.wardline.dev/", "html_line": "<body>", "line_index": 1},
        {"source_url": "https://www.wardline.dev/", "html_line": "<h1>Wardline</h1>", "line_index": 2},
    ]


def test_line_explode_preserves_empty_lines(ctx: PluginContext) -> None:
    from elspeth.plugins.transforms.line_explode import LineExplode

    transform = LineExplode(
        {
            "schema": DYNAMIC_SCHEMA,
            "source_field": "html",
            "output_field": "html_line",
        }
    )

    result = transform.process(make_pipeline_row({"html": "a\n\nb"}), ctx)

    assert result.rows is not None
    assert [row.to_dict()["html_line"] for row in result.rows] == ["a", "", "b"]


def test_line_explode_can_omit_index(ctx: PluginContext) -> None:
    from elspeth.plugins.transforms.line_explode import LineExplode

    transform = LineExplode(
        {
            "schema": DYNAMIC_SCHEMA,
            "source_field": "html",
            "output_field": "html_line",
            "include_index": False,
        }
    )

    result = transform.process(make_pipeline_row({"html": "a\nb"}), ctx)

    assert result.rows is not None
    assert [row.to_dict() for row in result.rows] == [{"html_line": "a"}, {"html_line": "b"}]


def test_line_explode_output_contract_matches_declared_fields(ctx: PluginContext) -> None:
    from elspeth.plugins.transforms.line_explode import LineExplode

    transform = LineExplode(
        {
            "schema": DYNAMIC_SCHEMA,
            "source_field": "html",
            "output_field": "html_line",
        }
    )

    result = transform.process(make_pipeline_row({"html": "a\nb"}), ctx)

    assert result.rows is not None
    field_by_name = {field.normalized_name: field for field in result.rows[0].contract.fields}
    for field_name in ("html_line", "line_index"):
        assert field_by_name[field_name].required is True
        assert field_by_name[field_name].source == "declared"


def test_line_explode_empty_string_returns_error(ctx: PluginContext) -> None:
    from elspeth.plugins.transforms.line_explode import LineExplode

    transform = LineExplode(
        {
            "schema": DYNAMIC_SCHEMA,
            "source_field": "html",
            "output_field": "html_line",
        }
    )

    result = transform.process(make_pipeline_row({"html": ""}), ctx)

    assert result.status == "error"
    assert result.reason is not None
    assert result.reason["reason"] == "invalid_input"
    assert result.reason["field"] == "html"
    assert not result.retryable


def test_line_explode_crashes_on_non_string_input(ctx: PluginContext) -> None:
    from elspeth.plugins.transforms.line_explode import LineExplode

    transform = LineExplode(
        {
            "schema": DYNAMIC_SCHEMA,
            "source_field": "html",
            "output_field": "html_line",
        }
    )

    with pytest.raises(TypeError, match="must be a string"):
        transform.process(make_pipeline_row({"html": ["not", "a", "string"]}), ctx)


def test_line_explode_is_discovered_by_plugin_manager() -> None:
    from elspeth.plugins.infrastructure.manager import PluginManager

    manager = PluginManager()
    manager.register_builtin_plugins()

    assert manager.get_transform_by_name("line_explode").name == "line_explode"
