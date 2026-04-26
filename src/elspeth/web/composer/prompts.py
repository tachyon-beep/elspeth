"""System prompt and message construction for the LLM composer.

build_messages() returns a NEW list on every call — never a cached
reference. This is critical because the tool-use loop appends to the
list during iteration.

Layer: L3 (application).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.composer.redaction import redact_source_storage_path
from elspeth.web.composer.skills import load_deployment_skill, load_skill
from elspeth.web.composer.state import CompositionState

# Load the pipeline composer skill once at module level (static content).
_PIPELINE_SKILL = load_skill("pipeline_composer")

# SYSTEM_PROMPT is the no-deployment-layer fast path.  Used directly by
# build_messages when data_dir is None, avoiding a function call.  Also
# exported for tests that need to assert identity with the core skill.
SYSTEM_PROMPT = _PIPELINE_SKILL


@lru_cache(maxsize=4)
def build_system_prompt(data_dir: str | None = None) -> str:
    """Build the full system prompt: core skill + optional deployment skill.

    The deployment skill is loaded from ``{data_dir}/skills/pipeline_composer.md``
    if it exists.  This lets operators inject company-specific knowledge
    (provider mappings, custom patterns, domain vocabulary) without editing
    the core skill pack.

    Cached per *data_dir* value — the deployment skill is read once from
    disk per unique data_dir, not on every LLM call.

    Args:
        data_dir: Root data directory.  ``None`` skips the deployment layer.

    Returns:
        Combined system prompt string.
    """
    deployment = load_deployment_skill("pipeline_composer", data_dir)
    if deployment:
        return _PIPELINE_SKILL + "\n\n---\n\n" + deployment
    return _PIPELINE_SKILL


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
    serialized = redact_source_storage_path(serialized)  # B4: strip blob paths
    validation = state.validate()
    serialized["validation"] = {
        "is_valid": validation.is_valid,
        "errors": [e.to_dict() for e in validation.errors],
        "warnings": [e.to_dict() for e in validation.warnings],
        "suggestions": [e.to_dict() for e in validation.suggestions],
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
    data_dir: str | None = None,
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
        data_dir: Optional data directory for deployment-specific skill
            overlay.  When provided, the deployment skill at
            ``{data_dir}/skills/pipeline_composer.md`` is appended to
            the core skill in the system prompt.

    Returns:
        A new list of message dicts for the LLM.
    """
    messages: list[dict[str, Any]] = []

    # 1. System prompt with injected context (single system message)
    prompt = build_system_prompt(data_dir) if data_dir is not None else SYSTEM_PROMPT
    context_str = build_context_string(state, catalog)
    messages.append({"role": "system", "content": prompt + "\n\n" + context_str})

    # 2. Chat history
    if chat_history:
        messages.extend(chat_history)

    # 3. Current user message
    messages.append({"role": "user", "content": user_message})

    return messages


def build_run_diagnostics_messages(
    snapshot: Mapping[str, object],
    data_dir: str | None = None,
) -> list[dict[str, str]]:
    """Build messages for run diagnostics explanation.

    Uses the same composer skill pack stack as normal composition so every
    composer LLM engagement carries the structure and MCP-tool guidance.
    """
    prompt = build_system_prompt(data_dir) if data_dir is not None else SYSTEM_PROMPT
    diagnostics_instructions = (
        "Run diagnostics explanation mode:\n"
        "- Explain the provided bounded run diagnostics snapshot to an operator.\n"
        "- Use only visible evidence from tokens, node states, operations, artifacts, and status.\n"
        "- Mention saved artifact paths when present.\n"
        "- If there are no Landscape records yet, say the run may still be setting up.\n"
        "- Return strict JSON only, with this exact object shape: "
        '{"headline": string, "evidence": string[], "meaning": string, "next_steps": string[]}.\n'
        "- Keep the headline and meaning plain-English and useful; avoid cute filler or vague progress claims.\n"
        "- Evidence entries must cite visible evidence from the snapshot, not hidden chain-of-thought.\n"
        "- Do not call tools, invent hidden progress, expose hidden chain-of-thought, or mention secrets."
    )
    return [
        {"role": "system", "content": prompt + "\n\n" + diagnostics_instructions},
        {"role": "user", "content": json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False)},
    ]
