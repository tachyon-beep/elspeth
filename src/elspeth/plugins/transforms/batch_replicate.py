"""Batch replicate transform plugin.

Demonstrates output_mode: transform deaggregation by replicating rows.
Each input row is replicated based on a 'copies' field, producing more
output rows than input rows (N inputs -> M outputs where M >= N).

IMPORTANT: This transform uses is_batch_aware=True, meaning the engine
will buffer rows and call process() with a list when the trigger fires.

For output_mode: transform, the engine creates NEW tokens for each output
row, with parent linkage to track deaggregation lineage.
"""

import copy
from typing import Any

import structlog
from pydantic import Field, model_validator

from elspeth.contracts.contexts import TransformContext
from elspeth.contracts.errors import TransformSuccessReason
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.plugins.infrastructure.base import BaseTransform
from elspeth.plugins.infrastructure.config_base import TransformDataConfig
from elspeth.plugins.infrastructure.results import TransformResult

logger = structlog.get_logger(__name__)


class BatchReplicateConfig(TransformDataConfig):
    """Configuration for batch replicate transform.

    Requires a field that specifies how many copies of each row to produce.
    """

    copies_field: str = Field(
        default="copies",
        description="Name of the field containing the number of copies to make",
        min_length=1,
    )
    default_copies: int = Field(
        default=1,
        ge=1,
        le=10000,
        description="Default number of copies if copies_field is missing or invalid",
    )
    max_copies: int = Field(
        default=10000,
        ge=1,
        le=10000,
        description="Upper bound on copies per row to prevent unbounded replication",
    )
    include_copy_index: bool = Field(
        default=True,
        description="Whether to add a 'copy_index' field (0-based) to each output row",
    )

    @model_validator(mode="after")
    def _default_within_max(self) -> "BatchReplicateConfig":
        if self.default_copies > self.max_copies:
            msg = f"default_copies ({self.default_copies}) exceeds max_copies ({self.max_copies})"
            raise ValueError(msg)
        return self


