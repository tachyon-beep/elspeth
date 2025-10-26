"""Tests for registry context utilities."""

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.context_utils import (
    create_plugin_context,
    extract_security_levels,
    prepare_plugin_payload,
)
from elspeth.core.validation import ConfigurationError

# extract_security_levels tests


def test_extract_from_options():
    """SECURITY: Reject security_level in options (ADR-002-B violation).

    Security level must come from declared_security_level ONLY, never from
    configuration options. Attempts to set it in options should crash.
    """
    with pytest.raises(ConfigurationError, match="security_level cannot be set in options"):
        extract_security_levels(
            definition={},
            options={
                "security_level": "PROTECTED",  # SECURITY VIOLATION
                "determinism_level": "high",
            },
            plugin_type="datasource",
            plugin_name="csv",
        )


def test_extract_from_definition():
    """Extract levels from definition dictionary."""
    security, determinism, sources = extract_security_levels(
        definition={
            "security_level": "OFFICIAL",
            "determinism_level": "low",
        },
        options={},
        plugin_type="llm",
        plugin_name="azure",
    )

    assert security == "OFFICIAL"
    assert determinism == "low"  # normalized
    assert "llm:azure.definition.security_level" in sources
    assert "llm:azure.definition.determinism_level" in sources


def test_extract_with_parent_context():
    """SECURITY: Reject inheritance from parent context (ADR-002-B).

    Old behavior: Child without security_level inherited from parent (SECURITY HOLE).
    New behavior: Fail loud - security must be declared, never inherited.
    """
    parent = PluginContext(
        plugin_name="parent",
        plugin_kind="parent",
        security_level="SECRET",
        determinism_level="high",
        provenance=("parent",),
    )

    # ADR-002-B: Attempting to create plugin without declared security_level
    # must FAIL LOUD, even if parent context exists
    with pytest.raises(ConfigurationError, match="security_level is required.*ADR-002-B"):
        extract_security_levels(
            definition={},
            options={},
            plugin_type="utility",
            plugin_name="helper",
            parent_context=parent,
            require_determinism=False,
        )


def test_extract_missing_required_security():
    """Raise error when security_level missing (ADR-001: always required, no backdoors)."""
    # ADR-001/002-B: Security is ALWAYS required in high-security systems (no require_security parameter)
    with pytest.raises(ConfigurationError, match="security_level is required.*ADR-002-B"):
        extract_security_levels(
            definition={},
            options={},
            plugin_type="datasource",
            plugin_name="csv",
        )


def test_extract_missing_required_determinism():
    """Raise error when required determinism_level missing.

    ADR-002-B: security_level must come from definition, not options.
    """
    with pytest.raises(ConfigurationError, match="determinism_level is required"):
        extract_security_levels(
            definition={"security_level": "OFFICIAL"},
            options={},
            plugin_type="datasource",
            plugin_name="csv",
            require_determinism=True,
        )


def test_extract_conflicting_security_levels():
    """SECURITY: Reject security_level in options (ADR-002-B).

    Old behavior: Detected conflicts between definition and options.
    New behavior: Reject options security_level immediately (before conflict check).
    """
    with pytest.raises(ConfigurationError, match="security_level cannot be set in options"):
        extract_security_levels(
            definition={"security_level": "UNOFFICIAL"},
            options={"security_level": "PROTECTED"},  # ← Rejected immediately
            plugin_type="sink",
            plugin_name="csv",
        )


def test_extract_determinism_defaults_to_none():
    """Determinism defaults to 'none' when not specified.

    ADR-002-B: security_level must come from definition, not options.
    """
    _, determinism, _ = extract_security_levels(
        definition={"security_level": "OFFICIAL"},
        options={},
        plugin_type="datasource",
        plugin_name="csv",
        require_determinism=False,
    )

    assert determinism == "none"


def test_extract_provenance_tracking():
    """Build correct provenance source list."""
    _, _, sources = extract_security_levels(
        definition={"security_level": "OFFICIAL"},
        options={"determinism_level": "high"},
        plugin_type="llm",
        plugin_name="openai",
    )

    assert len(sources) == 2
    assert "llm:openai.definition.security_level" in sources
    assert "llm:openai.options.determinism_level" in sources


