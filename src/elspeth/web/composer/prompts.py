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
from elspeth.web.composer.state import CompositionState

SYSTEM_PROMPT = """\
You are an ELSPETH pipeline composer. Your job is to translate the user's \
natural-language description into a valid pipeline configuration using the \
provided tools.

Rules:
1. Always check the current state (get_current_state) before making changes.
2. Always check plugin schemas (get_plugin_schema) before configuring a plugin.
3. Use list_sources/list_transforms/list_sinks to discover available plugins.
4. After making changes, review the validation result in the tool response. \
If there are errors, fix them before responding to the user.
5. When the pipeline is complete and valid, respond with a summary of what \
was built.
6. Do not fabricate plugin names or configuration fields. Only use plugins \
and fields that appear in the catalog.
7. Use get_expression_grammar to understand gate expression syntax before \
writing conditions.
8. Connect nodes with edges using upsert_edge after creating nodes.
9. Every pipeline needs at least: a source, one or more sinks, and edges \
connecting them.
"""


def build_context_message(
    state: CompositionState,
    catalog: CatalogService,
) -> dict[str, str]:
    """Build the injected context message with current state and plugin summary.

    Args:
        state: Current composition state.
        catalog: For building the plugin summary.

    Returns:
        A dict with "role" and "content" suitable for the LLM message list.
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

    return {
        "role": "system",
        "content": f"Current pipeline state and available plugins:\n{json.dumps(context, indent=2)}",
    }


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
    1. System message (static prompt)
    2. Injected context (current state + plugin summary)
    3. Chat history (previous messages in this session)
    4. Current user message

    Args:
        chat_history: Chat history as plain dicts (role/content keys).
        state: Current CompositionState.
        user_message: The user's current message.
        catalog: CatalogService for context injection.

    Returns:
        A new list of message dicts for the LLM.
    """
    messages: list[dict[str, Any]] = []

    # 1. System prompt
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # 2. Injected context
    messages.append(build_context_message(state, catalog))

    # 3. Chat history
    if chat_history:
        messages.extend(chat_history)

    # 4. Current user message
    messages.append({"role": "user", "content": user_message})

    return messages
