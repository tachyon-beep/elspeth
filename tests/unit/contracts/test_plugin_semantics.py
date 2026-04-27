"""Tests for plugin semantics contract types."""

from __future__ import annotations

from elspeth.contracts.plugin_semantics import (
    ContentKind,
    SemanticOutcome,
    TextFraming,
    UnknownSemanticPolicy,
)


class TestContentKind:
    def test_known_members(self):
        assert ContentKind.UNKNOWN.value == "unknown"
        assert ContentKind.PLAIN_TEXT.value == "plain_text"
        assert ContentKind.MARKDOWN.value == "markdown"
        assert ContentKind.HTML_RAW.value == "html_raw"
        assert ContentKind.JSON_STRUCTURED.value == "json_structured"
        assert ContentKind.BINARY.value == "binary"

    def test_is_str_subclass(self):
        assert isinstance(ContentKind.PLAIN_TEXT, str)
        assert ContentKind.PLAIN_TEXT == "plain_text"

    def test_membership_is_closed_for_phase_1(self):
        # Phase 1 vocabulary — additions require explicit plan amendment.
        assert {member.value for member in ContentKind} == {
            "unknown",
            "plain_text",
            "markdown",
            "html_raw",
            "json_structured",
            "binary",
        }


class TestTextFraming:
    def test_known_members(self):
        assert TextFraming.UNKNOWN.value == "unknown"
        assert TextFraming.NOT_TEXT.value == "not_text"
        assert TextFraming.COMPACT.value == "compact"
        assert TextFraming.NEWLINE_FRAMED.value == "newline_framed"
        assert TextFraming.LINE_COMPATIBLE.value == "line_compatible"

    def test_membership_is_closed_for_phase_1(self):
        assert {member.value for member in TextFraming} == {
            "unknown",
            "not_text",
            "compact",
            "newline_framed",
            "line_compatible",
        }


class TestUnknownSemanticPolicy:
    def test_known_members(self):
        assert UnknownSemanticPolicy.ALLOW.value == "allow"
        assert UnknownSemanticPolicy.WARN.value == "warn"
        assert UnknownSemanticPolicy.FAIL.value == "fail"


class TestSemanticOutcome:
    def test_known_members(self):
        assert SemanticOutcome.SATISFIED.value == "satisfied"
        assert SemanticOutcome.CONFLICT.value == "conflict"
        assert SemanticOutcome.UNKNOWN.value == "unknown"
