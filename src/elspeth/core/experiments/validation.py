from __future__ import annotations

from typing import Type

from elspeth.core.base.schema import DataFrameSchema, validate_schema_compatibility


def validate_plugin_schemas(
    datasource_schema: Type[DataFrameSchema],
    *,
    row_plugins: list | None = None,
    aggregator_plugins: list | None = None,
    validation_plugins: list | None = None,
) -> None:
    """Validate that plugins' input_schema declarations are compatible with datasource schema.

    This function mirrors the logic used by ExperimentRunner and is exposed as a public utility
    so callers (e.g., CLI preflight) can perform checks without invoking the runner.
    """

    # Row plugins
    for row_plugin in row_plugins or []:
        # Enforce input_schema requirement when registry declares so
        requires = bool(getattr(row_plugin, "_elspeth_requires_input_schema", False))
        plugin_schema = row_plugin.input_schema() if hasattr(row_plugin, "input_schema") and callable(row_plugin.input_schema) else None
        if requires and plugin_schema is None:
            raise ValueError(f"Row plugin '{getattr(row_plugin, 'name', row_plugin)}' requires input_schema() but none was provided")
        if plugin_schema is not None:
            validate_schema_compatibility(
                datasource_schema,
                plugin_schema,
                plugin_name=f"row_plugin:{getattr(row_plugin, 'name', row_plugin)}",
            )

    # Aggregation plugins
    for agg_plugin in aggregator_plugins or []:
        requires = bool(getattr(agg_plugin, "_elspeth_requires_input_schema", False))
        plugin_schema = agg_plugin.input_schema() if hasattr(agg_plugin, "input_schema") and callable(agg_plugin.input_schema) else None
        if requires and plugin_schema is None:
            raise ValueError(
                f"Aggregation plugin '{getattr(agg_plugin, 'name', agg_plugin)}' requires input_schema() but none was provided"
            )
        if plugin_schema is not None:
            validate_schema_compatibility(
                datasource_schema,
                plugin_schema,
                plugin_name=f"aggregation_plugin:{getattr(agg_plugin, 'name', agg_plugin)}",
            )

    # Validation plugins
    for v_plugin in validation_plugins or []:
        requires = bool(getattr(v_plugin, "_elspeth_requires_input_schema", False))
        plugin_schema = v_plugin.input_schema() if hasattr(v_plugin, "input_schema") and callable(v_plugin.input_schema) else None
        if requires and plugin_schema is None:
            raise ValueError(f"Validation plugin '{getattr(v_plugin, 'name', v_plugin)}' requires input_schema() but none was provided")
        if plugin_schema is not None:
            validate_schema_compatibility(
                datasource_schema,
                plugin_schema,
                plugin_name=f"validation_plugin:{getattr(v_plugin, 'name', v_plugin)}",
            )


__all__ = ["validate_plugin_schemas"]
