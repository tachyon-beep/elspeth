"""Experiment orchestrator bridging datasource, LLM, and sinks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elspeth.core.controls import CostTracker, RateLimiter
from elspeth.core.experiments.plugin_registry import (
    create_aggregation_plugin,
    create_early_stop_plugin,
    create_row_plugin,
    create_validation_plugin,
)
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.protocols import DataSource, LLMClientProtocol, ResultSink
from elspeth.core.llm.registry import create_middlewares
from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.security import resolve_security_level


@dataclass
class OrchestratorConfig:  # pylint: disable=too-many-instance-attributes
    """Container describing orchestrator runtime configuration values."""

    llm_prompt: dict[str, str]
    prompt_fields: list[str] | None = None
    prompt_aliases: dict[str, str] | None = None
    criteria: list[dict[str, str]] | None = None
    row_plugin_defs: list[dict[str, Any]] | None = None
    aggregator_plugin_defs: list[dict[str, Any]] | None = None
    sink_defs: list[dict[str, Any]] | None = None
    prompt_pack: str | None = None
    baseline_plugin_defs: list[dict[str, Any]] | None = None
    validation_plugin_defs: list[dict[str, Any]] | None = None
    retry_config: dict[str, Any] | None = None
    checkpoint_config: dict[str, Any] | None = None
    llm_middleware_defs: list[dict[str, Any]] | None = None
    prompt_defaults: dict[str, Any] | None = None
    concurrency_config: dict[str, Any] | None = None
    early_stop_config: dict[str, Any] | None = None
    early_stop_plugin_defs: list[dict[str, Any]] | None = None
    max_rows: int | None = None


class ExperimentOrchestrator:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Coordinates datasource loading, experiment execution, and sink writes."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        datasource: DataSource,
        llm_client: LLMClientProtocol,
        sinks: list[ResultSink],
        config: OrchestratorConfig,
        experiment_runner: ExperimentRunner | None = None,
        rate_limiter: RateLimiter | None = None,
        cost_tracker: CostTracker | None = None,
        name: str = "default",
    ):
        self.datasource = datasource
        self.llm_client = llm_client
        self.sinks = sinks
        self.config = config
        self.rate_limiter = rate_limiter
        self.cost_tracker = cost_tracker
        self.name = name
        security_level = resolve_security_level(
            getattr(datasource, "security_level", None),
            getattr(llm_client, "security_level", None),
        )
        experiment_context = PluginContext(
            plugin_name=name,
            plugin_kind="experiment",
            security_level=security_level,
            provenance=(f"orchestrator:{name}.resolved",),
        )

        if self.rate_limiter is not None:
            apply_plugin_context(
                self.rate_limiter,
                experiment_context.derive(
                    plugin_name=getattr(self.rate_limiter, "name", "rate_limiter"),
                    plugin_kind="rate_limiter",
                ),
            )
        if self.cost_tracker is not None:
            apply_plugin_context(
                self.cost_tracker,
                experiment_context.derive(
                    plugin_name=getattr(self.cost_tracker, "name", "cost_tracker"),
                    plugin_kind="cost_tracker",
                ),
            )

        row_plugins = (
            [create_row_plugin(defn, parent_context=experiment_context) for defn in config.row_plugin_defs]
            if config.row_plugin_defs
            else None
        )
        aggregator_plugins = (
            [create_aggregation_plugin(defn, parent_context=experiment_context) for defn in config.aggregator_plugin_defs]
            if config.aggregator_plugin_defs
            else None
        )
        validation_plugins = (
            [create_validation_plugin(defn, parent_context=experiment_context) for defn in config.validation_plugin_defs]
            if config.validation_plugin_defs
            else None
        )
        early_stop_plugins = (
            [create_early_stop_plugin(defn, parent_context=experiment_context) for defn in config.early_stop_plugin_defs]
            if config.early_stop_plugin_defs
            else None
        )
        self.early_stop_plugins = early_stop_plugins
        self.validation_plugins = validation_plugins

        middlewares = create_middlewares(config.llm_middleware_defs, parent_context=experiment_context)

        self.experiment_runner = experiment_runner or ExperimentRunner(
            llm_client=llm_client,
            sinks=sinks,
            prompt_system=config.llm_prompt["system"],
            prompt_template=config.llm_prompt["user"],
            prompt_fields=config.prompt_fields,
            criteria=config.criteria,
            row_plugins=row_plugins,
            aggregator_plugins=aggregator_plugins,
            validation_plugins=validation_plugins,
            rate_limiter=self.rate_limiter,
            cost_tracker=self.cost_tracker,
            experiment_name=name,
            retry_config=config.retry_config,
            checkpoint_config=config.checkpoint_config,
            llm_middlewares=middlewares,
            prompt_defaults=config.prompt_defaults,
            concurrency_config=config.concurrency_config,
            security_level=experiment_context.security_level,
            early_stop_plugins=early_stop_plugins,
            early_stop_config=config.early_stop_config,
        )
        setattr(self.experiment_runner, "plugin_context", experiment_context)

    def run(self) -> dict[str, Any]:
        """Execute all configured experiments and return the runner payload."""

        df = self.datasource.load()

        # Apply row limit if configured
        if self.config.max_rows is not None:
            df = df.head(self.config.max_rows)

        system_prompt = self.config.llm_prompt["system"]
        user_prompt_format = self.config.llm_prompt["user"]

        runner = self.experiment_runner
        runner.prompt_system = system_prompt
        runner.prompt_template = user_prompt_format
        runner.prompt_fields = self.config.prompt_fields
        runner.criteria = self.config.criteria
        runner.rate_limiter = self.rate_limiter
        runner.cost_tracker = self.cost_tracker
        runner.experiment_name = self.name
        runner.concurrency_config = self.config.concurrency_config
        runner.early_stop_plugins = self.early_stop_plugins
        runner.validation_plugins = self.validation_plugins
        payload = runner.run(df)
        return payload
