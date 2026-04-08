"""Tests for LLM message construction — build_messages and build_context_string.

Verifies:
- build_messages returns a NEW list on every call (cross-turn contamination guard)
- Message ordering: system → chat history → user message
- System message injects pipeline state and plugin catalog
- Empty chat history handled correctly
- Context string includes validation summary
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from elspeth.web.catalog.protocol import CatalogService, PluginKind
from elspeth.web.catalog.schemas import PluginSchemaInfo, PluginSummary
from elspeth.web.composer.prompts import (
    SYSTEM_PROMPT,
    build_context_string,
    build_messages,
    build_system_prompt,
)
from elspeth.web.composer.state import CompositionState


class StubCatalog:
    """Minimal CatalogService conforming to the protocol."""

    def list_sources(self) -> list[PluginSummary]:
        return [
            PluginSummary(
                name="csv",
                description="CSV source",
                plugin_type="source",
                config_fields=[],
            )
        ]

    def list_transforms(self) -> list[PluginSummary]:
        return [
            PluginSummary(
                name="uppercase",
                description="Uppercase transform",
                plugin_type="transform",
                config_fields=[],
            )
        ]

    def list_sinks(self) -> list[PluginSummary]:
        return [
            PluginSummary(
                name="csv",
                description="CSV sink",
                plugin_type="sink",
                config_fields=[],
            )
        ]

    def get_schema(self, plugin_type: PluginKind, name: str) -> PluginSchemaInfo:
        raise ValueError(f"Not implemented for stub: {plugin_type}/{name}")


def _stub_catalog() -> CatalogService:
    """Return a protocol-typed stub so mypy verifies conformance."""
    catalog: CatalogService = StubCatalog()
    return catalog


def _empty_state() -> CompositionState:
    """A minimal empty CompositionState for testing."""
    return CompositionState.from_dict(
        {
            "source": None,
            "nodes": [],
            "edges": [],
            "outputs": [],
            "metadata": {"name": "Test Pipeline", "description": ""},
            "version": 1,
        }
    )


class TestBuildMessages:
    """Message list construction and isolation."""

    def test_returns_new_list_each_call(self) -> None:
        """Critical: each call returns a distinct list object to prevent cross-turn contamination."""
        state = _empty_state()
        catalog = _stub_catalog()
        history: list[dict[str, Any]] = []

        list1 = build_messages(history, state, "Hello", catalog)
        list2 = build_messages(history, state, "Hello", catalog)
        assert list1 is not list2

    def test_mutating_returned_list_does_not_affect_next_call(self) -> None:
        """Appending to a returned list must not leak into subsequent calls."""
        state = _empty_state()
        catalog = _stub_catalog()

        list1 = build_messages([], state, "Hello", catalog)
        list1.append({"role": "assistant", "content": "I was injected"})

        list2 = build_messages([], state, "Hello", catalog)
        roles = [m["role"] for m in list2]
        assert "assistant" not in roles

    def test_message_ordering_system_history_user(self) -> None:
        """Messages must be: system, then history, then user."""
        state = _empty_state()
        catalog = _stub_catalog()
        history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]

        messages = build_messages(history, state, "new question", catalog)

        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "previous question"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "previous answer"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "new question"

    def test_empty_history_produces_system_and_user_only(self) -> None:
        state = _empty_state()
        catalog = _stub_catalog()

        messages = build_messages([], state, "my question", catalog)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "my question"

    def test_system_message_contains_prompt_and_context(self) -> None:
        state = _empty_state()
        catalog = _stub_catalog()

        messages = build_messages([], state, "test", catalog)
        system_content = messages[0]["content"]

        # Must contain the static system prompt
        assert SYSTEM_PROMPT in system_content
        # Must contain injected context with plugin names
        assert "csv" in system_content
        assert "uppercase" in system_content


class TestBuildContextString:
    """Context injection into the system prompt."""

    def test_contains_state_and_plugins(self) -> None:
        state = _empty_state()
        catalog = _stub_catalog()

        context = build_context_string(state, catalog)
        parsed = json.loads(context.split("\n", 1)[1])  # Skip header line

        assert "current_state" in parsed
        assert "available_plugins" in parsed
        plugins = parsed["available_plugins"]
        assert "csv" in plugins["sources"]
        assert "uppercase" in plugins["transforms"]
        assert "csv" in plugins["sinks"]

    def test_includes_validation_summary(self) -> None:
        state = _empty_state()
        catalog = _stub_catalog()

        context = build_context_string(state, catalog)
        parsed = json.loads(context.split("\n", 1)[1])

        validation = parsed["current_state"]["validation"]
        assert "is_valid" in validation
        assert "errors" in validation

    def test_metadata_included(self) -> None:
        state = _empty_state()
        catalog = _stub_catalog()

        context = build_context_string(state, catalog)
        parsed = json.loads(context.split("\n", 1)[1])

        assert parsed["current_state"]["metadata"]["name"] == "Test Pipeline"

    def test_includes_warnings_and_suggestions(self) -> None:
        """Validation context must include warnings and suggestions, not just errors."""
        state = _empty_state()
        catalog = _stub_catalog()

        context = build_context_string(state, catalog)
        parsed = json.loads(context.split("\n", 1)[1])

        validation = parsed["current_state"]["validation"]
        assert "warnings" in validation
        assert "suggestions" in validation


class TestBuildSystemPrompt:
    """System prompt composition with optional deployment layer."""

    def test_no_data_dir_returns_core_skill_only(self) -> None:
        """Without data_dir, returns the core skill unchanged."""
        result = build_system_prompt(None)
        assert result == SYSTEM_PROMPT

    def test_missing_deployment_skill_returns_core_only(self, tmp_path: Path) -> None:
        """data_dir with no skills/ subdir returns core skill only."""
        result = build_system_prompt(str(tmp_path))
        assert result == SYSTEM_PROMPT

    def test_deployment_skill_appended_after_separator(self, tmp_path: Path) -> None:
        """Deployment skill content is appended after a separator, in correct order."""
        deployment_content = "# Our Custom Providers\n\nUse ACME_API_KEY.\n"
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "pipeline_composer.md").write_text(deployment_content)

        result = build_system_prompt(str(tmp_path))

        # Exact equality — verifies ordering, not just presence.
        assert result == SYSTEM_PROMPT + "\n\n---\n\n" + deployment_content

    def test_empty_string_data_dir_still_calls_loader(self, tmp_path: Path) -> None:
        """Empty string data_dir is not None — build_system_prompt is called."""
        # Empty string produces a relative path lookup that finds no skills/.
        # The important thing is it goes through build_system_prompt, not the
        # SYSTEM_PROMPT fast path.
        result = build_system_prompt("")
        assert result == SYSTEM_PROMPT


class TestBuildMessagesWithDataDir:
    """build_messages with deployment skill overlay."""

    def test_data_dir_none_uses_core_prompt(self) -> None:
        """Default (no data_dir) uses core SYSTEM_PROMPT via fast path."""
        state = _empty_state()
        catalog = _stub_catalog()

        messages = build_messages([], state, "test", catalog, data_dir=None)
        system_content = messages[0]["content"]

        # System message is SYSTEM_PROMPT + context string.
        assert system_content.startswith(SYSTEM_PROMPT)

    def test_data_dir_with_deployment_skill_injects_it(self, tmp_path: Path) -> None:
        """When data_dir has a deployment skill, it appears in the system message."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "pipeline_composer.md").write_text("# Deployment: use ACME provider\n")

        state = _empty_state()
        catalog = _stub_catalog()

        messages = build_messages([], state, "test", catalog, data_dir=str(tmp_path))
        system_content = messages[0]["content"]

        assert "# Deployment: use ACME provider" in system_content
        assert SYSTEM_PROMPT in system_content
