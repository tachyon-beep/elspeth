"""System prompt and message construction for the LLM composer.

build_messages() returns a NEW list on every call — never a cached
reference. This is critical because the tool-use loop appends to the
list during iteration.

Layer: L3 (application).
"""

from __future__ import annotations

import json
from typing import Any

from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.composer.skills import load_skill
from elspeth.web.composer.state import CompositionState

# Load the pipeline composer skill once at module level (static content).
_PIPELINE_SKILL = load_skill("pipeline_composer")

SYSTEM_PROMPT = _PIPELINE_SKILL


def build_context_string(
    state: CompositionState,
    catalog: CatalogService,
) -> str:
    """Build the injected context string with current state and plugin summary.

    Args:
        state: Current composition state.
        catalog: For building the plugin summary.

    Returns:
        A string with state and plugin info, suitable for appending to the
        system prompt.
    """
    serialized = state.to_dict()
    validation = state.validate()
    serialized["validation"] = {
        "is_valid": validation.is_valid,
        "errors": list(validation.errors),
    }

    # Build lightweight plugin summary (names only).
    # CatalogService returns PluginSummary instances — use .name attribute.
    source_names = [p.name for p in catalog.list_sources()]
    transform_names = [p.name for p in catalog.list_transforms()]
    sink_names = [p.name for p in catalog.list_sinks()]

    context = {
        "current_state": serialized,
        "available_plugins": {
            "sources": source_names,
            "transforms": transform_names,
            "sinks": sink_names,
        },
    }

    return f"Current pipeline state and available plugins:\n{json.dumps(context, indent=2)}"


def build_messages(
    chat_history: list[dict[str, Any]],
    state: CompositionState,
    user_message: str,
    catalog: CatalogService,
) -> list[dict[str, Any]]:
    """Build the full message list for the LLM.

    IMPORTANT: Returns a NEW list on every call. Never returns a cached
    or shared reference. The tool-use loop appends to this list during
    iteration; returning a cached reference would cause cross-turn
    contamination.

    Message sequence:
    1. System message (static prompt + injected context)
    2. Chat history (previous messages in this session)
    3. Current user message

    Args:
        chat_history: Chat history as plain dicts (role/content keys).
        state: Current CompositionState.
        user_message: The user's current message.
        catalog: CatalogService for context injection.

    Returns:
        A new list of message dicts for the LLM.
    """
    messages: list[dict[str, Any]] = []

    # 1. System prompt with injected context (single system message)
    context_str = build_context_string(state, catalog)
    messages.append({"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context_str})

    # 2. Chat history
    if chat_history:
        messages.extend(chat_history)

    # 4. Current user message
    messages.append({"role": "user", "content": user_message})

    return messages
