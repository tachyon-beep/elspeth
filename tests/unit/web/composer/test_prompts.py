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
from typing import Any

from elspeth.web.catalog.protocol import CatalogService, PluginKind
from elspeth.web.catalog.schemas import PluginSchemaInfo, PluginSummary
from elspeth.web.composer.prompts import SYSTEM_PROMPT, build_context_string, build_messages
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
