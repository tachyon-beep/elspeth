"""FieldMapper transform plugin.

Renames, selects, and reorganizes row fields.

IMPORTANT: Transforms use allow_coercion=False to catch upstream bugs.
If the source outputs wrong types, the transform crashes immediately.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import Field, model_validator

from elspeth.contracts.contexts import TransformContext
from elspeth.contracts.contract_propagation import narrow_contract_to_output
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.infrastructure.base import BaseTransform
from elspeth.plugins.infrastructure.config_base import TransformDataConfig
from elspeth.plugins.infrastructure.results import TransformResult
from elspeth.plugins.infrastructure.sentinels import MISSING
from elspeth.plugins.infrastructure.utils import get_nested_field


class FieldMapperConfig(TransformDataConfig):
    """Configuration for field mapper transform.

    Requires 'schema' in config to define input/output expectations.
    Use 'schema: {mode: observed}' for dynamic field handling.
    """

    mapping: dict[str, str] = Field(default_factory=dict)
    select_only: bool = False
    strict: bool = False

    @model_validator(mode="after")
    def _reject_duplicate_targets(self) -> FieldMapperConfig:
        """Reject mappings where multiple sources map to the same target.

        Duplicate targets cause silent data loss: the last write wins,
        overwriting the value from the earlier mapping without any error.
        This also produces incorrect contract metadata (type/original_name
        lineage from the wrong source field).
        """
        if not self.mapping:
            return self
        targets: list[str] = list(self.mapping.values())
        seen: set[str] = set()
        duplicates: set[str] = set()
        for target in targets:
            if target in seen:
                duplicates.add(target)
            seen.add(target)
        if duplicates:
            # Build source->target details for the error message
            collisions: dict[str, list[str]] = {}
            for source, target in self.mapping.items():
                if target in duplicates:
                    collisions.setdefault(target, []).append(source)
            msg = (
                f"Mapping has duplicate target field names: "
                f"{', '.join(f'{t!r} <- {srcs}' for t, srcs in sorted(collisions.items()))}. "
                f"Multiple sources mapping to the same target causes silent data loss."
            )
            raise ValueError(msg)
        return self


class FieldMapper(BaseTransform):
    """Map, rename, and select row fields.

    Config options:
        schema: Required. Schema for input/output (use {mode: observed} for any fields)
        mapping: Dict of source_field -> target_field
            - Simple: {"old": "new"} renames old to new
            - Nested: {"meta.source": "origin"} extracts nested field
        select_only: If True, only include mapped fields (default: False)
        strict: If True, error on missing source fields (default: False)
    """

    name = "field_mapper"
    plugin_version = "1.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = FieldMapperConfig.from_dict(config)
        self._mapping: dict[str, str] = cfg.mapping
        self._select_only: bool = cfg.select_only
        self._strict: bool = cfg.strict
        self.validate_input = True  # Always validate — wrong types are upstream bugs

        # Mapping targets are the fields this transform guarantees in output.
        # Exclude targets that also appear as sources (identity/rename mappings
        # like {"score": "score"}) — these fields already exist in input and
        # would trigger false collision detection in TransformExecutor.
        self.declared_output_fields = frozenset(cfg.mapping.values()) - frozenset(cfg.mapping.keys())

        self._schema_config = cfg.schema_config

        self.input_schema, self.output_schema = self._create_schemas(
            cfg.schema_config,
            "FieldMapper",
            adds_fields=True,
        )
        self._output_schema_config = self._build_field_mapper_output_schema_config(cfg)

    def _build_field_mapper_output_schema_config(self, cfg: FieldMapperConfig) -> SchemaConfig:
        """Build output schema config reflecting the mapped output shape.

        FieldMapper is shape-changing: it removes source fields and adds target fields.
        The base _build_output_schema_config() incorrectly copies input fields into
        output guarantees. This method builds the correct output field set.

        When select_only=True: output guarantees are ONLY the mapping targets.
        When select_only=False: output guarantees are input fields MINUS removed
            sources PLUS new targets.
        """
        base_guaranteed = set(cfg.schema_config.guaranteed_fields or ())

        if cfg.select_only:
            # Only mapped targets appear in output
            output_fields = set(cfg.mapping.values())
        else:
            # Input fields minus removed sources plus new targets.
            # A source is removed from output when it's renamed to a different target.
            removed_sources = {source for source, target in cfg.mapping.items() if source != target and "." not in source}
            output_fields = (base_guaranteed - removed_sources) | set(cfg.mapping.values())

        # Always include declared_output_fields (targets that aren't also sources)
        output_fields |= self.declared_output_fields

        return SchemaConfig(
            mode=cfg.schema_config.mode,
            fields=cfg.schema_config.fields,
            guaranteed_fields=tuple(sorted(output_fields)) if output_fields else None,
            audit_fields=cfg.schema_config.audit_fields,
            required_fields=cfg.schema_config.required_fields,
        )

    def process(self, row: PipelineRow, ctx: TransformContext) -> TransformResult:
        """Apply field mapping to row.

        Args:
            row: Input row data
            ctx: Plugin context

        Returns:
            TransformResult with mapped row data

        Raises:
            ValidationError: If validate_input=True and row fails schema validation.
                This indicates a bug in the upstream source/transform.
        """
        # Keep a normalized dict view only for validation and dotted-path lookups.
        row_data = row.to_dict()

        # Start with empty or copy depending on select_only
        if self._select_only:
            output: dict[str, Any] = {}
        else:
            output = copy.deepcopy(row_data)

        # Apply mappings
        applied_mappings: dict[str, str] = {}
        for source, target in self._mapping.items():
            if "." in source:
                value = get_nested_field(row_data, source)
            elif source in row:
                value = row[source]
            else:
                value = MISSING

            if value is MISSING:
                if self._strict:
                    return TransformResult.error(
                        {"reason": "missing_field", "field": source, "message": f"Required field '{source}' not found in row"}
                    )
                continue  # Skip missing fields in non-strict mode

            # Remove old key if it exists (for rename within same dict)
            if not self._select_only and "." not in source and source in row:
                if source in output:
                    del output[source]
                else:
                    normalized_source = row.contract.resolve_name(source)
                    if normalized_source in output:
                        del output[normalized_source]

            output[target] = value
            applied_mappings[source] = target

        # Track field changes
        fields_modified: list[str] = []
        fields_added: list[str] = []
        for target in applied_mappings.values():
            if target in row:
                fields_modified.append(target)
            else:
                fields_added.append(target)

        # Update contract to reflect field mapping (renames and removals)
        output_contract = narrow_contract_to_output(
            input_contract=row.contract,
            output_row=output,
            renamed_fields=applied_mappings,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "mapped",
                "fields_modified": fields_modified,
                "fields_added": fields_added,
            },
        )

    def close(self) -> None:
        """No resources to release."""
        pass
