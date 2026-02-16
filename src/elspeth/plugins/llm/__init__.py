# src/elspeth/plugins/llm/__init__.py
"""LLM transform plugins for ELSPETH.

Provides transforms for Azure OpenAI, OpenRouter, and other LLM providers.
Includes support for pooled execution, batch processing, and multi-query evaluation.

Plugins are accessed via PluginManager, not direct imports:
    manager = PluginManager()
    manager.register_builtin_plugins()
    transform = manager.get_transform_by_name("azure_llm")

For testing or advanced usage, import directly from module paths:
    from elspeth.plugins.llm.azure import AzureLLMTransform
    from elspeth.plugins.llm.templates import PromptTemplate
    from elspeth.contracts.schema_contract import PipelineRow

Metadata Field Categories
=========================

guaranteed_fields: Contract-stable fields downstream can depend on
    - <response_field>: The LLM response content
    - <response_field>_usage: Token usage (for cost/quota management)
    - <response_field>_model: Model identifier (for routing/reporting)

audit_fields: Provenance metadata for audit trail (may change between versions)
    - <response_field>_template_hash: SHA256 of prompt template
    - <response_field>_variables_hash: SHA256 of rendered variables
    - <response_field>_template_source: Config file path
    - <response_field>_lookup_hash: SHA256 of lookup data
    - <response_field>_lookup_source: Config file path
    - <response_field>_system_prompt_source: Config file path

WARNING: Do not build production logic that depends on audit_fields.
These fields exist for audit trail reconstruction (explain() queries)
and may change between versions without notice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.contracts import PluginSchema
    from elspeth.contracts.schema import SchemaConfig

# Metadata field suffixes for contract-stable fields (downstream can depend on these)
LLM_GUARANTEED_SUFFIXES: tuple[str, ...] = (
    "",  # The response content field itself
    "_usage",  # Token usage dict {prompt_tokens, completion_tokens, total_tokens}
    "_model",  # Model identifier that actually responded
)

# Multi-query transforms emit suffixed fields only (no base field)
# e.g., category_score, category_rationale, category_usage, category_model
# NOT category (the base field with empty suffix)
MULTI_QUERY_GUARANTEED_SUFFIXES: tuple[str, ...] = (
    "_usage",  # Token usage dict {prompt_tokens, completion_tokens, total_tokens}
    "_model",  # Model identifier that actually responded
)

# Metadata field suffixes for audit-only fields (exist but may change between versions)
LLM_AUDIT_SUFFIXES: tuple[str, ...] = (
    "_template_hash",  # SHA256 of prompt template
    "_variables_hash",  # SHA256 of rendered template variables
    "_template_source",  # File path of template (None if inline)
    "_lookup_hash",  # SHA256 of lookup data
    "_lookup_source",  # File path of lookup data (None if no lookup)
    "_system_prompt_source",  # File path of system prompt (None if inline)
)


def get_llm_guaranteed_fields(response_field: str) -> tuple[str, ...]:
    """Return contract-stable metadata field names for LLM transforms.

    These fields are part of the stable API. Downstream transforms can
    safely declare dependencies on them via required_fields.

    Args:
        response_field: Base field name (e.g., "llm_response"). Must not be empty
            or whitespace-only.

    Returns:
        Tuple of field names that are guaranteed to exist.

    Raises:
        ValueError: If response_field is empty or whitespace-only.
    """
    if not response_field or not response_field.strip():
        raise ValueError("response_field cannot be empty or whitespace-only")
    if not response_field.isidentifier():
        raise ValueError(
            f"response_field '{response_field}' is not a valid Python identifier. "
            f"Use only letters, digits, and underscores, starting with a letter or underscore."
        )
    return tuple(f"{response_field}{suffix}" for suffix in LLM_GUARANTEED_SUFFIXES)


def get_llm_audit_fields(response_field: str) -> tuple[str, ...]:
    """Return audit-only metadata field names for LLM transforms.

    These fields exist for audit trail reconstruction but are NOT part
    of the stability contract. They may change between versions.

    Args:
        response_field: Base field name (e.g., "llm_response"). Must not be empty
            or whitespace-only.

    Returns:
        Tuple of field names for audit purposes.

    Raises:
        ValueError: If response_field is empty or whitespace-only.
    """
    if not response_field or not response_field.strip():
        raise ValueError("response_field cannot be empty or whitespace-only")
    if not response_field.isidentifier():
        raise ValueError(
            f"response_field '{response_field}' is not a valid Python identifier. "
            f"Use only letters, digits, and underscores, starting with a letter or underscore."
        )
    return tuple(f"{response_field}{suffix}" for suffix in LLM_AUDIT_SUFFIXES)


def get_multi_query_guaranteed_fields(output_prefix: str) -> tuple[str, ...]:
    """Return contract-stable metadata field names for multi-query LLM transforms.

    Multi-query transforms emit suffixed output fields (e.g., category_score,
    category_rationale) but NOT the base field itself. This function returns
    only the metadata fields (_usage, _model) without the base field.

    For the output mapping fields (score, rationale, etc.), multi-query
    computes those separately from the output_mapping config.

    Args:
        output_prefix: Output field prefix (e.g., "category"). Must not be empty
            or whitespace-only.

    Returns:
        Tuple of metadata field names that are guaranteed to exist.

    Raises:
        ValueError: If output_prefix is empty or whitespace-only.
    """
    if not output_prefix or not output_prefix.strip():
        raise ValueError("output_prefix cannot be empty or whitespace-only")
    if not output_prefix.isidentifier():
        raise ValueError(
            f"output_prefix '{output_prefix}' is not a valid Python identifier. "
            f"Use only letters, digits, and underscores, starting with a letter or underscore."
        )
    return tuple(f"{output_prefix}{suffix}" for suffix in MULTI_QUERY_GUARANTEED_SUFFIXES)


def populate_llm_metadata_fields(
    output: dict[str, object],
    field_prefix: str,
    *,
    usage: dict[str, int] | None,
    model: str,
    template_hash: str,
    variables_hash: str,
    template_source: str | None,
    lookup_hash: str | None,
    lookup_source: str | None,
    system_prompt_source: str | None,
) -> None:
    """Populate standard LLM metadata fields into an output row dict.

    The caller sets the base content field separately
    (e.g., ``output[field_prefix] = response.content``).
    This function adds the 8 metadata fields that ALL LLM transforms
    must include for audit completeness.

    Args:
        output: Mutable row dict to populate.
        field_prefix: Response field name (e.g., "llm_response").
        usage: Token usage dict (prompt_tokens, completion_tokens).
        model: Model identifier that actually responded.
        template_hash: SHA-256 of prompt template.
        variables_hash: SHA-256 of rendered template variables.
        template_source: Config file path of template (None if inline).
        lookup_hash: SHA-256 of lookup data (None if no lookup).
        lookup_source: Config file path of lookup data (None if no lookup).
        system_prompt_source: Config file path of system prompt (None if inline).
    """
    # Guaranteed metadata (contract-stable)
    output[f"{field_prefix}_usage"] = usage
    output[f"{field_prefix}_model"] = model
    # Audit metadata (provenance)
    output[f"{field_prefix}_template_hash"] = template_hash
    output[f"{field_prefix}_variables_hash"] = variables_hash
    output[f"{field_prefix}_template_source"] = template_source
    output[f"{field_prefix}_lookup_hash"] = lookup_hash
    output[f"{field_prefix}_lookup_source"] = lookup_source
    output[f"{field_prefix}_system_prompt_source"] = system_prompt_source


def _build_augmented_output_schema(
    base_schema_config: SchemaConfig,
    response_field: str,
    schema_name: str,
) -> type[PluginSchema]:
    """Build an output schema that includes LLM-added fields.

    LLM transforms add response, usage, model, and audit fields to output rows.
    The output schema must include these fields for DAG type validation to pass
    when downstream consumers have explicit schemas requiring LLM output fields.

    For observed schemas this returns the same dynamic schema (no fields to add).
    For explicit schemas (fixed/flexible) this augments the base fields with
    optional LLM output fields typed as ``object`` (Any).

    Args:
        base_schema_config: The base schema config from plugin options.
        response_field: Base field name (e.g., "llm_response").
        schema_name: Name for the generated Pydantic model class.

    Returns:
        A PluginSchema subclass with input fields plus LLM output fields.
    """
    from elspeth.plugins.schema_factory import create_schema_from_config

    if base_schema_config.is_observed:
        # Observed schemas accept anything — no augmentation needed
        return create_schema_from_config(base_schema_config, schema_name, allow_coercion=False)

    # For explicit schemas, build an augmented SchemaConfig that includes
    # LLM output fields as optional fields.
    from elspeth.contracts.schema import FieldDefinition, SchemaConfig

    base_fields = base_schema_config.fields or ()
    existing_names = {f.name for f in base_fields}

    # Add LLM fields (guaranteed + audit) as optional 'any' type fields
    llm_field_names = [
        *get_llm_guaranteed_fields(response_field),
        *get_llm_audit_fields(response_field),
    ]
    extra_fields = tuple(
        FieldDefinition(name=name, field_type="any", required=False) for name in llm_field_names if name not in existing_names
    )

    augmented_config = SchemaConfig(
        # Use flexible mode so extra fields from upstream are accepted
        mode="flexible",
        fields=(*base_fields, *extra_fields),
        guaranteed_fields=base_schema_config.guaranteed_fields,
        required_fields=base_schema_config.required_fields,
        audit_fields=base_schema_config.audit_fields,
    )
    return create_schema_from_config(augmented_config, schema_name, allow_coercion=False)


__all__ = [
    "LLM_AUDIT_SUFFIXES",
    "LLM_GUARANTEED_SUFFIXES",
    "MULTI_QUERY_GUARANTEED_SUFFIXES",
    "_build_augmented_output_schema",
    "get_llm_audit_fields",
    "get_llm_guaranteed_fields",
    "get_multi_query_guaranteed_fields",
    "populate_llm_metadata_fields",
]
