"""Multi-query LLM support for case study x criteria cross-product evaluation.

Contains both the legacy domain-specific multi-query types (QuerySpec,
CaseStudyConfig, CriterionConfig, MultiQueryConfigMixin) and the new
domain-agnostic types (UnifiedQuerySpec, resolve_queries). Legacy types
are retained during the transition period (Tasks 5-12) and will be
deleted in Task 12.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.config_base import PluginConfig
from elspeth.plugins.llm.azure import AzureOpenAIConfig

logger = logging.getLogger(__name__)


class OutputFieldType(StrEnum):
    """Supported types for structured output fields."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"


class ResponseFormat(StrEnum):
    """LLM response format modes.

    - STANDARD: Uses {"type": "json_object"} - model outputs JSON but no schema enforcement
    - STRUCTURED: Uses {"type": "json_schema", ...} - API enforces exact schema compliance
    """

    STANDARD = "standard"
    STRUCTURED = "structured"


class OutputFieldConfig(PluginConfig):
    """Configuration for a single output field in the LLM response.

    Attributes:
        suffix: Column suffix in output row (e.g., "score" -> "{prefix}_score")
        type: Data type for schema enforcement
        values: Required for enum type - list of allowed values
    """

    suffix: str = Field(..., description="Column suffix in output row")
    type: OutputFieldType = Field(..., description="Data type for schema enforcement")
    values: list[str] | None = Field(None, description="Allowed values (required for enum type)")

    @model_validator(mode="after")
    def validate_enum_has_values(self) -> OutputFieldConfig:
        """Ensure enum type has values list."""
        if self.type == OutputFieldType.ENUM:
            if not self.values or len(self.values) == 0:
                raise ValueError("enum type requires non-empty 'values' list")
        elif self.values is not None:
            raise ValueError(f"'values' is only valid for enum type, not {self.type.value}")
        return self

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema property definition.

        Returns:
            JSON Schema dict for this field
        """
        if self.type == OutputFieldType.ENUM:
            # Enum uses 'enum' keyword with allowed values
            return {"type": "string", "enum": self.values}
        else:
            # Direct type mapping
            return {"type": self.type.value}


@dataclass
class QuerySpec:
    """Specification for a single query in the cross-product.

    Represents one (case_study, criterion) pair to be evaluated.

    Attributes:
        case_study_name: Name of the case study (e.g., "cs1")
        criterion_name: Name of the criterion (e.g., "diagnosis")
        input_fields: List of row field names to map to input_1, input_2, etc.
        output_prefix: Prefix for output fields (e.g., "cs1_diagnosis")
        criterion_data: Full criterion object for template injection
        case_study_data: Full case study object for template injection
    """

    case_study_name: str
    criterion_name: str
    input_fields: list[str]
    output_prefix: str
    criterion_data: dict[str, Any]
    case_study_data: dict[str, Any]
    max_tokens: int | None = None  # Per-query override for max_tokens

    def build_template_context(self, row: PipelineRow | dict[str, Any]) -> dict[str, Any]:
        """Build template context for this query.

        Maps input_fields to input_1, input_2, etc. and injects criterion and case_study data.

        Args:
            row: Full row data (dict or PipelineRow)

        Returns:
            Context dict with input_N, criterion, case_study, and source_row
        """
        context: dict[str, Any] = {}

        # Map input fields to positional variables
        # Access directly - missing field is a config error, should crash
        for i, field_name in enumerate(self.input_fields, start=1):
            if field_name not in row:
                raise KeyError(f"Required field '{field_name}' not found in row for query {self.output_prefix}")
            context[f"input_{i}"] = row[field_name]

        # Inject criterion data
        context["criterion"] = self.criterion_data

        # Inject case study data (name, context, metadata)
        context["case_study"] = self.case_study_data

        # Include full row for row-based lookups.
        # Named "source_row" to avoid collision with PromptTemplate.render() which
        # wraps the entire context under its own "row" key. Without this rename,
        # templates saw row.row for the original data — a confusing double-nesting.
        # Fix: elspeth-rapid-ishd
        context["source_row"] = row

        return context


@dataclass(frozen=True, slots=True)
class UnifiedQuerySpec:
    """Domain-agnostic query specification for multi-query transforms.

    Unlike the legacy QuerySpec (case_study x criterion cross-product),
    this uses named input_fields (dict mapping template variable name
    to row column name) instead of positional input_1, input_2 variables.

    Attributes:
        name: Unique query identifier (used in output field prefixes)
        input_fields: Mapping of template variable → row column name
        response_format: LLM response format mode
        output_fields: Typed output field definitions (None = unstructured)
        template: Per-query template override (None = use config-level template)
        max_tokens: Per-query max_tokens override (None = use config-level)
    """

    name: str
    input_fields: dict[str, str]
    response_format: ResponseFormat = ResponseFormat.STANDARD
    output_fields: list[OutputFieldConfig] | None = None
    template: str | None = None
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be non-empty")
        if not self.input_fields:
            raise ValueError("input_fields must be non-empty")

    def build_template_context(self, row: PipelineRow | dict[str, Any]) -> dict[str, Any]:
        """Build template context mapping named variables to row values.

        Args:
            row: Full row data (dict or PipelineRow)

        Returns:
            Context dict with named variables and source_row reference

        Raises:
            KeyError: If a required row column is missing
        """
        context: dict[str, Any] = {}
        for template_var, row_column in self.input_fields.items():
            context[template_var] = row[row_column]
        context["source_row"] = row
        return context


# Pattern for detecting legacy positional template variables {{ input_N }}
_POSITIONAL_VAR_PATTERN = re.compile(r"\{\{\s*input_\d+\s*\}\}")


def resolve_queries(
    queries: list[UnifiedQuerySpec] | dict[str, Any] | list[dict[str, Any]],
) -> list[UnifiedQuerySpec]:
    """Normalize query definitions into a list of UnifiedQuerySpec.

    Accepts:
    - list[UnifiedQuerySpec]: Pass through as-is
    - dict[str, dict]: Key becomes query name, value has spec fields
    - list[dict]: Each dict must include 'name' key

    Validates:
    - Non-empty input
    - No output field suffix collisions across queries
    - Warns on reserved suffixes (e.g., "error", "usage", "model")
    - Rejects legacy positional template variables ({{ input_N }})

    Args:
        queries: Query definitions in any supported format

    Returns:
        List of validated UnifiedQuerySpec instances

    Raises:
        ValueError: If queries is empty, has collisions, or uses positional vars
    """
    specs: list[UnifiedQuerySpec] = []

    if isinstance(queries, dict):
        if not queries:
            raise ValueError("no queries configured")
        for name, definition in queries.items():
            # Parse output_fields from dicts if present
            output_fields = None
            raw_output_fields = definition.get("output_fields")
            if raw_output_fields is not None:
                output_fields = [OutputFieldConfig(**of) if isinstance(of, dict) else of for of in raw_output_fields]
            specs.append(
                UnifiedQuerySpec(
                    name=name,
                    input_fields=definition["input_fields"],
                    response_format=ResponseFormat(definition["response_format"])
                    if "response_format" in definition
                    else ResponseFormat.STANDARD,
                    output_fields=output_fields,
                    template=definition.get("template"),
                    max_tokens=definition.get("max_tokens"),
                )
            )
    elif isinstance(queries, list):
        if not queries:
            raise ValueError("no queries configured")
        for item in queries:
            if isinstance(item, UnifiedQuerySpec):
                specs.append(item)
            else:
                # dict form with 'name' key
                output_fields = None
                raw_output_fields = item.get("output_fields")
                if raw_output_fields is not None:
                    output_fields = [OutputFieldConfig(**of) if isinstance(of, dict) else of for of in raw_output_fields]
                specs.append(
                    UnifiedQuerySpec(
                        name=item["name"],
                        input_fields=item["input_fields"],
                        response_format=ResponseFormat(item.get("response_format", "standard")),
                        output_fields=output_fields,
                        template=item.get("template"),
                        max_tokens=item.get("max_tokens"),
                    )
                )
    else:
        raise TypeError(f"queries must be list or dict, got {type(queries).__name__}")

    # Validate: reject positional template variables
    for spec in specs:
        if spec.template and _POSITIONAL_VAR_PATTERN.search(spec.template):
            raise ValueError(
                f"Query '{spec.name}' template uses positional variables "
                f"(e.g., {{{{ input_1 }}}}). Use named input_fields instead: "
                f"map template variables to row columns via input_fields dict."
            )

    # Validate: check output field suffix collisions across queries
    from elspeth.plugins.llm import LLM_AUDIT_SUFFIXES, LLM_GUARANTEED_SUFFIXES

    reserved_suffixes = set()
    for suffix in LLM_GUARANTEED_SUFFIXES + LLM_AUDIT_SUFFIXES:
        if suffix:
            reserved_suffixes.add(suffix.lstrip("_"))
    # System-reserved suffixes used by multi-query error handling
    reserved_suffixes.add("error")

    seen_output_keys: dict[str, str] = {}  # full output key → first query name
    for spec in specs:
        if spec.output_fields:
            for field in spec.output_fields:
                # Warn on reserved suffixes
                if field.suffix in reserved_suffixes:
                    logger.warning(
                        "Query '%s' output field suffix '%s' matches a reserved LLM suffix. This may cause output field conflicts.",
                        spec.name,
                        field.suffix,
                    )
                # Check for cross-query output key collisions.
                # Output keys are "{query_name}_{suffix}" (see MultiQueryStrategy),
                # so different queries MAY share the same suffix as long as the full
                # key is unique.
                output_key = f"{spec.name}_{field.suffix}"
                if output_key in seen_output_keys:
                    raise ValueError(
                        f"Output field key collision: key '{output_key}' "
                        f"used by both query '{seen_output_keys[output_key]}' "
                        f"and query '{spec.name}'"
                    )
                seen_output_keys[output_key] = spec.name

    return specs


class CaseStudyConfig(PluginConfig):
    """Configuration for a single case study.

    Attributes:
        name: Unique identifier for this case study (used in output field prefix)
        input_fields: Row field names to map to input_1, input_2, etc.
        context: Context type (e.g., "Capability", "Capacity") for template use
        description: Human-readable description of this case study type
    """

    name: str = Field(..., description="Case study identifier")
    input_fields: list[str] = Field(..., description="Row fields to map to input_N")
    context: str | None = Field(None, description="Context type (e.g., Capability, Capacity)")
    description: str | None = Field(None, description="Human-readable description")

    @field_validator("input_fields")
    @classmethod
    def validate_input_fields_not_empty(cls, v: list[str]) -> list[str]:
        """Ensure at least one input field."""
        if not v:
            raise ValueError("input_fields cannot be empty")
        return v

    def to_template_data(self) -> dict[str, Any]:
        """Convert to dict for template injection."""
        return {
            "name": self.name,
            "context": self.context,
            "description": self.description,
            "input_fields": self.input_fields,
        }


class CriterionConfig(PluginConfig):
    """Configuration for a single evaluation criterion.

    All fields except 'name' are optional and available in templates
    via {{ row.criterion.field_name }}.

    Attributes:
        name: Unique identifier (used in output field prefix)
        code: Short code for lookups (e.g., "DIAG")
        description: Human-readable description
        subcriteria: List of subcriteria names/descriptions
    """

    name: str = Field(..., description="Criterion identifier")
    code: str | None = Field(None, description="Short code for lookups")
    description: str | None = Field(None, description="Human-readable description")
    subcriteria: list[str] = Field(default_factory=list, description="Subcriteria list")
    max_tokens: int | None = Field(None, gt=0, description="Per-criterion max_tokens override")

    def to_template_data(self) -> dict[str, Any]:
        """Convert to dict for template injection."""
        return {
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "subcriteria": self.subcriteria,
        }


def validate_multi_query_key_collisions(
    case_studies: list[CaseStudyConfig],
    criteria: list[CriterionConfig],
    output_mapping: dict[str, OutputFieldConfig],
) -> None:
    """Validate no duplicate names or output key collisions.

    Shared validation for both Azure and OpenRouter multi-query configs.

    Checks:
    1. No duplicate case_study names
    2. No duplicate criterion names
    3. No duplicate output_mapping suffixes
    4. No output_mapping suffixes that collide with reserved LLM suffixes

    Raises:
        ValueError: If duplicates or collisions are detected.
    """
    from elspeth.plugins.llm import LLM_AUDIT_SUFFIXES, LLM_GUARANTEED_SUFFIXES

    # Check for duplicate case_study names
    case_study_names: set[str] = set()
    for cs in case_studies:
        if cs.name in case_study_names:
            raise ValueError(f"Duplicate case_study name: '{cs.name}'. Each case_study must have a unique name.")
        case_study_names.add(cs.name)

    # Check for duplicate criterion names
    criterion_names: set[str] = set()
    for crit in criteria:
        if crit.name in criterion_names:
            raise ValueError(f"Duplicate criterion name: '{crit.name}'. Each criterion must have a unique name.")
        criterion_names.add(crit.name)

    # Check output_mapping suffixes are unique (duplicate suffixes overwrite keys)
    suffix_to_fields: dict[str, list[str]] = {}
    for json_field, field_config in output_mapping.items():
        suffix = field_config.suffix
        if suffix not in suffix_to_fields:
            suffix_to_fields[suffix] = [json_field]
        else:
            suffix_to_fields[suffix].append(json_field)

    duplicate_suffixes = {suffix: fields for suffix, fields in suffix_to_fields.items() if len(fields) > 1}
    if duplicate_suffixes:
        details = ", ".join(f"'{suffix}' (fields: {sorted(fields)})" for suffix, fields in sorted(duplicate_suffixes.items()))
        raise ValueError(
            f"Duplicate output_mapping suffixes detected. Each suffix must be unique to avoid output key overwrites: {details}"
        )

    # Build set of reserved suffixes (strip leading underscore for comparison)
    reserved_suffixes = set()
    for suffix in LLM_GUARANTEED_SUFFIXES + LLM_AUDIT_SUFFIXES:
        if suffix:  # Skip empty string
            # Reserved suffixes are stored as "_usage", we compare against "usage"
            reserved_suffixes.add(suffix.lstrip("_"))

    # Check output_mapping suffixes don't collide with reserved suffixes
    for json_field, field_config in output_mapping.items():
        if field_config.suffix in reserved_suffixes:
            raise ValueError(
                f"Output mapping '{json_field}' has suffix '{field_config.suffix}' that collides with reserved LLM suffix '_{field_config.suffix}'. "
                f"Reserved suffixes: {sorted('_' + s for s in reserved_suffixes)}"
            )

    # Check cross-product output prefixes are unique after delimiter application.
    # The prefix is f"{case_study.name}_{criterion.name}", so names containing
    # underscores can create ambiguous collisions:
    #   (case_study="a_b", criterion="c") -> "a_b_c"
    #   (case_study="a", criterion="b_c") -> "a_b_c"
    # Both generate the same prefix, causing silent data overwrites downstream.
    prefix_to_pairs: dict[str, list[tuple[str, str]]] = {}
    for cs in case_studies:
        for crit in criteria:
            prefix = f"{cs.name}_{crit.name}"
            prefix_to_pairs.setdefault(prefix, []).append((cs.name, crit.name))

    collisions = {p: pairs for p, pairs in prefix_to_pairs.items() if len(pairs) > 1}
    if collisions:
        details = ", ".join(
            f"prefix '{prefix}' generated by: {sorted(f'({cs}, {cr})' for cs, cr in pairs)}" for prefix, pairs in sorted(collisions.items())
        )
        raise ValueError(
            f"Cross-product output prefix collision detected. Different (case_study, criterion) "
            f"pairs generate the same output prefix due to underscore ambiguity: {details}. "
            f"Rename case studies or criteria to avoid this."
        )


class MultiQueryConfigMixin(PluginConfig):
    """Mixin providing multi-query config fields for any LLM provider.

    Provides case_studies x criteria cross-product evaluation support.
    Add as a second base class alongside a provider config:

        class MultiQueryConfig(AzureOpenAIConfig, MultiQueryConfigMixin): ...
        class OpenRouterMultiQueryConfig(OpenRouterConfig, MultiQueryConfigMixin): ...
    """

    case_studies: list[CaseStudyConfig] = Field(
        ...,
        description="Case study definitions",
        min_length=1,
    )
    criteria: list[CriterionConfig] = Field(
        ...,
        description="Criterion definitions",
        min_length=1,
    )
    output_mapping: dict[str, OutputFieldConfig] = Field(
        ...,
        description="JSON field -> typed output field configuration",
    )
    response_format: ResponseFormat = Field(
        ResponseFormat.STANDARD,
        description="Response format: 'standard' (JSON mode) or 'structured' (schema-enforced)",
    )

    @field_validator("output_mapping", mode="before")
    @classmethod
    def parse_output_mapping(cls, v: Any) -> dict[str, Any]:
        """Parse output_mapping from config dict format."""
        if not isinstance(v, dict):
            raise ValueError("output_mapping must be a dict")
        if not v:
            raise ValueError("output_mapping cannot be empty")
        # Pydantic will handle nested OutputFieldConfig parsing
        return v

    @model_validator(mode="after")
    def validate_no_output_key_collisions(self) -> Self:
        """Validate no duplicate names or reserved suffix collisions."""
        validate_multi_query_key_collisions(self.case_studies, self.criteria, self.output_mapping)
        return self

    def build_json_schema(self) -> dict[str, Any]:
        """Build JSON Schema for structured outputs.

        Returns:
            Complete JSON Schema dict for the response format
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        for json_field, field_config in self.output_mapping.items():
            properties[json_field] = field_config.to_json_schema()
            required.append(json_field)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def build_response_format(self) -> dict[str, Any]:
        """Build the response_format parameter for the LLM API.

        Returns:
            Dict to pass as response_format to the LLM API
        """
        if self.response_format == ResponseFormat.STRUCTURED:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "query_response",
                    "strict": True,
                    "schema": self.build_json_schema(),
                },
            }
        # Standard JSON mode
        return {"type": "json_object"}

    def expand_queries(self) -> list[QuerySpec]:
        """Expand config into QuerySpec list (case_studies x criteria).

        Returns:
            List of QuerySpec, one per (case_study, criterion) pair
        """
        specs: list[QuerySpec] = []

        for case_study in self.case_studies:
            for criterion in self.criteria:
                spec = QuerySpec(
                    case_study_name=case_study.name,
                    criterion_name=criterion.name,
                    input_fields=case_study.input_fields,
                    output_prefix=f"{case_study.name}_{criterion.name}",
                    criterion_data=criterion.to_template_data(),
                    case_study_data=case_study.to_template_data(),
                    max_tokens=criterion.max_tokens,
                )
                specs.append(spec)

        return specs


class MultiQueryConfig(AzureOpenAIConfig, MultiQueryConfigMixin):
    """Configuration for Azure multi-query LLM transform.

    Combines AzureOpenAIConfig (connection settings, pooling, templates)
    with MultiQueryConfigMixin (case_studies, criteria, output_mapping).

    The cross-product of case_studies x criteria defines all queries.

    Example:
        output_mapping:
          score:
            suffix: score
            type: integer
          rationale:
            suffix: rationale
            type: string
          confidence:
            suffix: confidence
            type: enum
            values: [low, medium, high]
    """


# Resolve forward references for Pydantic
MultiQueryConfigMixin.model_rebuild()
MultiQueryConfig.model_rebuild()
