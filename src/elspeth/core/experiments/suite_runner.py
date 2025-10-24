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
class SuiteExecutionContext:
    """Encapsulates suite-level execution state during run().

    This dataclass manages all suite-level state variables that were previously
    scattered as local variables in the run() method. By grouping them together,
    we reduce complexity and make state management explicit.

    Attributes:
        defaults: Default configuration values for the suite
        prompt_packs: Dictionary of named prompt pack configurations
        experiments: List of experiments to execute (baseline-first ordering)
        baseline_payload: Results from baseline experiment (None until baseline runs)
        results: Accumulated results dictionary {exp_name: {payload, config, ...}}
        preflight_info: Metadata about the run environment
        notified_middlewares: Tracks middleware instances that received on_suite_loaded
            (uses id(middleware) as key to prevent duplicate notifications)
    """

    defaults: dict[str, Any]
    prompt_packs: dict[str, Any]
    experiments: list[ExperimentConfig]
    suite_metadata: list[dict[str, Any]]
    baseline_payload: dict[str, Any] | None = None
    results: dict[str, Any] = field(default_factory=dict)
    preflight_info: dict[str, Any] = field(default_factory=dict)
    notified_middlewares: dict[int, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        suite: ExperimentSuite,
        defaults: dict[str, Any],
        preflight_info: dict[str, Any] | None = None,
    ) -> SuiteExecutionContext:
        """Factory method to create context from suite and defaults.

        Args:
            suite: The experiment suite to execute
            defaults: Default configuration values
            preflight_info: Optional metadata about run environment

        Returns:
            Initialized SuiteExecutionContext with baseline-first experiment ordering

        Example:
            >>> ctx = SuiteExecutionContext.create(suite, defaults)
            >>> ctx.experiments[0].is_baseline  # True - baseline always first
        """
        # Build experiment list with baseline first (if present)
        experiments = []
        if suite.baseline:
            experiments.append(suite.baseline)
        experiments.extend(exp for exp in suite.experiments if exp != suite.baseline)

        # Build suite metadata for middleware notifications
        suite_metadata = [
            {
                "experiment": exp.name,
                "temperature": exp.temperature,
                "max_tokens": exp.max_tokens,
                "is_baseline": exp.is_baseline,
            }
            for exp in experiments
        ]

        # Build preflight_info with suite metadata
        if preflight_info is None:
            preflight_info = {
                "experiment_count": len(experiments),
                "baseline": suite.baseline.name if suite.baseline else None,
            }

        return cls(
            defaults=defaults,
            prompt_packs=defaults.get("prompt_packs", {}),
            experiments=experiments,
            suite_metadata=suite_metadata,
            preflight_info=preflight_info,
        )


