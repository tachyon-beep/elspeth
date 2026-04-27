"""Tests for plugin assistance contract types — including deep-freeze guards."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from elspeth.contracts.plugin_assistance import (
    PluginAssistance,
    PluginAssistanceExample,
)


class TestPluginAssistanceExampleFreeze:
    def test_dict_fields_become_mapping_proxy(self):
        example = PluginAssistanceExample(
            title="t",
            before={"format": "text", "text_separator": " "},
            after={"format": "text", "text_separator": "\n"},
        )
        assert isinstance(example.before, MappingProxyType)
        assert isinstance(example.after, MappingProxyType)

    def test_none_fields_are_left_none(self):
        example = PluginAssistanceExample(title="t", before=None, after=None)
        assert example.before is None
        assert example.after is None

    def test_inner_mutation_is_blocked(self):
        original = {"format": "text"}
        example = PluginAssistanceExample(title="t", before=original)
        with pytest.raises(TypeError):
            example.before["format"] = "markdown"  # type: ignore[index]
        # And mutating the source dict does NOT affect the frozen field
        original["format"] = "markdown"
        assert example.before["format"] == "text"


class TestPluginAssistanceFreeze:
    def test_examples_field_freezes_inner_dicts(self):
        example = PluginAssistanceExample(title="t", before={"k": "v"})
        assistance = PluginAssistance(
            plugin_name="web_scrape",
            issue_code="line_explode.source_field.line_framed_text",
            summary="Set text_separator to '\\n'.",
            suggested_fixes=("Set text_separator: '\\n'", "Or use format: markdown"),
            examples=(example,),
        )
        # Both examples and inner dicts are frozen.
        assert isinstance(assistance.examples, tuple)
        assert isinstance(assistance.examples[0].before, MappingProxyType)

    def test_required_fields(self):
        # plugin_name, issue_code, summary are REQUIRED (no defaults).
        # suggested_fixes, examples, composer_hints have empty defaults.
        assistance = PluginAssistance(
            plugin_name="p",
            issue_code=None,
            summary="s",
        )
        assert assistance.suggested_fixes == ()
        assert assistance.examples == ()
        assert assistance.composer_hints == ()
