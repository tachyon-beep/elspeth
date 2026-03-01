# src/elspeth/plugins/llm/validation.py
"""LLM response validation utilities.

Per ELSPETH's Three-Tier Trust Model:
- LLM responses are Tier 3 (external data) - zero trust
- Validation must happen IMMEDIATELY at the boundary
- Invalid responses must be caught, not silently coerced

This module extracts the common validation pattern from LLM transforms
so it can be:
1. Reused across all LLM plugin implementations
2. Property-tested with Hypothesis

Shared helpers (added for T10 consolidation):
- render_template_safe: Template rendering with structured error return
- check_truncation: Response truncation detection via finish_reason or token heuristic
- strip_markdown_fences: Strip markdown code block wrappers from LLM output
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from elspeth.contracts.errors import TransformErrorReason
from elspeth.plugins.transforms.llm.multi_query import OutputFieldConfig, OutputFieldType
from elspeth.plugins.transforms.llm.templates import PromptTemplate, RenderedPrompt, TemplateError

if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import SchemaContract


def reject_nonfinite_constant(value: str) -> None:
    """Reject non-standard JSON constants (NaN, Infinity, -Infinity).

    Used as ``parse_constant`` argument to ``json.loads`` at every Tier 3
    boundary where LLM JSON responses are parsed.
    """
    raise ValueError(f"Non-standard JSON constant '{value}' not allowed")


def validate_field_value(
    value: Any,
    field_config: OutputFieldConfig,
) -> str | None:
    """Validate a parsed JSON value against its declared output field type.

    Tier 3 boundary enforcement: LLM responses may contain values that parse
    as valid JSON but violate the declared schema (e.g., string where integer
    expected, boolean where number expected, non-finite floats).

    Args:
        value: The parsed JSON value from the LLM response
        field_config: Expected type configuration from output_fields

    Returns:
        Error message string if validation fails, None if valid
    """
    expected_type = field_config.type

    if expected_type == OutputFieldType.STRING:
        if not isinstance(value, str):
            return f"expected string, got {type(value).__name__}"

    elif expected_type == OutputFieldType.INTEGER:
        # bool is subclass of int in Python — reject explicitly
        if isinstance(value, bool):
            return "expected integer, got boolean"
        if isinstance(value, float) and not math.isfinite(value):
            return "expected finite integer, got non-finite float"
        if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
            pass
        else:
            return f"expected integer, got {type(value).__name__}"

    elif expected_type == OutputFieldType.NUMBER:
        if isinstance(value, bool):
            return "expected number, got boolean"
        if not isinstance(value, (int, float)):
            return f"expected number, got {type(value).__name__}"
        if isinstance(value, float) and not math.isfinite(value):
            return "expected finite number, got non-finite float"

    elif expected_type == OutputFieldType.BOOLEAN:
        if not isinstance(value, bool):
            return f"expected boolean, got {type(value).__name__}"

    elif expected_type == OutputFieldType.ENUM:
        if not isinstance(value, str):
            return f"expected string (enum), got {type(value).__name__}"
        if field_config.values and value not in field_config.values:
            return f"value '{value}' not in allowed values: {field_config.values}"

    return None


@dataclass(frozen=True)
class ValidationSuccess:
    """Successful validation result containing parsed data."""

    data: dict[str, Any]


@dataclass(frozen=True)
class ValidationError:
    """Failed validation result with error details."""

    reason: str
    detail: str | None = None
    expected: str | None = None
    actual: str | None = None


ValidationResult = ValidationSuccess | ValidationError


def validate_json_object_response(content: str) -> ValidationResult:
    """Validate LLM response content is a JSON object.

    This is the standard validation for ELSPETH LLM transforms:
    1. Parse JSON (catch JSONDecodeError)
    2. Verify type is dict (not array, null, or primitive)
    3. Return validated dict or structured error

    Args:
        content: Raw response content from LLM API

    Returns:
        ValidationSuccess with parsed dict, or ValidationError with details
    """
    # Step 1: Parse JSON
    try:
        parsed = json.loads(content, parse_constant=reject_nonfinite_constant)
    except (json.JSONDecodeError, ValueError) as e:
        return ValidationError(
            reason="invalid_json",
            detail=str(e),
        )

    # Step 2: Verify type is dict
    if not isinstance(parsed, dict):
        return ValidationError(
            reason="invalid_json_type",
            expected="object",
            actual=type(parsed).__name__,
        )

    # Success
    return ValidationSuccess(data=parsed)


def render_template_safe(
    template: PromptTemplate,
    row_or_context: Any,
    *,
    contract: SchemaContract | None = None,
    query_name: str | None = None,
) -> RenderedPrompt | TransformErrorReason:
    """Render a template, returning structured error on failure.

    Consolidates the try/except TemplateError pattern from 4 LLM transforms.
    """
    try:
        return template.render_with_metadata(row_or_context, contract=contract)
    except TemplateError as e:
        error: TransformErrorReason = {
            "reason": "template_rendering_failed",
            "error": str(e),
            "template_hash": template.template_hash,
        }
        if template.template_source:
            error["template_file_path"] = template.template_source
        if query_name is not None:
            error["query"] = query_name
        return error


def check_truncation(
    *,
    finish_reason: str | None,
    completion_tokens: int | None,
    prompt_tokens: int | None,
    max_tokens: int | None,
    query_name: str | None = None,
    content_preview: str | None = None,
) -> TransformErrorReason | None:
    """Check for response truncation. Returns error dict or None.

    Uses finish_reason as authoritative signal, falls back to token heuristic.
    Accepts both FinishReason enum and raw str (StrEnum comparison works with ==).
    Consolidates truncation detection from azure_multi_query.py and
    openrouter_multi_query.py.

    The returned error dict always contains: reason, error, completion_tokens,
    prompt_tokens, finish_reason. Optional fields: max_tokens (omitted when None),
    query (when query_name provided), raw_response_preview (when content_preview provided).
    """
    is_truncated: bool
    if finish_reason is not None:
        is_truncated = finish_reason == "length"
    else:
        # Token heuristic fallback — guard against max_tokens=0 spurious trigger
        is_truncated = (
            max_tokens is not None
            and max_tokens > 0
            and completion_tokens is not None
            and completion_tokens > 0
            and completion_tokens >= max_tokens
        )

    if not is_truncated:
        return None

    error: TransformErrorReason = {
        "reason": "response_truncated",
        "error": (
            f"LLM response was truncated at {completion_tokens} tokens "
            f"(max_tokens={max_tokens}). Increase max_tokens or shorten your prompt."
        ),
        "completion_tokens": completion_tokens,
        "prompt_tokens": prompt_tokens,
        "finish_reason": finish_reason,
    }
    if max_tokens is not None:
        error["max_tokens"] = max_tokens
    if query_name is not None:
        error["query"] = query_name
    if content_preview:
        error["raw_response_preview"] = content_preview[:500]
    return error


def strip_markdown_fences(content: str) -> str:
    """Strip markdown code block fences from LLM response content.

    LLMs sometimes wrap JSON responses in ```json ... ``` blocks even in
    JSON mode. This strips them so JSON parsing succeeds.

    Consolidates identical logic from azure_multi_query.py and
    openrouter_multi_query.py.
    """
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    first_newline = stripped.find("\n")
    if first_newline == -1:
        # No newline after opening fence — no body to extract
        return stripped

    stripped = stripped[first_newline + 1 :]
    # Handle trailing whitespace before closing fence (e.g. "``` \n")
    if stripped.rstrip().endswith("```"):
        stripped = stripped.rstrip()
        stripped = stripped[:-3].strip()
    return stripped