class BatchReplicate(BaseTransform):
    """Replicate rows based on a copies field.

    This is a batch-aware transform that demonstrates output_mode: transform
    deaggregation. It receives N input rows and produces M output rows where
    M is the sum of all copies values.

    Example: If input has 3 rows with copies=2,3,1 respectively:
    - Input: 3 rows
    - Output: 6 rows (2 + 3 + 1)
    - Each output row has copy_index showing which copy it is

    Config options:
        schema: Required. Schema for input validation
        copies_field: Field name for copy count (default: "copies")
        default_copies: Fallback if field missing (default: 1)
        include_copy_index: Add copy_index field (default: True)

    Example YAML:
        aggregations:
          - name: replicate_batch
            plugin: batch_replicate
            trigger:
              count: 5
            output_mode: transform  # CRITICAL: Creates new tokens for outputs
            options:
              schema:
                mode: observed
              copies_field: quantity
              default_copies: 1
    """

    name = "batch_replicate"
    plugin_version = "1.0.0"
    is_batch_aware = True  # CRITICAL: Engine buffers rows for batch processing

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = BatchReplicateConfig.from_dict(config)

        # Declare output fields for centralized collision detection.
        self.declared_output_fields = frozenset(["copy_index"] if cfg.include_copy_index else [])
        self._copies_field = cfg.copies_field
        self._default_copies = cfg.default_copies
        self._max_copies = cfg.max_copies
        self._include_copy_index = cfg.include_copy_index

        self._schema_config = cfg.schema_config

        self.input_schema, self.output_schema = self._create_schemas(
            cfg.schema_config,
            "BatchReplicate",
            adds_fields=True,
        )
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)

    def process(  # type: ignore[override] # Batch signature: list[PipelineRow] instead of PipelineRow
        self, rows: list[PipelineRow], ctx: TransformContext
    ) -> TransformResult:
        """Replicate each row based on its copies field.

        Args:
            rows: List of input rows (batch-aware receives list[PipelineRow])
            ctx: Plugin context

        Returns:
            TransformResult.success_multi() with replicated rows
        """
        if not rows:
            # Empty batch is an anomaly — return error, not fabricated data.
            # A synthetic PipelineRow({batch_empty: True}) would flow through
            # the pipeline as real data, corrupting the audit trail.
            return TransformResult.error(
                {"reason": "empty_batch"},
                retryable=False,
            )

        valid_rows: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        quarantined_indices: list[int] = []

        for row_index, row in enumerate(rows):
            # Get copies count - field is optional, type must be correct if present
            if self._copies_field not in row:
                # Field missing - use default, still bounded by max_copies
                copies = min(self._default_copies, self._max_copies)
            else:
                raw_copies = row[self._copies_field]

                # Contract enforcement: copies_field must be int if present
                # Tier 2 pipeline data - wrong types indicate upstream bug
                # Use `type(x) is int` instead of `isinstance(x, int)` because
                # bool is a subclass of int in Python, so isinstance(True, int)
                # returns True. We must reject bool values explicitly.
                if type(raw_copies) is not int:
                    raise TypeError(
                        f"Field '{self._copies_field}' must be int, got {type(raw_copies).__name__}. "
                        f"This indicates an upstream validation bug - check source schema or prior transforms."
                    )

                # Value-level validation: copies must be >= 1 and <= max_copies
                # Tier 2 operation safety - type is correct but value is unsafe
                if raw_copies < 1 or raw_copies > self._max_copies:
                    quarantined.append(
                        {
                            "reason": "invalid_copies",
                            "field": self._copies_field,
                            "value": raw_copies,
                            "row_data": row.to_dict(),
                        }
                    )
                    quarantined_indices.append(row_index)
                    continue

                copies = raw_copies

            # Create copies of this row
            for copy_idx in range(copies):
                # Deep copy ensures each replica is fully independent —
                # shallow copy would share nested mutable values across copies
                output = copy.deepcopy(row.to_dict())
                if self._include_copy_index:
                    output["copy_index"] = copy_idx
                valid_rows.append(output)

        # If ALL rows were quarantined, return error — no valid output to expand
        if not valid_rows:
            return TransformResult.error(
                {
                    "reason": "all_rows_failed",
                    "error": f"All {len(quarantined)} rows quarantined: invalid copies values",
                    "row_errors": [{"row_index": i, "reason": q["reason"]} for i, q in enumerate(quarantined)],
                },
                retryable=False,
            )

        # Build contract from union of ALL valid output row keys (not just first)
        all_keys: dict[str, None] = {}
        for r in valid_rows:
            for key in r:
                all_keys[key] = None

        fields = tuple(
            FieldContract(
                normalized_name=key,
                original_name=key,
                python_type=object,  # OBSERVED mode - infer all as object type
                required=False,
                source="inferred",
            )
            for key in all_keys
        )
        output_contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)

        # Record each quarantine decision in the audit trail so an auditor
        # can trace which specific source rows were dropped and why.
        # Without this, quarantined rows are only in success_reason metadata —
        # invisible to Landscape queries and explain(token_id).
        if quarantined:
            logger.warning(
                "batch_replicate_rows_quarantined",
                quarantined_count=len(quarantined),
                total_rows=len(rows),
                valid_count=len(valid_rows),
                quarantined_indices=quarantined_indices,
            )

        success_reason: TransformSuccessReason = {
            "action": "processed",
            "fields_added": ["copy_index"] if self._include_copy_index else [],
        }
        if quarantined:
            success_reason["metadata"] = {
                "quarantined_count": len(quarantined),
                "quarantined": quarantined,
                "quarantined_indices": quarantined_indices,
            }

        # Return only valid replicated rows — quarantined rows are in success_reason
        return TransformResult.success_multi(
            [PipelineRow(r, output_contract) for r in valid_rows],
            success_reason=success_reason,
        )

    def close(self) -> None:
        """No resources to release."""
        pass
