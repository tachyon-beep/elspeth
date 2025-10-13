"""Suite runner orchestrating multiple experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, cast

from elspeth.core import registry as core_registry
from elspeth.core.controls import create_cost_tracker, create_rate_limiter
from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.plugin_registry import (
    create_aggregation_plugin,
    create_baseline_plugin,
    create_early_stop_plugin,
    create_row_plugin,
    create_validation_plugin,
    normalize_early_stop_definitions,
)
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.interfaces import LLMClientProtocol, ResultSink
from elspeth.core.llm.registry import create_middleware
from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.security import resolve_security_level
from elspeth.core.validation import ConfigurationError


@dataclass
class ExperimentSuiteRunner:
    suite: ExperimentSuite
    llm_client: LLMClientProtocol
    sinks: List[ResultSink]
    _shared_middlewares: Dict[str, Any] = field(default_factory=dict, init=False)

    def build_runner(
        self,
        config: ExperimentConfig,
        defaults: Dict[str, Any],
        sinks: List[ResultSink],
    ) -> ExperimentRunner:
        prompt_packs = defaults.get("prompt_packs", {})
        pack_name = config.prompt_pack or defaults.get("prompt_pack")
        pack = prompt_packs.get(pack_name) if pack_name else None

        prompt_system = config.prompt_system or defaults.get("prompt_system", "")
        prompt_template = config.prompt_template or defaults.get("prompt_template", "")
        prompt_fields = config.prompt_fields or defaults.get("prompt_fields")
        criteria = config.criteria or defaults.get("criteria")
        prompt_defaults: Dict[str, Any] = {}
        for source in (
            defaults.get("prompt_defaults"),
            pack.get("prompt_defaults") if pack else None,
            config.prompt_defaults,
        ):
            if source:
                prompt_defaults.update(source)
        if not prompt_defaults:
            prompt_defaults = {}

        middleware_defs: list[Dict[str, Any]] = []
        for source in (
            defaults.get("llm_middleware_defs") or defaults.get("llm_middlewares"),
            pack.get("llm_middlewares") if pack else None,
            config.llm_middleware_defs,
        ):
            if source:
                middleware_defs.extend(source)
        middlewares: list[Any] | None = None

        raw_concurrency: Dict[str, Any] = {}
        for source in (
            defaults.get("concurrency_config") or defaults.get("concurrency"),
            pack.get("concurrency") if pack else None,
            config.concurrency_config,
        ):
            if source:
                raw_concurrency.update(source)
        concurrency_config = raw_concurrency or None

        early_stop_plugin_defs: List[Dict[str, Any]] = []
        for source in (
            defaults.get("early_stop_plugin_defs") or defaults.get("early_stop_plugins"),
            pack.get("early_stop_plugins") if pack else None,
            config.early_stop_plugin_defs,
        ):
            if source:
                early_stop_plugin_defs.extend(normalize_early_stop_definitions(source))

        raw_early_stop_config: Dict[str, Any] = {}
        for source in (
            defaults.get("early_stop_config") or defaults.get("early_stop"),
            pack.get("early_stop") if pack else None,
            config.early_stop_config,
        ):
            if source:
                raw_early_stop_config.update(source)
        early_stop_config = raw_early_stop_config or None
        if not early_stop_plugin_defs and early_stop_config:
            early_stop_plugin_defs.extend(normalize_early_stop_definitions(early_stop_config))

        row_defs = list(defaults.get("row_plugin_defs", []))
        if pack and pack.get("row_plugins"):
            row_defs = list(pack.get("row_plugins", [])) + row_defs
        if config.row_plugin_defs:
            row_defs += config.row_plugin_defs

        agg_defs = list(defaults.get("aggregator_plugin_defs", []))
        if pack and pack.get("aggregator_plugins"):
            agg_defs = list(pack.get("aggregator_plugins", [])) + agg_defs
        if config.aggregator_plugin_defs:
            agg_defs += config.aggregator_plugin_defs

        validation_defs = list(defaults.get("validation_plugin_defs", []))
        if pack and pack.get("validation_plugins"):
            validation_defs = list(pack.get("validation_plugins", [])) + validation_defs
        if config.validation_plugin_defs:
            validation_defs += config.validation_plugin_defs

        rate_limiter_def = defaults.get("rate_limiter_def")
        if pack and pack.get("rate_limiter"):
            rate_limiter_def = pack["rate_limiter"]
        if config.rate_limiter_def:
            rate_limiter_def = config.rate_limiter_def

        cost_tracker_def = defaults.get("cost_tracker_def")
        if pack and pack.get("cost_tracker"):
            cost_tracker_def = pack["cost_tracker"]
        if config.cost_tracker_def:
            cost_tracker_def = config.cost_tracker_def

        security_level = resolve_security_level(
            config.security_level,
            (pack.get("security_level") if pack else None),
            defaults.get("security_level"),
        )

        experiment_context = PluginContext(
            plugin_name=config.name,
            plugin_kind="experiment",
            security_level=security_level,
            provenance=(f"experiment:{config.name}.resolved",),
        )

        for idx, sink in enumerate(sinks):
            sink_name = getattr(sink, "_elspeth_sink_name", getattr(sink, "_elspeth_plugin_name", sink.__class__.__name__))
            sink_level = getattr(sink, "security_level", experiment_context.security_level)
            sink_context = experiment_context.derive(
                plugin_name=str(sink_name),
                plugin_kind="sink",
                security_level=sink_level,
                provenance=(f"sink:{sink_name}.resolved",),
            )
            apply_plugin_context(sink, sink_context)

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

        row_defs = list(defaults.get("row_plugin_defs", []))
        if pack and pack.get("row_plugins"):
            row_defs = list(pack.get("row_plugins", [])) + row_defs
        if config.row_plugin_defs:
            row_defs += config.row_plugin_defs

        agg_defs = list(defaults.get("aggregator_plugin_defs", []))
        if pack and pack.get("aggregator_plugins"):
            agg_defs = list(pack.get("aggregator_plugins", [])) + agg_defs
        if config.aggregator_plugin_defs:
            agg_defs += config.aggregator_plugin_defs

        validation_defs = list(defaults.get("validation_plugin_defs", []))
        if pack and pack.get("validation_plugins"):
            validation_defs = list(pack.get("validation_plugins", [])) + validation_defs
        if config.validation_plugin_defs:
            validation_defs += config.validation_plugin_defs

        rate_limiter_def = defaults.get("rate_limiter_def")
        if pack and pack.get("rate_limiter"):
            rate_limiter_def = pack["rate_limiter"]
        if config.rate_limiter_def:
            rate_limiter_def = config.rate_limiter_def

        cost_tracker_def = defaults.get("cost_tracker_def")
        if pack and pack.get("cost_tracker"):
            cost_tracker_def = pack["cost_tracker"]
        if config.cost_tracker_def:
            cost_tracker_def = config.cost_tracker_def

        if pack:
            pack_prompts = pack.get("prompts", {})
            prompt_system = prompt_system or pack_prompts.get("system", "")
            prompt_template = prompt_template or pack_prompts.get("user", "")
            if not prompt_fields:
                prompt_fields = pack.get("prompt_fields")
            if not criteria:
                criteria = pack.get("criteria")

        if not (prompt_system or "").strip():
            raise ConfigurationError(
                f"Experiment '{config.name}' has no system prompt defined. Provide one in the experiment, defaults, or prompt pack."
            )
        if not (prompt_template or "").strip():
            raise ConfigurationError(
                f"Experiment '{config.name}' has no user prompt defined. Provide one in the experiment, defaults, or prompt pack."
            )

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
            early_stop_plugins=early_stop_plugins,
            early_stop_config=early_stop_config,
        )
        setattr(runner_instance, "plugin_context", experiment_context)
        return runner_instance

    def _create_middlewares(
        self,
        definitions: list[Dict[str, Any]] | None,
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

    def _instantiate_sinks(self, defs: List[Dict[str, Any]]) -> List[ResultSink]:
        sinks: List[ResultSink] = []
        for index, entry in enumerate(defs):
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
            core_registry.registry.validate_sink(plugin, options_with_level)
            sink = core_registry.registry.create_sink(
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
        df,
        defaults: Dict[str, Any] | None = None,
        sink_factory: Callable[[ExperimentConfig], List[ResultSink]] | None = None,
        preflight_info: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        defaults = defaults or {}
        results: Dict[str, Any] = {}
        prompt_packs = defaults.get("prompt_packs", {})

        experiments: List[ExperimentConfig] = []
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
                ),
            )
            middlewares = cast(List[Any], runner.llm_middlewares or [])
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
