"""Plugin-declared semantic contracts.

L0 module (contracts layer). Imports nothing above L0.

Vocabulary is intentionally CLOSED. Additions require design review and
a plan amendment — adding enum values lazily is exactly how the project
ends up rebuilding ad hoc runtime validation as expanding prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContentKind(StrEnum):
    """The kind of content a field carries."""

    UNKNOWN = "unknown"
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    HTML_RAW = "html_raw"
    JSON_STRUCTURED = "json_structured"
    BINARY = "binary"


class TextFraming(StrEnum):
    """How a text-bearing field is framed for downstream line operations."""

    UNKNOWN = "unknown"
    NOT_TEXT = "not_text"
    COMPACT = "compact"
    NEWLINE_FRAMED = "newline_framed"
    LINE_COMPATIBLE = "line_compatible"


class UnknownSemanticPolicy(StrEnum):
    """How a consumer treats an UNKNOWN producer fact for a required field.

    Phase 1 line_explode uses FAIL — every producer that semantically
    feeds it must declare semantics. WARN and ALLOW are present for
    future consumers but are not used in Phase 1.
    """

    ALLOW = "allow"
    WARN = "warn"
    FAIL = "fail"


class SemanticOutcome(StrEnum):
    """Result of comparing producer facts to a consumer requirement."""

    SATISFIED = "satisfied"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FieldSemanticFacts:
    """Structured facts a producer declares about a field it emits.

    All container fields are tuples / enum values. ``configured_by``
    names option paths that influenced this fact; it MUST contain only
    safe option names, never values, URLs, headers, prompts, row data,
    or exception text.
    """

    field_name: str
    content_kind: ContentKind
    text_framing: TextFraming = TextFraming.UNKNOWN
    fact_code: str = "field_semantics"
    configured_by: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OutputSemanticDeclaration:
    """A producer's full semantic facts across the fields it emits."""

    fields: tuple[FieldSemanticFacts, ...] = ()


@dataclass(frozen=True, slots=True)
class FieldSemanticRequirement:
    """Structured requirements a consumer declares for a field it consumes."""

    field_name: str
    accepted_content_kinds: frozenset[ContentKind]
    accepted_text_framings: frozenset[TextFraming]
    requirement_code: str
    severity: str = "high"
    unknown_policy: UnknownSemanticPolicy = UnknownSemanticPolicy.FAIL
    configured_by: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InputSemanticRequirements:
    """A consumer's full semantic requirements across the fields it consumes."""

    fields: tuple[FieldSemanticRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticEdgeContract:
    """Per-edge result of comparing producer facts to consumer requirement.

    consumer_plugin is REQUIRED — assistance lookup MUST address a
    specific plugin class, not iterate every registered transform.
    producer_plugin is optional because some producers (e.g., source)
    are not registered transform classes.
    """

    from_id: str
    to_id: str
    consumer_plugin: str
    producer_plugin: str | None
    producer_field: str
    consumer_field: str
    producer_facts: FieldSemanticFacts | None
    requirement: FieldSemanticRequirement
    outcome: SemanticOutcome


def compare_semantic(
    facts: FieldSemanticFacts | None,
    requirement: FieldSemanticRequirement,
) -> SemanticOutcome:
    """Compare producer facts to a consumer requirement.

    Returns UNKNOWN if facts are absent or any compared dimension is
    UNKNOWN. Returns CONFLICT if either dimension is not in the
    accepted set. Returns SATISFIED only when both dimensions are
    explicitly in the accepted set.
    """
    if facts is None:
        return SemanticOutcome.UNKNOWN
    if facts.content_kind is ContentKind.UNKNOWN:
        return SemanticOutcome.UNKNOWN
    if facts.text_framing is TextFraming.UNKNOWN:
        return SemanticOutcome.UNKNOWN
    if facts.content_kind not in requirement.accepted_content_kinds:
        return SemanticOutcome.CONFLICT
    if facts.text_framing not in requirement.accepted_text_framings:
        return SemanticOutcome.CONFLICT
    return SemanticOutcome.SATISFIED
