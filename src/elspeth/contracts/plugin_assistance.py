"""Plugin assistance: deterministic guidance keyed by issue codes.

L0 module. Carries no plugin runtime references. Consumers (catalog
service, MCP discovery, validators) attach assistance to issue codes;
they do not parse summary/suggested_fixes prose.

Secret discipline: assistance fields MUST contain only safe option
names, plugin names, enum values, and human-readable advice. They MUST
NOT contain raw URLs, headers, prompts, row data, credentials, raw
provider errors, file paths, or exception strings. Enforcement is by
plugin authors and tests (see secret-leakage tests in Phase 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from elspeth.contracts.freeze import freeze_fields


@dataclass(frozen=True, slots=True)
class PluginAssistanceExample:
    """A before/after configuration sketch."""

    title: str
    before: Mapping[str, object] | None = None
    after: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.before is not None:
            freeze_fields(self, "before")
        if self.after is not None:
            freeze_fields(self, "after")


@dataclass(frozen=True, slots=True)
class PluginAssistance:
    """Deterministic, side-effect-free guidance for an issue code.

    Returned by ``BaseTransform.get_agent_assistance(issue_code=...)``.
    Validators attach the issue code; they do not parse the prose
    fields. Catalog/MCP discovery surfaces this as structured data.
    """

    plugin_name: str
    issue_code: str | None
    summary: str
    suggested_fixes: tuple[str, ...] = ()
    examples: tuple[PluginAssistanceExample, ...] = ()
    composer_hints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # examples is tuple[PluginAssistanceExample, ...]; the elements
        # already deep-freeze their own dict fields in their own __post_init__.
        # No additional freeze_fields needed for examples itself, because
        # tuple of frozen-dataclass elements is natively immutable AND
        # element fields are already frozen at element construction time.
        # suggested_fixes / composer_hints are tuple[str, ...]: natively
        # immutable, no guard needed.
        pass
