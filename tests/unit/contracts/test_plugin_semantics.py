"""Tests for plugin semantics contract types."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from elspeth.contracts.plugin_semantics import (
    ContentKind,
    FieldSemanticFacts,
    FieldSemanticRequirement,
    InputSemanticRequirements,
    OutputSemanticDeclaration,
    SemanticEdgeContract,
    SemanticOutcome,
    TextFraming,
    UnknownSemanticPolicy,
    compare_semantic,
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


class TestSemanticEdgeContract:
    def test_construct(self):
        facts = FieldSemanticFacts("x", ContentKind.PLAIN_TEXT, fact_code="t.x")
        req = FieldSemanticRequirement(
            field_name="x",
            accepted_content_kinds=frozenset({ContentKind.PLAIN_TEXT}),
            accepted_text_framings=frozenset({TextFraming.UNKNOWN, TextFraming.LINE_COMPATIBLE}),
            requirement_code="c.x.req",
        )
        edge = SemanticEdgeContract(
            from_id="a",
            to_id="b",
            consumer_plugin="line_explode",
            producer_plugin="web_scrape",
            producer_field="x",
            consumer_field="x",
            producer_facts=facts,
            requirement=req,
            outcome=SemanticOutcome.SATISFIED,
        )
        assert edge.outcome is SemanticOutcome.SATISFIED
        assert edge.consumer_plugin == "line_explode"
        assert edge.producer_plugin == "web_scrape"


class TestCompareSemantic:
    def _req(self, kinds, framings, policy=UnknownSemanticPolicy.FAIL):
        return FieldSemanticRequirement(
            field_name="x",
            accepted_content_kinds=frozenset(kinds),
            accepted_text_framings=frozenset(framings),
            requirement_code="t.x.req",
            unknown_policy=policy,
        )

    def test_satisfied_when_facts_within_acceptance(self):
        facts = FieldSemanticFacts(
            "x",
            ContentKind.PLAIN_TEXT,
            text_framing=TextFraming.NEWLINE_FRAMED,
            fact_code="t.x.nl",
        )
        req = self._req(
            {ContentKind.PLAIN_TEXT, ContentKind.MARKDOWN},
            {TextFraming.NEWLINE_FRAMED, TextFraming.LINE_COMPATIBLE},
        )
        assert compare_semantic(facts, req) is SemanticOutcome.SATISFIED

    def test_conflict_on_content_kind_mismatch(self):
        facts = FieldSemanticFacts(
            "x",
            ContentKind.HTML_RAW,
            text_framing=TextFraming.NOT_TEXT,
            fact_code="t.x.raw",
        )
        req = self._req({ContentKind.PLAIN_TEXT}, {TextFraming.NEWLINE_FRAMED})
        assert compare_semantic(facts, req) is SemanticOutcome.CONFLICT

    def test_conflict_on_framing_mismatch(self):
        facts = FieldSemanticFacts(
            "x",
            ContentKind.PLAIN_TEXT,
            text_framing=TextFraming.COMPACT,
            fact_code="t.x.compact",
        )
        req = self._req(
            {ContentKind.PLAIN_TEXT},
            {TextFraming.NEWLINE_FRAMED, TextFraming.LINE_COMPATIBLE},
        )
        assert compare_semantic(facts, req) is SemanticOutcome.CONFLICT

    def test_unknown_when_facts_are_none(self):
        req = self._req({ContentKind.PLAIN_TEXT}, {TextFraming.NEWLINE_FRAMED})
        assert compare_semantic(None, req) is SemanticOutcome.UNKNOWN

    def test_unknown_when_either_dimension_is_unknown(self):
        facts_kind_unknown = FieldSemanticFacts(
            "x",
            ContentKind.UNKNOWN,
            text_framing=TextFraming.NEWLINE_FRAMED,
            fact_code="t.x.kindless",
        )
        facts_framing_unknown = FieldSemanticFacts(
            "x",
            ContentKind.PLAIN_TEXT,
            text_framing=TextFraming.UNKNOWN,
            fact_code="t.x.framingless",
        )
        req = self._req({ContentKind.PLAIN_TEXT}, {TextFraming.NEWLINE_FRAMED})
        assert compare_semantic(facts_kind_unknown, req) is SemanticOutcome.UNKNOWN
        assert compare_semantic(facts_framing_unknown, req) is SemanticOutcome.UNKNOWN


_CONTENT_KINDS = list(ContentKind)
_FRAMINGS = list(TextFraming)


@given(
    content_kind=st.sampled_from(_CONTENT_KINDS),
    text_framing=st.sampled_from(_FRAMINGS),
    accepted_kinds=st.sets(st.sampled_from(_CONTENT_KINDS), min_size=1),
    accepted_framings=st.sets(st.sampled_from(_FRAMINGS), min_size=1),
)
def test_compare_semantic_outcome_is_consistent(
    content_kind,
    text_framing,
    accepted_kinds,
    accepted_framings,
):
    facts = FieldSemanticFacts(
        field_name="x",
        content_kind=content_kind,
        text_framing=text_framing,
        fact_code="t.x.gen",
    )
    requirement = FieldSemanticRequirement(
        field_name="x",
        accepted_content_kinds=frozenset(accepted_kinds),
        accepted_text_framings=frozenset(accepted_framings),
        requirement_code="c.x.req",
    )
    outcome = compare_semantic(facts, requirement)

    if content_kind is ContentKind.UNKNOWN or text_framing is TextFraming.UNKNOWN:
        assert outcome is SemanticOutcome.UNKNOWN
    elif content_kind in accepted_kinds and text_framing in accepted_framings:
        assert outcome is SemanticOutcome.SATISFIED
    else:
        assert outcome is SemanticOutcome.CONFLICT