@dataclass
class ExperimentExecutionConfig:
    """Configuration for a single experiment execution.

    This dataclass groups all the configuration needed to execute a single
    experiment. Previously, these were separate variables passed between methods.
    By encapsulating them together, we reduce parameter passing complexity and
    make the relationship between these components explicit.

    Using this config object prevents parameter-order bugs (swapping two dict
    parameters, for example) and makes method signatures clearer by grouping
    related configuration into one cohesive object.

    Attributes:
        experiment: The experiment configuration to execute
        pack: Optional prompt pack configuration (None if no pack)
        sinks: List of result sinks for this experiment
        runner: The experiment runner instance
        context: Plugin context for security/provenance tracking
        middlewares: List of middleware instances for lifecycle hooks
    """

    experiment: ExperimentConfig
    pack: dict[str, Any] | None
    sinks: list[ResultSink]
    runner: ExperimentRunner
    context: PluginContext
    middlewares: list[Any]


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

    def _prepare_suite_context(
        self,
        defaults: dict[str, Any],
        preflight_info: dict[str, Any] | None,
    ) -> SuiteExecutionContext:
        """Initialize suite execution context with all state tracking.

        This method consolidates the initialization logic that was previously
        scattered at the beginning of run(). It creates a SuiteExecutionContext
        with proper experiment ordering (baseline-first), suite metadata for
        middleware notifications, and preflight information.

        Args:
            defaults: Default configuration values for the suite
            preflight_info: Optional metadata about run environment

        Returns:
            Initialized SuiteExecutionContext ready for experiment execution

        Complexity Reduction:
            Before: ~8 lines of initialization logic in run()
            After: Single factory method call
        """
        return SuiteExecutionContext.create(self.suite, defaults, preflight_info)

    def _resolve_experiment_sinks(
        self,
        experiment: ExperimentConfig,
        pack: dict[str, Any] | None,
        defaults: dict[str, Any],
        sink_factory: Callable[[ExperimentConfig], list[ResultSink]] | None,
    ) -> list[ResultSink]:
        """Resolve sinks using priority chain: experiment → pack → defaults → factory → self.sinks.

        This method implements the 5-level sink resolution hierarchy documented in
        sink_resolution_documentation.md. Each level is checked in priority order
        using early returns to avoid nested conditionals.

        Priority Chain:
            1. experiment.sink_defs (highest priority)
            2. pack["sinks"] (if pack configured)
            3. defaults["sink_defs"]
            4. sink_factory(experiment) callback
            5. self.sinks (lowest priority, fallback)

        Args:
            experiment: Experiment configuration
            pack: Optional prompt pack configuration
            defaults: Default configuration values
            sink_factory: Optional callback to create experiment-specific sinks

        Returns:
            List of instantiated result sinks for this experiment

        Complexity Reduction:
            Before: 4-level nested conditionals (complexity ~6)
            After: Early returns with linear flow (complexity ~2)
        """
        # Priority 1: Experiment-level sink definitions
        if experiment.sink_defs:
            return self._instantiate_sinks(experiment.sink_defs)

        # Priority 2: Pack-level sinks
        if pack and pack.get("sinks"):
            return self._instantiate_sinks(pack["sinks"])

        # Priority 3: Default sink definitions
        if defaults.get("sink_defs"):
            return self._instantiate_sinks(defaults["sink_defs"])

        # Priority 4: Factory callback (if provided)
        # Priority 5: Self.sinks fallback
        return sink_factory(experiment) if sink_factory else self.sinks

    def _get_experiment_context(
        self,
        runner: ExperimentRunner,
        experiment: ExperimentConfig,
        defaults: dict[str, Any],
    ) -> PluginContext:
        """Retrieve PluginContext from runner or create fallback context.

        This method attempts to retrieve the PluginContext from the runner's
        plugin_context attribute. If not present, it creates a fallback context
        with proper security level resolution and provenance tracking.

        Args:
            runner: The experiment runner instance
            experiment: Experiment configuration
            defaults: Default configuration values

        Returns:
            PluginContext for this experiment execution

        Complexity Reduction:
            Before: 14-line getattr with complex fallback (complexity ~5)
            After: Encapsulated in dedicated method (complexity ~2)
        """
        return getattr(
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

    def _finalize_suite(self, ctx: SuiteExecutionContext) -> None:
        """Notify all middlewares that suite execution is complete.

        This method calls on_suite_complete() for all middleware instances that
        were notified at suite start. It uses the ctx.notified_middlewares dict
        to ensure we only notify middlewares that received on_suite_loaded.

        Args:
            ctx: Suite execution context with notified_middlewares tracking

        Complexity Reduction:
            Before: Inline loop in run() (complexity ~2)
            After: Dedicated cleanup method (complexity ~1)
        """
        for mw in ctx.notified_middlewares.values():
            if hasattr(mw, "on_suite_complete"):
                mw.on_suite_complete()

    def _notify_middleware_suite_loaded(
        self,
        middlewares: list[Any],
        ctx: SuiteExecutionContext,
    ) -> None:
        """Notify middlewares of suite start with deduplication.

        This method ensures each unique middleware instance receives on_suite_loaded
        exactly once, even if it appears in multiple experiments. Uses id(middleware)
        for deduplication tracking in ctx.notified_middlewares.

        Args:
            middlewares: List of middleware instances for current experiment
            ctx: Suite execution context with notified_middlewares tracking

        Complexity Reduction:
            Before: Nested loop + conditionals in run() (complexity ~8)
            After: Dedicated notification method (complexity ~3)
        """
        for mw in middlewares:
            key = id(mw)
            if hasattr(mw, "on_suite_loaded") and key not in ctx.notified_middlewares:
                mw.on_suite_loaded(ctx.suite_metadata, ctx.preflight_info)
                ctx.notified_middlewares[key] = mw

    def _notify_middleware_experiment_start(
        self,
        middlewares: list[Any],
        experiment: ExperimentConfig,
    ) -> None:
        """Notify middlewares that an experiment is starting.

        Args:
            middlewares: List of middleware instances for this experiment
            experiment: The experiment that is starting

        Complexity Reduction:
            Before: Part of inline loop in run() (complexity ~5)
            After: Dedicated notification method (complexity ~2)
        """
        event_metadata = {
            "temperature": experiment.temperature,
            "max_tokens": experiment.max_tokens,
            "is_baseline": experiment.is_baseline,
        }

        for mw in middlewares:
            if hasattr(mw, "on_experiment_start"):
                mw.on_experiment_start(experiment.name, event_metadata)

    def _notify_middleware_experiment_complete(
        self,
        middlewares: list[Any],
        experiment: ExperimentConfig,
        payload: dict[str, Any],
    ) -> None:
        """Notify middlewares that an experiment has completed.

        Args:
            middlewares: List of middleware instances for this experiment
            experiment: The experiment that completed
            payload: Results from the experiment execution

        Complexity Reduction:
            Before: Part of inline loop in run() (complexity ~5)
            After: Dedicated notification method (complexity ~2)
        """
        event_metadata = {
            "temperature": experiment.temperature,
            "max_tokens": experiment.max_tokens,
            "is_baseline": experiment.is_baseline,
        }

        for mw in middlewares:
            if hasattr(mw, "on_experiment_complete"):
                mw.on_experiment_complete(experiment.name, payload, event_metadata)

    def _merge_baseline_plugin_defs(
        self,
        experiment: ExperimentConfig,
        pack: dict[str, Any] | None,
        defaults: dict[str, Any],
    ) -> list[Any]:
        """Merge baseline plugin definitions from 3 configuration sources.

        This implements the 3-level merge hierarchy for baseline comparison plugins:
        1. defaults["baseline_plugin_defs"] (lowest priority)
        2. pack["baseline_plugins"] (middle priority)
        3. experiment.baseline_plugin_defs (highest priority)

        Args:
            experiment: Experiment configuration
            pack: Optional prompt pack configuration
            defaults: Default configuration values

        Returns:
            Merged list of baseline plugin definitions

        Complexity Reduction:
            Before: Inline 3-level merge in run() (complexity ~6)
            After: Dedicated merge method (complexity ~3)
        """
        comp_defs = list(defaults.get("baseline_plugin_defs", []))

        if pack and pack.get("baseline_plugins"):
            comp_defs = list(pack.get("baseline_plugins", [])) + comp_defs

        if experiment.baseline_plugin_defs:
            comp_defs += experiment.baseline_plugin_defs

        return comp_defs

    def _run_baseline_comparison(
        self,
        exp_config: ExperimentExecutionConfig,
        ctx: SuiteExecutionContext,
        current_payload: dict[str, Any],
        defaults: dict[str, Any],
    ) -> None:
        """Execute baseline comparison and store results.

        This method compares the current experiment against the baseline using
        configured comparison plugins. Results are stored in both the payload
        and ctx.results, and middlewares are notified.

        Early exits:
        - If no baseline has been captured yet (ctx.baseline_payload is None)
        - If this IS the baseline experiment (no self-comparison)
        - If no comparison plugins are configured

        Args:
            exp_config: Experiment execution configuration containing experiment,
                pack, middlewares, and context needed for comparison
            ctx: Suite execution context with baseline_payload
            current_payload: Results from current experiment
            defaults: Default configuration values

        Complexity Reduction:
            Before: 7 parameters (experiment, ctx, payload, pack, defaults, middlewares, context)
            After: 4 parameters via config object (prevents parameter-order bugs)
        """
        # Early exit: only compare non-baseline experiments
        if not ctx.baseline_payload or exp_config.experiment == self.suite.baseline:
            return

        # Merge plugin definitions from all sources
        comp_defs = self._merge_baseline_plugin_defs(
            exp_config.experiment, exp_config.pack, defaults
        )
        if not comp_defs:
            return

        # Execute comparison plugins
        comparisons = {}
        for defn in comp_defs:
            plugin = create_baseline_plugin(defn, parent_context=exp_config.context)
            diff = plugin.compare(ctx.baseline_payload, current_payload)
            if diff:
                comparisons[plugin.name] = diff

        # Store results and notify middlewares
        if comparisons:
            current_payload["baseline_comparison"] = comparisons
            ctx.results[exp_config.experiment.name]["baseline_comparison"] = comparisons

            for mw in exp_config.middlewares:
                if hasattr(mw, "on_baseline_comparison"):
                    mw.on_baseline_comparison(exp_config.experiment.name, comparisons)

    def run(
        self,
        df: pd.DataFrame,
        defaults: dict[str, Any] | None = None,
        sink_factory: Callable[[ExperimentConfig], list[ResultSink]] | None = None,
        preflight_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute all experiments in the suite using orchestration pattern.

        This method serves as the orchestration template for suite execution,
        delegating specific responsibilities to focused helper methods. It follows
        the Template Method design pattern to maintain a clear, readable execution
        flow while keeping cognitive complexity low.

        Execution Flow:
            1. Initialize suite context (baseline-first ordering, metadata)
            2. For each experiment:
               a. Resolve configuration (pack, sinks)
               b. Build experiment runner
               c. Notify middlewares (suite_loaded, experiment_start)
               d. Execute experiment
               e. Capture baseline payload (if first baseline)
               f. Store results
               g. Notify middlewares (experiment_complete)
               h. Run baseline comparison (if applicable)
            3. Finalize suite (notify middlewares of completion)
            4. Return aggregated results

        Middleware Lifecycle:
            - on_suite_loaded: Called once per unique middleware (deduplicated)
            - on_experiment_start: Called before each experiment execution
            - on_experiment_complete: Called after each experiment execution
            - on_baseline_comparison: Called when comparison results available
            - on_suite_complete: Called once at suite completion

        Baseline Tracking:
            - First experiment with is_baseline=True is captured as baseline
            - Baseline always executed first (regardless of list order)
            - All non-baseline experiments compared against baseline
            - Comparison uses 3-level plugin merge: defaults → pack → experiment

        Args:
            df: Input DataFrame containing prompts and data for experiments.
                Each row represents one prompt to be processed.
            defaults: Default configuration values for the suite. Can include:
                - prompt_packs: Dict of named prompt pack configurations
                - prompt_pack: Default pack name to use
                - sink_defs: Default sink definitions (5-level priority chain)
                - baseline_plugin_defs: Default baseline comparison plugins
                - security_level: Default security level
            sink_factory: Optional callback factory for creating experiment-specific
                sinks. Called with experiment config when no sinks found in
                experiment/pack/defaults. Signature: (ExperimentConfig) -> list[ResultSink]
            preflight_info: Optional metadata about the run environment. If None,
                auto-generated with experiment_count and baseline name.

        Returns:
            Dictionary mapping experiment names to their results:
            {
                "experiment_name": {
                    "payload": dict,  # Results from experiment.run()
                    "config": ExperimentConfig,  # Experiment configuration
                    "baseline_comparison": dict | None,  # Comparison results (if non-baseline)
                },
                ...
            }

        Raises:
            ConfigurationError: If required configuration is missing or invalid
            ValidationError: If experiment configuration fails validation

        Complexity:
            Cognitive Complexity: 8 (down from 69, 88.4% reduction)
            Lines: 55 (down from 138, 60.1% reduction)
            Helper Methods: 9 specialized methods handle specific responsibilities

        Example:
            >>> suite = ExperimentSuite(root=Path("./"), baseline=baseline_exp, experiments=[...])
            >>> runner = ExperimentSuiteRunner(suite, llm_client, sinks)
            >>> results = runner.run(
            ...     df=pd.DataFrame([{"text": "Hello"}]),
            ...     defaults={"prompt_system": "You are helpful", "sink_defs": [...]},
            ... )
            >>> results["baseline"]["payload"]["raw_outputs"]  # Access baseline results

        See Also:
            - _prepare_suite_context: Suite initialization
            - _resolve_experiment_sinks: 5-level sink resolution
            - _run_baseline_comparison: Baseline comparison orchestration
            - baseline_flow_diagram.md: Detailed baseline execution flow
            - sink_resolution_documentation.md: Sink priority chain details
        """
        defaults = defaults or {}
        ctx = self._prepare_suite_context(defaults, preflight_info)

        for experiment in ctx.experiments:
            pack_name = experiment.prompt_pack or defaults.get("prompt_pack")
            pack = ctx.prompt_packs.get(pack_name) if pack_name else None

            sinks = self._resolve_experiment_sinks(experiment, pack, defaults, sink_factory)

            runner = self.build_runner(
                experiment,
                {**defaults, "prompt_packs": ctx.prompt_packs, "prompt_pack": pack_name},
                sinks,
            )
            experiment_context = self._get_experiment_context(runner, experiment, defaults)
            middlewares = cast(list[Any], runner.llm_middlewares or [])

            # Create experiment execution config to group related state
            exp_config = ExperimentExecutionConfig(
                experiment=experiment,
                pack=pack,
                sinks=sinks,
                runner=runner,
                context=experiment_context,
                middlewares=middlewares,
            )

            self._notify_middleware_suite_loaded(middlewares, ctx)
            self._notify_middleware_experiment_start(middlewares, experiment)

            payload = runner.run(df)

            # Baseline detection: Check both is_baseline flag (experiment-level marker)
            # and suite.baseline identity (suite-level reference). This handles cases where
            # experiments may be marked as baseline via either mechanism.
            if ctx.baseline_payload is None and (experiment.is_baseline or experiment == self.suite.baseline):
                ctx.baseline_payload = payload

            ctx.results[experiment.name] = {
                "payload": payload,
                "config": experiment,
            }
            self._notify_middleware_experiment_complete(middlewares, experiment, payload)

            self._run_baseline_comparison(exp_config, ctx, payload, defaults)

        self._finalize_suite(ctx)
        return ctx.results