def test_extract_normalizes_levels():
    """Security and determinism levels are normalized.

    ADR-002-B: security_level must come from definition (declared_security_level),
    never from options.
    """
    security, determinism, _ = extract_security_levels(
        definition={
            "security_level": "confidential",  # lowercase - will be normalized
        },
        options={
            "determinism_level": "HIGH",  # uppercase - will be normalized
        },
        plugin_type="datasource",
        plugin_name="test",
    )

    assert security == "PROTECTED"  # normalized to PROTECTED
    assert determinism == "high"  # normalized to lowercase


# create_plugin_context tests


def test_create_context_new():
    """Create new context without parent."""
    context = create_plugin_context(
        plugin_name="csv",
        plugin_kind="datasource",
        security_level="OFFICIAL",
        determinism_level="high",
        provenance=["datasource:csv.options"],
    )

    assert isinstance(context, PluginContext)
    assert context.plugin_name == "csv"
    assert context.plugin_kind == "datasource"
    assert context.security_level == "OFFICIAL"
    assert context.determinism_level == "high"
    assert "datasource:csv.options" in context.provenance


def test_create_context_derived():
    """Derive context from parent."""
    parent = PluginContext(
        plugin_name="parent",
        plugin_kind="parent",
        security_level="SECRET",
        determinism_level="high",
        provenance=("parent.source",),
    )

    context = create_plugin_context(
        plugin_name="child",
        plugin_kind="child",
        security_level="SECRET",
        determinism_level="high",
        provenance=["child.source"],
        parent_context=parent,
    )

    assert isinstance(context, PluginContext)
    assert context.plugin_name == "child"
    # Parent is stored separately, not merged into provenance
    assert context.parent == parent
    assert "child.source" in context.provenance
    # Parent provenance is accessible via parent attribute
    assert "parent.source" in context.parent.provenance


def test_create_context_empty_provenance():
    """Handle empty provenance gracefully."""
    context = create_plugin_context(
        plugin_name="test",
        plugin_kind="test",
        security_level="OFFICIAL",
        determinism_level="high",
        provenance=[],
    )

    # Should have default provenance
    assert len(context.provenance) > 0
    assert "test:test.resolved" in context.provenance


# prepare_plugin_payload tests


def test_prepare_payload_strips_security():
    """Reject security_level in options (ADR-002-B)."""
    from elspeth.core.validation.base import ConfigurationError

    options = {
        "path": "data.csv",
        "security_level": "PROTECTED",  # ADR-002-B: Not allowed in config
        "determinism_level": "high",
    }

    # ADR-002-B: security_level in options should raise error
    with pytest.raises(ConfigurationError, match="author-owned.*ADR-002-B"):
        prepare_plugin_payload(options)


def test_prepare_payload_keep_security():
    """Reject security_level regardless of strip_security flag (ADR-002-B)."""
    from elspeth.core.validation.base import ConfigurationError

    options = {
        "path": "data.csv",
        "security_level": "PROTECTED",  # ADR-002-B: Not allowed in config
    }

    # ADR-002-B: security_level always rejected, even with strip_security=False
    with pytest.raises(ConfigurationError, match="author-owned.*ADR-002-B"):
        prepare_plugin_payload(options, strip_security=False)


def test_prepare_payload_keep_determinism():
    """Keep determinism_level when strip_determinism=False."""
    options = {
        "path": "data.csv",
        "determinism_level": "high",
    }

    payload = prepare_plugin_payload(options, strip_determinism=False)

    assert "determinism_level" in payload
    assert payload["determinism_level"] == "high"


def test_prepare_payload_creates_copy():
    """Prepare payload creates copy, doesn't modify original."""
    options = {
        "path": "data.csv",
        "determinism_level": "high",  # Use determinism instead (not security)
    }

    payload = prepare_plugin_payload(options)

    # Determinism stripped by default
    assert "determinism_level" not in payload
    assert "determinism_level" in options  # original unchanged


def test_prepare_payload_empty_options():
    """Handle empty options dict."""
    payload = prepare_plugin_payload({})

    assert isinstance(payload, dict)
    assert len(payload) == 0


def test_prepare_payload_no_framework_keys():
    """Handle options without framework keys."""
    options = {"path": "data.csv", "encoding": "utf-8"}

    payload = prepare_plugin_payload(options)

    assert payload == options  # should be unchanged (except being a copy)
    assert payload is not options  # but still a copy
