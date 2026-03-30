"""Tests for the plain-text line source plugin."""

from pathlib import Path

import pytest

from elspeth.contracts.plugin_context import PluginContext
from tests.fixtures.factories import make_source_context

DYNAMIC_SCHEMA = {"mode": "observed"}
QUARANTINE_SINK = "quarantine"


class TestTextSource:
    """Tests for TextSource plugin."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        return make_source_context(plugin_name="text")

    def test_has_required_attributes(self) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        assert TextSource.name == "text"
        source = TextSource(
            {
                "path": "/tmp/test.txt",
                "column": "url",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        assert source.output_schema is not None

    def test_loads_one_row_per_line(self, tmp_path: Path, ctx: PluginContext) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        text_file = tmp_path / "urls.txt"
        text_file.write_text("https://a.example\nhttps://b.example\n", encoding="utf-8")

        source = TextSource(
            {
                "path": str(text_file),
                "column": "url",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )

        rows = list(source.load(ctx))

        assert [row.row for row in rows] == [
            {"url": "https://a.example"},
            {"url": "https://b.example"},
        ]
        assert all(row.is_quarantined is False for row in rows)

    def test_strips_whitespace_by_default(self, tmp_path: Path, ctx: PluginContext) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        text_file = tmp_path / "items.md"
        text_file.write_text("  first  \n\tsecond\t\n", encoding="utf-8")

        source = TextSource(
            {
                "path": str(text_file),
                "column": "item",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )

        rows = list(source.load(ctx))

        assert [row.row for row in rows] == [{"item": "first"}, {"item": "second"}]

    def test_skips_blank_lines_by_default(self, tmp_path: Path, ctx: PluginContext) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        text_file = tmp_path / "urls.txt"
        text_file.write_text("https://a.example\n\n   \nhttps://b.example\n", encoding="utf-8")

        source = TextSource(
            {
                "path": str(text_file),
                "column": "url",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )

        rows = list(source.load(ctx))

        assert [row.row for row in rows] == [
            {"url": "https://a.example"},
            {"url": "https://b.example"},
        ]

    def test_can_preserve_blank_lines(self, tmp_path: Path, ctx: PluginContext) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        text_file = tmp_path / "items.txt"
        text_file.write_text("first\n\nsecond\n", encoding="utf-8")

        source = TextSource(
            {
                "path": str(text_file),
                "column": "item",
                "schema": DYNAMIC_SCHEMA,
                "skip_blank_lines": False,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )

        rows = list(source.load(ctx))

        assert [row.row for row in rows] == [{"item": "first"}, {"item": ""}, {"item": "second"}]

    def test_file_not_found_raises(self, ctx: PluginContext) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        source = TextSource(
            {
                "path": "/nonexistent/file.txt",
                "column": "value",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )

        with pytest.raises(FileNotFoundError):
            list(source.load(ctx))

    def test_invalid_schema_quarantines_rows(self, tmp_path: Path, ctx: PluginContext) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        text_file = tmp_path / "numbers.txt"
        text_file.write_text("123\nabc\n", encoding="utf-8")

        source = TextSource(
            {
                "path": str(text_file),
                "column": "value",
                "schema": {"mode": "fixed", "fields": ["value: int"]},
                "on_validation_failure": QUARANTINE_SINK,
            }
        )

        rows = list(source.load(ctx))

        assert len(rows) == 2
        assert rows[0].is_quarantined is False
        assert rows[0].row == {"value": 123}
        assert rows[1].is_quarantined is True

    def test_has_plugin_version(self) -> None:
        from elspeth.plugins.sources.text_source import TextSource

        assert isinstance(TextSource.plugin_version, str)
        assert TextSource.plugin_version != "0.0.0"
