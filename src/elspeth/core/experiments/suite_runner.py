"""Suite runner orchestrating multiple experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, cast

import pandas as pd

from elspeth.core.base.plugin_context import PluginContext, apply_plugin_context
from elspeth.core.base.protocols import LLMClientProtocol, ResultSink
from elspeth.core.controls import create_cost_tracker, create_rate_limiter
from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.config_merger import ConfigMerger
from elspeth.core.experiments.plugin_registry import (
    create_aggregation_plugin,
    create_baseline_plugin,
    create_early_stop_plugin,
    create_row_plugin,
    create_validation_plugin,
    normalize_early_stop_definitions,
)
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.registries.middleware import create_middleware
from elspeth.core.registries.sink import sink_registry
from elspeth.core.security import resolve_determinism_level, resolve_security_level
from elspeth.core.validation.base import ConfigurationError


@dataclass
class ExperimentSuiteRunner:
    """Runner for executing experiment suites with shared LLM client and sinks.

    Orchestrates the execution of multiple experiments defined in an ExperimentSuite,
    managing shared resources like LLM clients and output sinks. Handles experiment
    initialization, execution, result collection, and artifact management.
    """

    suite: ExperimentSuite
    llm_client: LLMClientProtocol
    sinks: list[ResultSink]
    suite_root: Any = None
    config_path: Any = None
    _shared_middlewares: dict[str, Any] = field(default_factory=dict, init=False)

    def build_runner(
        self,
        config: ExperimentConfig,
        defaults: dict[str, Any],
        sinks: list[ResultSink],
    ) -> ExperimentRunner:
        """Build an ExperimentRunner from merged configuration layers.

        This method merges configuration from three sources (in priority order):
        1. Suite defaults (lowest)
        2. Prompt pack (middle, if specified)
        3. Experiment config (highest)

        The ConfigMerger helper consolidates the merge logic to reduce duplication.
        """
        # Resolve prompt pack
        prompt_packs = defaults.get("prompt_packs", {})
        pack_name = config.prompt_pack or defaults.get("prompt_pack")
        pack = prompt_packs.get(pack_name) if pack_name else None

        # Create merger helper
        merger = ConfigMerger(defaults, pack, config)

        # Merge prompt configuration
        prompt_defaults = merger.merge_dict("prompt_defaults")
        prompt_system = merger.merge_scalar("prompt_system", default="")
        prompt_template = merger.merge_scalar("prompt_template", default="")
        prompt_fields = merger.merge_scalar("prompt_fields")
        criteria = merger.merge_scalar("criteria")

        # Handle pack.prompts shorthand (if pack defines nested "prompts" dict)
        if pack and "prompts" in pack:
            pack_prompts = pack["prompts"]
            prompt_system = prompt_system or pack_prompts.get("system", "")
            prompt_template = prompt_template or pack_prompts.get("user", "")
            if not prompt_fields:
                prompt_fields = pack.get("prompt_fields")
            if not criteria:
                criteria = pack.get("criteria")

        # Merge middleware definitions
        middleware_defs = merger.merge_list("llm_middleware_defs", "llm_middlewares")

        # Merge concurrency configuration
        concurrency_dict = merger.merge_dict("concurrency_config", "concurrency")
        concurrency_config = concurrency_dict or None

        # Merge early stop configuration
        early_stop_plugin_defs = merger.merge_list(
            "early_stop_plugin_defs",
            "early_stop_plugins",
            transform=normalize_early_stop_definitions,
        )
        early_stop_dict = merger.merge_dict("early_stop_config", "early_stop")
        early_stop_config = early_stop_dict or None

        # If early_stop_config specified but no plugin defs, convert config to plugin defs
        if not early_stop_plugin_defs and early_stop_config:
            early_stop_plugin_defs.extend(normalize_early_stop_definitions(early_stop_config))

        # Merge plugin definitions (special pattern: pack prepends to defaults)
        row_defs = merger.merge_plugin_definitions("row_plugin_defs", "row_plugins")
        agg_defs = merger.merge_plugin_definitions("aggregator_plugin_defs", "aggregator_plugins")
        validation_defs = merger.merge_plugin_definitions("validation_plugin_defs", "validation_plugins")

        # Merge control definitions (scalar - last wins)
        rate_limiter_def = cast(dict[str, Any] | None, merger.merge_scalar("rate_limiter_def", "rate_limiter"))
        cost_tracker_def = cast(dict[str, Any] | None, merger.merge_scalar("cost_tracker_def", "cost_tracker"))

        # Resolve security level (most restrictive wins)
        security_level = resolve_security_level(
            config.security_level,
            pack.get("security_level") if pack else None,
            defaults.get("security_level"),
        )

        determinism_level = resolve_determinism_level(
            config.determinism_level,
            pack.get("determinism_level") if pack else None,
            defaults.get("determinism_level"),
        )

        # Create experiment context
        experiment_context = PluginContext(
            plugin_name=config.name,
            plugin_kind="experiment",
            security_level=security_level,
            determinism_level=determinism_level,
            provenance=(f"experiment:{config.name}.resolved",),
            suite_root=self.suite_root,
            config_path=self.config_path,
        )

        # Apply context to sinks
        for sink in sinks:
            sink_name = getattr(sink, "_elspeth_sink_name", getattr(sink, "_elspeth_plugin_name", sink.__class__.__name__))
            sink_level = getattr(sink, "security_level", experiment_context.security_level)
            sink_det_level = getattr(sink, "determinism_level", experiment_context.determinism_level)
            sink_context = experiment_context.derive(
                plugin_name=str(sink_name),
                plugin_kind="sink",
                security_level=sink_level,
                determinism_level=sink_det_level,
                provenance=(f"sink:{sink_name}.resolved",),
            )
            apply_plugin_context(sink, sink_context)

        # Instantiate plugins
        row_plugins = [create_row_plugin(defn, parent_context=experiment_context) for defn in row_defs] if row_defs else None
        aggregator_plugins = [create_aggregation_plugin(defn, parent_context=experiment_context) for defn in agg_defs] if agg_defs else None
        validation_plugins = (
            [create_validation_plugin(defn, parent_context=experiment_context) for defn in validation_defs] if validation_defs else None
        )
        early_stop_plugins = (
            [create_early_stop_plugin(defn, parent_context=experiment_context) for defn in early_stop_plugin_defs]
            if early_stop_plugin_defs
            else None
        )
        middlewares = self._create_middlewares(middleware_defs, parent_context=experiment_context)

        # Instantiate controls
        rate_limiter: Any | None = None
        if rate_limiter_def:
            rate_limiter = create_rate_limiter(rate_limiter_def, parent_context=experiment_context)
        elif defaults.get("rate_limiter") is not None:
            base = defaults["rate_limiter"]
            apply_plugin_context(
                base,
                experiment_context.derive(
                    plugin_name=getattr(base, "name", "rate_limiter"),
                    plugin_kind="rate_limiter",
                ),
            )
            rate_limiter = base

        cost_tracker: Any | None = None
        if cost_tracker_def:
            cost_tracker = create_cost_tracker(cost_tracker_def, parent_context=experiment_context)
        elif defaults.get("cost_tracker") is not None:
            base_tracker = defaults["cost_tracker"]
            apply_plugin_context(
                base_tracker,
                experiment_context.derive(
                    plugin_name=getattr(base_tracker, "name", "cost_tracker"),
                    plugin_kind="cost_tracker",
                ),
            )
            cost_tracker = base_tracker

        if not (prompt_system or "").strip():
            raise ConfigurationError(
                f"Experiment '{config.name}' has no system prompt defined. Provide one in the experiment, defaults, or prompt pack."
            )
        if not (prompt_template or "").strip():
            raise ConfigurationError(
                f"Experiment '{config.name}' has no user prompt defined. Provide one in the experiment, defaults, or prompt pack."
            )

        # After validation, we know these are not None (ConfigurationError would have been raised)
        if prompt_system is None:  # pragma: no cover - defensive, should be unreachable
            raise RuntimeError("prompt_system was None after validation")
        if prompt_template is None:  # pragma: no cover - defensive, should be unreachable
            raise RuntimeError("prompt_template was None after validation")

        runner_instance = ExperimentRunner(
            llm_client=self.llm_client,
            sinks=sinks,
            prompt_system=prompt_system,
            prompt_template=prompt_template,
            prompt_fields=prompt_fields,
            criteria=criteria,
            row_plugins=row_plugins,
            aggregator_plugins=aggregator_plugins,
            validation_plugins=validation_plugins,
            rate_limiter=rate_limiter,
            cost_tracker=cost_tracker,
            experiment_name=config.name,
            prompt_defaults=prompt_defaults or None,
            llm_middlewares=middlewares or None,
            concurrency_config=concurrency_config,
            security_level=security_level,
            determinism_level=experiment_context.determinism_level,
            early_stop_plugins=early_stop_plugins,
            early_stop_config=early_stop_config,
        )
        setattr(runner_instance, "plugin_context", experiment_context)
        return runner_instance

    def _create_middlewares(
        self,
        definitions: list[dict[str, Any]] | None,
        *,
        parent_context: PluginContext,
    ) -> list[Any]:
        instances: list[Any] = []
        for defn in definitions or []:
            name = defn.get("name") or defn.get("plugin")
            identifier = f"{name}:{json.dumps(defn.get('options', {}), sort_keys=True)}:{parent_context.security_level}"
            if identifier not in self._shared_middlewares:
                self._shared_middlewares[identifier] = create_middleware(defn, parent_context=parent_context)
            instances.append(self._shared_middlewares[identifier])
        return instances

    def _instantiate_sinks(self, defs: list[dict[str, Any]]) -> list[ResultSink]:
        sinks: list[ResultSink] = []
        for _, entry in enumerate(defs):
            plugin = entry.get("plugin")
            if not isinstance(plugin, str) or not plugin:
                raise ConfigurationError("Each sink definition must include a 'plugin' string")
            raw_options = dict(entry.get("options", {}))
            artifacts_cfg = raw_options.pop("artifacts", None)
            security_level = entry.get("security_level", raw_options.get("security_level"))
            if security_level is None:
                raise ConfigurationError(f"sink '{plugin}' requires a security_level")
            determinism_level = entry.get("determinism_level", raw_options.get("determinism_level"))
            if determinism_level is None:
                raise ConfigurationError(f"sink '{plugin}' requires a determinism_level")
            options_with_level = dict(raw_options)
            options_with_level["security_level"] = security_level
            options_with_level["determinism_level"] = determinism_level
            sink_registry.validate(plugin, options_with_level)
            sink = sink_registry.create(
                plugin,
                options_with_level,
                provenance=(f"sink:{plugin}.definition",),
            )
            setattr(sink, "_elspeth_artifact_config", artifacts_cfg or {})
            setattr(sink, "_elspeth_plugin_name", plugin)
            name_value = entry.get("name")
            base_name = name_value if isinstance(name_value, str) and name_value else plugin
            setattr(sink, "_elspeth_sink_name", base_name)
            sinks.append(sink)
        return sinks

    def run(
        self,
        df: pd.DataFrame,
        defaults: dict[str, Any] | None = None,
        sink_factory: Callable[[ExperimentConfig], list[ResultSink]] | None = None,
        preflight_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute all experiments in the suite.

        Args:
            df: Input DataFrame for experiments
            defaults: Default configuration values
            sink_factory: Optional factory for creating experiment-specific sinks
            preflight_info: Optional metadata about the run environment

        Returns:
            Dictionary containing results for all experiments
        """
        defaults = defaults or {}
        results: dict[str, Any] = {}
        prompt_packs = defaults.get("prompt_packs", {})

        experiments: list[ExperimentConfig] = []
        if self.suite.baseline:
            experiments.append(self.suite.baseline)
        experiments.extend(exp for exp in self.suite.experiments if exp != self.suite.baseline)

        baseline_payload = None
        suite_metadata = [
            {
                "experiment": exp.name,
                "temperature": exp.temperature,
                "max_tokens": exp.max_tokens,
                "is_baseline": exp.is_baseline,
            }
            for exp in experiments
        ]
        if preflight_info is None:
            preflight_info = {
                "experiment_count": len(experiments),
                "baseline": self.suite.baseline.name if self.suite.baseline else None,
            }
        notified_middlewares: dict[int, Any] = {}

        for experiment in experiments:
            pack_name = experiment.prompt_pack or defaults.get("prompt_pack")
            pack = prompt_packs.get(pack_name) if pack_name else None

            if experiment.sink_defs:
                sinks = self._instantiate_sinks(experiment.sink_defs)
            elif pack and pack.get("sinks"):
                sinks = self._instantiate_sinks(pack["sinks"])
            elif defaults.get("sink_defs"):
                sinks = self._instantiate_sinks(defaults["sink_defs"])
            else:
                sinks = sink_factory(experiment) if sink_factory else self.sinks

            runner = self.build_runner(
                experiment,
                {**defaults, "prompt_packs": prompt_packs, "prompt_pack": pack_name},
                sinks,
            )
            experiment_context = getattr(
                runner,
                "plugin_context",
                PluginContext(
                    plugin_name=experiment.name,
                    plugin_kind="experiment",
                    security_level=resolve_security_level(
                        experiment.security_level,
                        defaults.get("security_level"),
                    ),
                    provenance=(f"experiment:{experiment.name}.fallback",),
                    suite_root=self.suite_root,
                    config_path=self.config_path,
                ),
            )
            middlewares = cast(list[Any], runner.llm_middlewares or [])
            suite_notified = []
            for mw in middlewares:
                key = id(mw)
                if hasattr(mw, "on_suite_loaded") and key not in notified_middlewares:
                    mw.on_suite_loaded(suite_metadata, preflight_info)
                    notified_middlewares[key] = mw
                    suite_notified.append(mw)
                if hasattr(mw, "on_experiment_start"):
                    mw.on_experiment_start(
                        experiment.name,
                        {
                            "temperature": experiment.temperature,
                            "max_tokens": experiment.max_tokens,
                            "is_baseline": experiment.is_baseline,
                        },
                    )
            payload = runner.run(df)

            if baseline_payload is None and (experiment.is_baseline or experiment == self.suite.baseline):
                baseline_payload = payload

            results[experiment.name] = {
                "payload": payload,
                "config": experiment,
            }
            for mw in middlewares:
                if hasattr(mw, "on_experiment_complete"):
                    mw.on_experiment_complete(
                        experiment.name,
                        payload,
                        {
                            "temperature": experiment.temperature,
                            "max_tokens": experiment.max_tokens,
                            "is_baseline": experiment.is_baseline,
                        },
                    )

            if baseline_payload and experiment != self.suite.baseline:
                comp_defs = list(defaults.get("baseline_plugin_defs", []))
                if pack and pack.get("baseline_plugins"):
                    comp_defs = list(pack.get("baseline_plugins", [])) + comp_defs
                if experiment.baseline_plugin_defs:
                    comp_defs += experiment.baseline_plugin_defs
                comparisons = {}
                for defn in comp_defs:
                    plugin = create_baseline_plugin(defn, parent_context=experiment_context)
                    diff = plugin.compare(baseline_payload, payload)
                    if diff:
                        comparisons[plugin.name] = diff
                if comparisons:
                    payload["baseline_comparison"] = comparisons
                    results[experiment.name]["baseline_comparison"] = comparisons
                    for mw in middlewares:
                        if hasattr(mw, "on_baseline_comparison"):
                            mw.on_baseline_comparison(experiment.name, comparisons)

        for mw in notified_middlewares.values():
            if hasattr(mw, "on_suite_complete"):
                mw.on_suite_complete()

        return results
