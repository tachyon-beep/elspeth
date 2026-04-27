"""Tests for plugin semantics contract types."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from elspeth.contracts.plugin_semantics import (
    ContentKind,
    FieldSemanticFacts,
    FieldSemanticRequirement,
    InputSemanticRequirements,
    OutputSemanticDeclaration,
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


class TestFieldSemanticFacts:
    def test_construct(self):
        facts = FieldSemanticFacts(
            field_name="content",
            content_kind=ContentKind.PLAIN_TEXT,
            text_framing=TextFraming.COMPACT,
            fact_code="web_scrape.content.compact_text",
            configured_by=("format", "text_separator"),
        )
        assert facts.field_name == "content"
        assert facts.content_kind is ContentKind.PLAIN_TEXT
        assert facts.text_framing is TextFraming.COMPACT
        assert facts.fact_code == "web_scrape.content.compact_text"
        assert facts.configured_by == ("format", "text_separator")

    def test_immutable(self):
        facts = FieldSemanticFacts(
            field_name="x",
            content_kind=ContentKind.PLAIN_TEXT,
            fact_code="t.x.basic",
        )
        with pytest.raises(FrozenInstanceError):
            facts.field_name = "y"  # type: ignore[misc]

    def test_default_configured_by_is_empty_tuple(self):
        facts = FieldSemanticFacts(
            field_name="x",
            content_kind=ContentKind.UNKNOWN,
            fact_code="t.x.unknown",
        )
        assert facts.configured_by == ()


class TestFieldSemanticRequirement:
    def test_construct_and_compare_against_satisfied_facts(self):
        requirement = FieldSemanticRequirement(
            field_name="content",
            accepted_content_kinds=frozenset({ContentKind.PLAIN_TEXT, ContentKind.MARKDOWN}),
            accepted_text_framings=frozenset({TextFraming.NEWLINE_FRAMED, TextFraming.LINE_COMPATIBLE}),
            requirement_code="line_explode.source_field.line_framed_text",
            unknown_policy=UnknownSemanticPolicy.FAIL,
        )
        assert requirement.field_name == "content"
        assert ContentKind.PLAIN_TEXT in requirement.accepted_content_kinds
        assert TextFraming.LINE_COMPATIBLE in requirement.accepted_text_framings
        assert requirement.severity == "high"  # default

    def test_immutable(self):
        requirement = FieldSemanticRequirement(
            field_name="x",
            accepted_content_kinds=frozenset({ContentKind.PLAIN_TEXT}),
            accepted_text_framings=frozenset({TextFraming.NEWLINE_FRAMED}),
            requirement_code="t.x.req",
        )
        with pytest.raises(FrozenInstanceError):
            requirement.field_name = "y"  # type: ignore[misc]


class TestOutputSemanticDeclaration:
    def test_default_is_empty(self):
        decl = OutputSemanticDeclaration()
        assert decl.fields == ()

    def test_carries_facts(self):
        f1 = FieldSemanticFacts("a", ContentKind.PLAIN_TEXT, fact_code="t.a")
        f2 = FieldSemanticFacts("b", ContentKind.MARKDOWN, fact_code="t.b")
        decl = OutputSemanticDeclaration(fields=(f1, f2))
        assert decl.fields == (f1, f2)


class TestInputSemanticRequirements:
    def test_default_is_empty(self):
        reqs = InputSemanticRequirements()
        assert reqs.fields == ()
