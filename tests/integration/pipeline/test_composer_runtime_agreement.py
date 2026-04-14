"""Composer/runtime agreement test for shared schema-contract rules.

Verifies that the composer's schema contract validation and the runtime DAG
validator agree on pass/fail for the same pipeline configuration in the
shared-contract cases covered here. This suite does not claim global
equivalence; intentionally stricter composer-only checks should live in
separate tests with explicit documentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.core.config import (
    AggregationSettings,
    ElspethSettings,
    SinkSettings,
    SourceSettings,
    TransformSettings,
    TriggerConfig,
)
from elspeth.core.dag import ExecutionGraph, GraphValidationError
from elspeth.plugins.infrastructure.config_base import PluginConfigError
from elspeth.web.composer.state import (
    CompositionState,
    EdgeSpec,
    NodeSpec,
    OutputSpec,
    PipelineMetadata,
    SourceSpec,
)


class TestComposerRuntimeAgreement:
    """Composer and runtime validators must agree on shared contract cases."""

    def _empty_state(self) -> CompositionState:
        return CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=1,
        )

    def _build_runtime_graph(
        self,
        *,
        source_plugin: str,
        source_options: dict[str, Any],
        sink_options: dict[str, Any],
        transform_options: dict[str, Any] | None = None,
        transform_plugin: str | None = "value_transform",
        aggregation_options: dict[str, Any] | None = None,
        aggregation_plugin: str | None = None,
    ) -> ExecutionGraph:
        """Build a runtime ExecutionGraph through the production assembly path."""
        if transform_plugin is not None and aggregation_plugin is not None:
            raise AssertionError(
                "Task 8 agreement helper supports either a transform chain or an aggregation chain, not both in the same case."
            )

        source_on_success = "agg1" if aggregation_plugin is not None else ("t1" if transform_plugin is not None else "main")
        transforms: list[TransformSettings] = []
        aggregations: list[AggregationSettings] = []

        if transform_plugin is not None:
            transforms.append(
                TransformSettings(
                    name="t1",
                    plugin=transform_plugin,
                    input="t1",
                    on_success="main",
                    on_error="discard",
                    options=transform_options or {},
                )
            )

        if aggregation_plugin is not None:
            aggregations.append(
                AggregationSettings(
                    name="agg1",
                    plugin=aggregation_plugin,
                    input="agg1",
                    on_success="main",
                    on_error="discard",
                    trigger=TriggerConfig(count=1),
                    options=aggregation_options or {},
                )
            )

        config = ElspethSettings(
            source=SourceSettings(
                plugin=source_plugin,
                on_success=source_on_success,
                options={**source_options, "on_validation_failure": "discard"},
            ),
            transforms=transforms,
            aggregations=aggregations,
            sinks={
                "main": SinkSettings(
                    plugin="csv",
                    on_write_failure="discard",
                    options=sink_options,
                )
            },
        )
        plugins = instantiate_plugins_from_config(config)
        return ExecutionGraph.from_plugin_instances(
            source=plugins.source,
            source_settings=plugins.source_settings,
            transforms=plugins.transforms,
            sinks=plugins.sinks,
            aggregations=plugins.aggregations,
            gates=list(config.gates),
        )

    def test_both_reject_missing_required_field(self, tmp_path: Path) -> None:
        """Both validators reject when a consumer requires an unsatisfied field."""
        text_path = tmp_path / "input.txt"
        text_path.write_text("hello\n", encoding="utf-8")
        output_path = tmp_path / "out.csv"

        state = self._empty_state()
        state = state.with_source(
            SourceSpec(
                plugin="text",
                on_success="t1",
                options={
                    "path": str(text_path),
                    "column": "line",
                    "schema": {"mode": "observed"},
                },
                on_validation_failure="quarantine",
            )
        )
        state = state.with_node(
            NodeSpec(
                id="t1",
                node_type="transform",
                plugin="value_transform",
                input="t1",
                on_success="main",
                on_error=None,
                options={
                    "required_input_fields": ["text"],
                    "operations": [
                        {
                            "target": "out",
                            "expression": "row['text'] + ' world'",
                        }
                    ],
                    "schema": {"mode": "observed"},
                },
                condition=None,
                routes=None,
                fork_to=None,
                branches=None,
                policy=None,
                merge=None,
            )
        )
        state = state.with_output(
            OutputSpec(
                name="main",
                plugin="csv",
                options={
                    "path": str(output_path),
                    "schema": {"mode": "observed"},
                },
                on_write_failure="discard",
            )
        )
        state = state.with_edge(
            EdgeSpec(
                id="e1",
                from_node="source",
                to_node="t1",
                edge_type="on_success",
                label=None,
            )
        )

        composer_result = state.validate()
        assert not composer_result.is_valid, "Composer should reject: source column is 'line' but consumer requires 'text'."
        assert any("schema contract violation" in entry.message.lower() for entry in composer_result.errors)

        with pytest.raises(GraphValidationError) as exc_info:
            graph = self._build_runtime_graph(
                source_plugin="text",
                source_options={
                    "path": str(text_path),
                    "column": "line",
                    "schema": {"mode": "observed"},
                },
                transform_options={
                    "required_input_fields": ["text"],
                    "operations": [
                        {
                            "target": "out",
                            "expression": "row['text'] + ' world'",
                        }
                    ],
                    "schema": {"mode": "observed"},
                },
                sink_options={
                    "path": str(output_path),
                    "schema": {"mode": "observed"},
                },
            )
            graph.validate_edge_compatibility()
        assert "text" in str(exc_info.value).lower()

    def test_both_accept_observed_text_source_with_auto_guarantee(
        self,
        tmp_path: Path,
    ) -> None:
        """Both validators accept the observed-text special-case contract."""
        text_path = tmp_path / "input.txt"
        text_path.write_text("hello\n", encoding="utf-8")
        output_path = tmp_path / "out.csv"

        state = self._empty_state()
        state = state.with_source(
            SourceSpec(
                plugin="text",
                on_success="t1",
                options={
                    "path": str(text_path),
                    "column": "text",
                    "schema": {"mode": "observed"},
                },
                on_validation_failure="quarantine",
            )
        )
        state = state.with_node(
            NodeSpec(
                id="t1",
                node_type="transform",
                plugin="value_transform",
                input="t1",
                on_success="main",
                on_error=None,
                options={
                    "required_input_fields": ["text"],
                    "operations": [
                        {
                            "target": "out",
                            "expression": "row['text'] + ' world'",
                        }
                    ],
                    "schema": {"mode": "observed"},
                },
                condition=None,
                routes=None,
                fork_to=None,
                branches=None,
                policy=None,
                merge=None,
            )
        )
        state = state.with_output(
            OutputSpec(
                name="main",
                plugin="csv",
                options={
                    "path": str(output_path),
                    "schema": {"mode": "observed"},
                },
                on_write_failure="discard",
            )
        )
        state = state.with_edge(
            EdgeSpec(
                id="e1",
                from_node="source",
                to_node="t1",
                edge_type="on_success",
                label=None,
            )
        )

        composer_result = state.validate()
        assert composer_result.is_valid, composer_result.errors

        graph = self._build_runtime_graph(
            source_plugin="text",
            source_options={
                "path": str(text_path),
                "column": "text",
                "schema": {"mode": "observed"},
            },
            transform_options={
                "required_input_fields": ["text"],
                "operations": [
                    {
                        "target": "out",
                        "expression": "row['text'] + ' world'",
                    }
                ],
                "schema": {"mode": "observed"},
            },
            sink_options={
                "path": str(output_path),
                "schema": {"mode": "observed"},
            },
        )
        graph.validate_edge_compatibility()

    def test_both_reject_observed_text_source_keyword_column(self, tmp_path: Path) -> None:
        """Invalid keyword columns must not create a false composer/runtime accept."""
        text_path = tmp_path / "input.txt"
        text_path.write_text("hello\n", encoding="utf-8")
        output_path = tmp_path / "out.csv"

        state = self._empty_state()
        state = state.with_source(
            SourceSpec(
                plugin="text",
                on_success="t1",
                options={
                    "path": str(text_path),
                    "column": "class",
                    "schema": {"mode": "observed"},
                },
                on_validation_failure="quarantine",
            )
        )
        state = state.with_node(
            NodeSpec(
                id="t1",
                node_type="transform",
                plugin="value_transform",
                input="t1",
                on_success="main",
                on_error=None,
                options={
                    "required_input_fields": ["class"],
                    "operations": [
                        {
                            "target": "out",
                            "expression": "row['class'] + ' world'",
                        }
                    ],
                    "schema": {"mode": "observed"},
                },
                condition=None,
                routes=None,
                fork_to=None,
                branches=None,
                policy=None,
                merge=None,
            )
        )
        state = state.with_output(
            OutputSpec(
                name="main",
                plugin="csv",
                options={
                    "path": str(output_path),
                    "schema": {"mode": "observed"},
                },
                on_write_failure="discard",
            )
        )
        state = state.with_edge(
            EdgeSpec(
                id="e1",
                from_node="source",
                to_node="t1",
                edge_type="on_success",
                label=None,
            )
        )

        composer_result = state.validate()
        assert not composer_result.is_valid, (
            "Composer must not infer an observed-text guarantee for a keyword column name that runtime text-source config rejects."
        )
        assert any("class" in entry.message.lower() for entry in composer_result.errors)

        with pytest.raises(PluginConfigError, match="Python keyword"):
            self._build_runtime_graph(
                source_plugin="text",
                source_options={
                    "path": str(text_path),
                    "column": "class",
                    "schema": {"mode": "observed"},
                },
                transform_options={
                    "required_input_fields": ["class"],
                    "operations": [
                        {
                            "target": "out",
                            "expression": "row['class'] + ' world'",
                        }
                    ],
                    "schema": {"mode": "observed"},
                },
                sink_options={
                    "path": str(output_path),
                    "schema": {"mode": "observed"},
                },
            )

    def test_both_reject_strict_sink_typed_requirement_without_upstream_guarantee(
        self,
        tmp_path: Path,
    ) -> None:
        """Both validators reject when a strict sink requires an ungiven field."""
        text_path = tmp_path / "input.txt"
        text_path.write_text("hello\n", encoding="utf-8")
        output_path = tmp_path / "out.csv"

        state = self._empty_state()
        state = state.with_source(
            SourceSpec(
                plugin="text",
                on_success="main",
                options={
                    "path": str(text_path),
                    "column": "line",
                    "schema": {"mode": "observed"},
                },
                on_validation_failure="quarantine",
            )
        )
        state = state.with_output(
            OutputSpec(
                name="main",
                plugin="csv",
                options={
                    "path": str(output_path),
                    "schema": {"mode": "fixed", "fields": ["text: str"]},
                },
                on_write_failure="discard",
            )
        )

        composer_result = state.validate()
        assert not composer_result.is_valid, "Composer should reject: strict sink requires 'text' but upstream guarantees only 'line'."
        assert any(contract.to_id == "output:main" and not contract.satisfied for contract in composer_result.edge_contracts)

        with pytest.raises(GraphValidationError) as exc_info:
            graph = self._build_runtime_graph(
                source_plugin="text",
                source_options={
                    "path": str(text_path),
                    "column": "line",
                    "schema": {"mode": "observed"},
                },
                transform_plugin=None,
                sink_options={
                    "path": str(output_path),
                    "schema": {"mode": "fixed", "fields": ["text: str"]},
                },
            )
            graph.validate_edge_compatibility()
        assert "requires" in str(exc_info.value).lower()

    def test_both_reject_aggregation_nested_required_input_fields_without_upstream_guarantee(
        self,
        tmp_path: Path,
    ) -> None:
        """Both validators reject the shared aggregation required-input case."""
        csv_path = tmp_path / "input.csv"
        csv_path.write_text("line\nhello\n", encoding="utf-8")
        output_path = tmp_path / "out.csv"

        state = self._empty_state()
        state = state.with_source(
            SourceSpec(
                plugin="csv",
                on_success="agg1",
                options={
                    "path": str(csv_path),
                    "schema": {"mode": "fixed", "fields": ["line: str"]},
                },
                on_validation_failure="quarantine",
            )
        )
        state = state.with_node(
            NodeSpec(
                id="agg1",
                node_type="aggregation",
                plugin="batch_stats",
                input="agg1",
                on_success="main",
                on_error=None,
                options={
                    "value_field": "value",
                    "required_input_fields": ["value"],
                    "schema": {"mode": "observed"},
                },
                condition=None,
                routes=None,
                fork_to=None,
                branches=None,
                policy=None,
                merge=None,
            )
        )
        state = state.with_output(
            OutputSpec(
                name="main",
                plugin="csv",
                options={
                    "path": str(output_path),
                    "schema": {"mode": "observed"},
                },
                on_write_failure="discard",
            )
        )
        state = state.with_edge(
            EdgeSpec(
                id="e1",
                from_node="source",
                to_node="agg1",
                edge_type="on_success",
                label=None,
            )
        )

        composer_result = state.validate()
        assert not composer_result.is_valid
        assert any("value" in entry.message.lower() for entry in composer_result.errors)

        with pytest.raises(GraphValidationError) as exc_info:
            graph = self._build_runtime_graph(
                source_plugin="csv",
                source_options={
                    "path": str(csv_path),
                    "schema": {"mode": "fixed", "fields": ["line: str"]},
                },
                transform_plugin=None,
                aggregation_plugin="batch_stats",
                aggregation_options={
                    "value_field": "value",
                    "required_input_fields": ["value"],
                    "schema": {"mode": "observed"},
                },
                sink_options={
                    "path": str(output_path),
                    "schema": {"mode": "observed"},
                },
            )
            graph.validate_edge_compatibility()
        assert "value" in str(exc_info.value).lower()
