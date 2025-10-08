"""Experiment orchestrator bridging datasource, LLM, and sinks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd

from dmp.core.interfaces import DataSource, LLMClientProtocol, ResultSink
from dmp.core.experiments.runner import ExperimentRunner
from dmp.core.controls import RateLimiter, CostTracker
from dmp.core.llm.registry import create_middlewares
from dmp.core.experiments.plugin_registry import create_row_plugin, create_aggregation_plugin, create_early_stop_plugin


@dataclass
class OrchestratorConfig:
    llm_prompt: Dict[str, str]
    prompt_fields: List[str] | None = None
    prompt_aliases: Dict[str, str] | None = None
    criteria: List[Dict[str, str]] | None = None
    row_plugin_defs: List[Dict[str, Any]] | None = None
    aggregator_plugin_defs: List[Dict[str, Any]] | None = None
    sink_defs: List[Dict[str, Any]] | None = None
    prompt_pack: str | None = None
    baseline_plugin_defs: List[Dict[str, Any]] | None = None
    retry_config: Dict[str, Any] | None = None
    checkpoint_config: Dict[str, Any] | None = None
    llm_middleware_defs: List[Dict[str, Any]] | None = None
    prompt_defaults: Dict[str, Any] | None = None
    concurrency_config: Dict[str, Any] | None = None
    early_stop_config: Dict[str, Any] | None = None
    early_stop_plugin_defs: List[Dict[str, Any]] | None = None


class ExperimentOrchestrator:
    def __init__(
        self,
        *,
        datasource: DataSource,
        llm_client: LLMClientProtocol,
        sinks: List[ResultSink],
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
        row_plugins = None
        if config.row_plugin_defs:
            row_plugins = [create_row_plugin(defn) for defn in config.row_plugin_defs]
        aggregator_plugins = None
        if config.aggregator_plugin_defs:
            aggregator_plugins = [create_aggregation_plugin(defn) for defn in config.aggregator_plugin_defs]
        early_stop_plugins = None
        if config.early_stop_plugin_defs:
            early_stop_plugins = [create_early_stop_plugin(defn) for defn in config.early_stop_plugin_defs]
        self.early_stop_plugins = early_stop_plugins

        self.experiment_runner = experiment_runner or ExperimentRunner(
            llm_client=llm_client,
            sinks=sinks,
            prompt_system=config.llm_prompt["system"],
            prompt_template=config.llm_prompt["user"],
            prompt_fields=config.prompt_fields,
            criteria=config.criteria,
            row_plugins=row_plugins,
            aggregator_plugins=aggregator_plugins,
            rate_limiter=rate_limiter,
            cost_tracker=cost_tracker,
            experiment_name=name,
            retry_config=config.retry_config,
            checkpoint_config=config.checkpoint_config,
            llm_middlewares=create_middlewares(config.llm_middleware_defs),
            prompt_defaults=config.prompt_defaults,
            concurrency_config=config.concurrency_config,
            early_stop_plugins=early_stop_plugins,
            early_stop_config=config.early_stop_config,
        )

    def run(self) -> Dict[str, Any]:
        df = self.datasource.load()
        system_prompt = self.config.llm_prompt["system"]
        user_prompt_format = self.config.llm_prompt["user"]

        results = []
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
        payload = runner.run(df)
        return payload
