"""PassThrough transform plugin.

Passes rows through unchanged. Useful for testing and debugging pipelines.

IMPORTANT: Transforms use allow_coercion=False to catch upstream bugs.
If the source outputs wrong types, the transform crashes immediately.
"""

import copy
from typing import Any

from pydantic import Field

from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.config_base import TransformDataConfig
from elspeth.plugins.results import TransformResult


class PassThroughConfig(TransformDataConfig):
    """Configuration for passthrough transform.

    Requires 'schema' in config to define input/output expectations.
    Use 'schema: {mode: observed}' for dynamic field handling.
    """

    validate_input: bool = Field(
        default=False,
        description="If True, validate input against schema (default: False)",
    )


class PassThrough(BaseTransform):
    """Pass rows through unchanged.

    Use cases:
    - Testing pipeline wiring without modification
    - Debugging data flow (add logging in subclass)
    - Placeholder for future transform logic

    Config options:
        schema: Required. Schema for input/output (use {mode: observed} for any fields)
        validate_input: If True, validate input against schema (default: False)
    """

    name = "passthrough"
    plugin_version = "1.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = PassThroughConfig.from_dict(config)
        self.validate_input = cfg.validate_input

        self._schema_config = cfg.schema_config
        self.input_schema, self.output_schema = self._create_schemas(cfg.schema_config, "PassThrough")

    def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
        """Return row unchanged (deep copy to prevent mutation).

        Args:
            row: Input row data
            ctx: Plugin context

        Returns:
            TransformResult with unchanged row data

        Raises:
            ValidationError: If validate_input=True and row fails schema validation.
                This indicates a bug in the upstream source/transform.
        """
        return TransformResult.success(
            PipelineRow(copy.deepcopy(row.to_dict()), row.contract),
            success_reason={"action": "passthrough"},
        )

    def close(self) -> None:
        """No resources to release."""
        pass
