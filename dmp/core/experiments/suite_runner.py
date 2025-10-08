"""Suite runner orchestrating multiple experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Callable

from dmp.core.experiments.config import ExperimentSuite, ExperimentConfig
from dmp.core.experiments.runner import ExperimentRunner
from dmp.core.experiments.plugin_registry import (
    create_row_plugin,
    create_aggregation_plugin,
    create_baseline_plugin,
    create_early_stop_plugin,
    normalize_early_stop_definitions,
)
from dmp.core.interfaces import LLMClientProtocol, ResultSink
from dmp.core.controls import create_rate_limiter, create_cost_tracker
from dmp.core.llm.registry import create_middleware
from dmp.core import registry as core_registry
from dmp.core.security import resolve_security_level
from dmp.core.validation import ConfigurationError


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
        middlewares = self._create_middlewares(middleware_defs)

        concurrency_config: Dict[str, Any] = {}
        for source in (
            defaults.get("concurrency_config") or defaults.get("concurrency"),
            pack.get("concurrency") if pack else None,
            config.concurrency_config,
        ):
            if source:
                concurrency_config.update(source)
        if not concurrency_config:
            concurrency_config = None

        early_stop_plugin_defs: List[Dict[str, Any]] = []
        for source in (
            defaults.get("early_stop_plugin_defs") or defaults.get("early_stop_plugins"),
            pack.get("early_stop_plugins") if pack else None,
            config.early_stop_plugin_defs,
        ):
            if source:
                early_stop_plugin_defs.extend(normalize_early_stop_definitions(source))

        early_stop_config: Dict[str, Any] = {}
        for source in (
            defaults.get("early_stop_config") or defaults.get("early_stop"),
            pack.get("early_stop") if pack else None,
            config.early_stop_config,
        ):
            if source:
                early_stop_config.update(source)
        if not early_stop_config:
            early_stop_config = None
        if not early_stop_plugin_defs and early_stop_config:
            early_stop_plugin_defs.extend(normalize_early_stop_definitions(early_stop_config))
        early_stop_plugins = (
            [create_early_stop_plugin(defn) for defn in early_stop_plugin_defs] if early_stop_plugin_defs else None
        )

        security_level = resolve_security_level(
            config.security_level,
            (pack.get("security_level") if pack else None),
            defaults.get("security_level"),
        )

        row_defs = list(defaults.get("row_plugin_defs", []))
        if pack and pack.get("row_plugins"):
            row_defs = list(pack.get("row_plugins", [])) + row_defs
        if config.row_plugin_defs:
            row_defs += config.row_plugin_defs
        row_plugins = [create_row_plugin(defn) for defn in row_defs] if row_defs else None

        agg_defs = list(defaults.get("aggregator_plugin_defs", []))
        if pack and pack.get("aggregator_plugins"):
            agg_defs = list(pack.get("aggregator_plugins", [])) + agg_defs
        if config.aggregator_plugin_defs:
            agg_defs += config.aggregator_plugin_defs
        aggregator_plugins = [create_aggregation_plugin(defn) for defn in agg_defs] if agg_defs else None

        rate_limiter = defaults.get("rate_limiter")
        if defaults.get("rate_limiter_def"):
            rate_limiter = create_rate_limiter(defaults["rate_limiter_def"])
        if pack and pack.get("rate_limiter"):
            rate_limiter = create_rate_limiter(pack["rate_limiter"])
        if config.rate_limiter_def:
            rate_limiter = create_rate_limiter(config.rate_limiter_def)

        cost_tracker = defaults.get("cost_tracker")
        if defaults.get("cost_tracker_def"):
            cost_tracker = create_cost_tracker(defaults["cost_tracker_def"])
        if pack and pack.get("cost_tracker"):
            cost_tracker = create_cost_tracker(pack["cost_tracker"])
        if config.cost_tracker_def:
            cost_tracker = create_cost_tracker(config.cost_tracker_def)

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

        runner_kwargs = {
            "llm_client": self.llm_client,
            "sinks": sinks,
            "prompt_system": prompt_system,
            "prompt_template": prompt_template,
            "prompt_fields": prompt_fields,
            "criteria": criteria,
            "prompt_defaults": prompt_defaults or None,
            "row_plugins": row_plugins,
            "aggregator_plugins": aggregator_plugins,
            "rate_limiter": rate_limiter,
            "cost_tracker": cost_tracker,
            "experiment_name": config.name,
            "llm_middlewares": middlewares or None,
            "concurrency_config": concurrency_config,
            "security_level": security_level,
            "early_stop_plugins": early_stop_plugins,
            "early_stop_config": early_stop_config,
        }
        return ExperimentRunner(**runner_kwargs)

    def _create_middlewares(self, definitions: list[Dict[str, Any]] | None) -> list[Any]:
        instances: list[Any] = []
        for defn in definitions or []:
            name = defn.get("name") or defn.get("plugin")
            identifier = f"{name}:{json.dumps(defn.get('options', {}), sort_keys=True)}"
            if identifier not in self._shared_middlewares:
                self._shared_middlewares[identifier] = create_middleware(defn)
            instances.append(self._shared_middlewares[identifier])
        return instances

    def _instantiate_sinks(self, defs: List[Dict[str, Any]]) -> List[ResultSink]:
        sinks: List[ResultSink] = []
        for index, entry in enumerate(defs):
            plugin = entry.get("plugin")
            raw_options = dict(entry.get("options", {}))
            core_registry.registry.validate_sink(plugin, raw_options)
            options = dict(raw_options)
            artifacts_cfg = options.pop("artifacts", None)
            security_level = options.pop("security_level", entry.get("security_level"))
            sink = core_registry.registry.create_sink(plugin, options)
            setattr(sink, "_dmp_artifact_config", artifacts_cfg or {})
            setattr(sink, "_dmp_plugin_name", plugin)
            base_name = entry.get("name") or plugin or f"sink{index}"
            setattr(sink, "_dmp_sink_name", base_name)
            if security_level:
                setattr(sink, "_dmp_security_level", security_level)
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
            middlewares = list(runner.llm_middlewares or [])
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
                    plugin = create_baseline_plugin(defn)
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
