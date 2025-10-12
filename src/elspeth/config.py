"""Config loader for orchestrator settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

import yaml

from elspeth.core.controls import create_cost_tracker, create_rate_limiter
from elspeth.core.experiments.plugin_registry import normalize_early_stop_definitions
from elspeth.core.orchestrator import OrchestratorConfig
from elspeth.core.registry import registry
from elspeth.core.security import coalesce_security_level, normalize_security_level
from elspeth.core.validation import ConfigurationError


@dataclass
class Settings:
    """Fully hydrated configuration for orchestrator execution."""

    datasource: Any
    llm: Any
    sinks: Any
    orchestrator_config: OrchestratorConfig
    suite_root: Path | None = None
    suite_defaults: Dict[str, Any] = field(default_factory=dict)
    rate_limiter: Any | None = None
    cost_tracker: Any | None = None
    prompt_packs: Dict[str, Any] = field(default_factory=dict)
    prompt_pack: Optional[str] = None


@dataclass
class PromptConfiguration:
    """Encapsulates prompt-related configuration for orchestrator setup."""

    prompts: Dict[str, Any]
    prompt_fields: Any
    prompt_aliases: Any
    criteria: Any


@dataclass
class PluginDefinitions:
    """Holds plugin definition sections prior to instantiation."""

    row_plugins: List[Dict[str, Any]]
    aggregator_plugins: List[Dict[str, Any]]
    baseline_plugins: List[Dict[str, Any]]
    validation_plugins: List[Dict[str, Any]]
    sink_defs: List[Dict[str, Any]]
    llm_middlewares: List[Dict[str, Any]]
    prompt_defaults: Dict[str, Any] | None
    concurrency_config: Dict[str, Any] | None
    rate_limiter_def: Dict[str, Any] | None
    cost_tracker_def: Dict[str, Any] | None
    early_stop_config: Dict[str, Any] | None
    early_stop_plugin_defs: List[Dict[str, Any]]


def _prepare_plugin_definition(
    definition: Mapping[str, Any], context: str
) -> tuple[Dict[str, Any], str, tuple[str, ...]]:
    """Extract options, normalized security level, and provenance."""

    options = dict(definition.get("options", {}) or {})
    entry_level = definition.get("security_level")
    options_level = options.get("security_level")
    sources: list[str] = []
    if entry_level is not None:
        sources.append(f"{context}.definition.security_level")
    if options_level is not None:
        sources.append(f"{context}.options.security_level")
    try:
        level = coalesce_security_level(entry_level, options_level)
    except ValueError as exc:
        raise ConfigurationError(f"{context}: {exc}") from exc
    # Keep the resolved level inside the options we hand to plugin factories so that
    # plugin constructors (e.g. CSV/Excel sinks) can normalise it themselves. Removing
    # it causes them to fall back to their default ("unofficial") security posture.
    options["security_level"] = level
    provenance = tuple(sources or (f"{context}.resolved",))
    return options, level, provenance


def _merge_pack(base: Dict[str, Any], pack: Dict[str, Any]) -> Dict[str, Any]:
    """Merge prompt pack defaults into an existing dict without mutating inputs."""

    merged = dict(pack)
    merged.update(base)
    return merged


def _read_profile_data(config_path: Path, profile: str) -> Dict[str, Any]:
    """Load YAML configuration and return the selected profile section."""

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise ConfigurationError("Settings file must contain a mapping at the root level.")
    profile_section = raw.get(profile, {})
    if not isinstance(profile_section, Mapping):
        raise ConfigurationError(f"Profile '{profile}' must be a mapping in configuration.")
    return dict(profile_section)


def _instantiate_plugin(
    definition: Mapping[str, Any],
    context: str,
    factory: Callable[[str, Dict[str, Any]], Any],
) -> Any:
    """Instantiate a plugin and apply the resolved security level attribute."""

    if not isinstance(definition, Mapping):
        raise ConfigurationError(f"{context} configuration must be a mapping.")
    plugin_name = definition.get("plugin")
    if not plugin_name:
        raise ConfigurationError(f"{context} configuration must define a plugin name.")
    options, level, provenance = _prepare_plugin_definition(definition, context)
    payload = dict(options)
    payload["security_level"] = level
    return factory(plugin_name, payload, provenance=provenance)


def _collect_prompt_configuration(profile_data: Mapping[str, Any]) -> PromptConfiguration:
    """Extract prompt, fields, aliases, and criteria configuration."""

    return PromptConfiguration(
        prompts=dict(profile_data.get("prompts", {})),
        prompt_fields=profile_data.get("prompt_fields"),
        prompt_aliases=profile_data.get("prompt_aliases"),
        criteria=profile_data.get("criteria"),
    )


def _collect_plugin_definitions(profile_data: Mapping[str, Any]) -> PluginDefinitions:
    """Capture plugin definition lists and runtime configuration sections."""

    early_stop_config = profile_data.get("early_stop")
    if isinstance(early_stop_config, Mapping):
        early_stop_config = dict(early_stop_config)
    else:
        early_stop_config = None
    early_stop_plugin_defs = normalize_early_stop_definitions(profile_data.get("early_stop_plugins")) or []
    if not early_stop_plugin_defs and early_stop_config:
        early_stop_plugin_defs = normalize_early_stop_definitions(early_stop_config) or []
    rate_limiter_def = profile_data.get("rate_limiter")
    if isinstance(rate_limiter_def, Mapping):
        rate_limiter_def = dict(rate_limiter_def)
    else:
        rate_limiter_def = None
    cost_tracker_def = profile_data.get("cost_tracker")
    if isinstance(cost_tracker_def, Mapping):
        cost_tracker_def = dict(cost_tracker_def)
    else:
        cost_tracker_def = None
    concurrency_config = profile_data.get("concurrency")
    if isinstance(concurrency_config, Mapping):
        concurrency_config = dict(concurrency_config)
    prompt_defaults = profile_data.get("prompt_defaults")
    if isinstance(prompt_defaults, Mapping):
        prompt_defaults = dict(prompt_defaults)

    return PluginDefinitions(
        row_plugins=list(profile_data.get("row_plugins", []) or []),
        aggregator_plugins=list(profile_data.get("aggregator_plugins", []) or []),
        baseline_plugins=list(profile_data.get("baseline_plugins", []) or []),
        validation_plugins=list(profile_data.get("validation_plugins", []) or []),
        sink_defs=list(profile_data.get("sinks", []) or []),
        llm_middlewares=list(profile_data.get("llm_middlewares", []) or []),
        prompt_defaults=prompt_defaults,
        concurrency_config=concurrency_config,
        rate_limiter_def=rate_limiter_def,
        cost_tracker_def=cost_tracker_def,
        early_stop_config=early_stop_config,
        early_stop_plugin_defs=early_stop_plugin_defs,
    )


def _apply_prompt_pack_overrides(
    pack: Mapping[str, Any] | None,
    prompt_config: PromptConfiguration,
    plugin_defs: PluginDefinitions,
) -> None:
    """Apply prompt pack overrides to the prompt configuration and plugin definitions."""

    if not pack or not isinstance(pack, Mapping):
        return

    if pack_prompts := pack.get("prompts"):
        prompt_config.prompts = _merge_pack(prompt_config.prompts, pack_prompts)
    if not prompt_config.prompt_fields:
        prompt_config.prompt_fields = pack.get("prompt_fields")
    if not prompt_config.criteria:
        prompt_config.criteria = pack.get("criteria")

    plugin_defs.row_plugins = list(pack.get("row_plugins", []) or []) + plugin_defs.row_plugins
    plugin_defs.aggregator_plugins = list(pack.get("aggregator_plugins", []) or []) + plugin_defs.aggregator_plugins
    plugin_defs.baseline_plugins = list(pack.get("baseline_plugins", []) or []) + plugin_defs.baseline_plugins
    plugin_defs.validation_plugins = list(pack.get("validation_plugins", []) or []) + plugin_defs.validation_plugins
    plugin_defs.llm_middlewares = list(pack.get("llm_middlewares", []) or []) + plugin_defs.llm_middlewares

    if not plugin_defs.sink_defs:
        plugin_defs.sink_defs = list(pack.get("sinks", []) or [])
    if not plugin_defs.rate_limiter_def and pack.get("rate_limiter"):
        rate_limiter_override = pack.get("rate_limiter")
        if isinstance(rate_limiter_override, Mapping):
            plugin_defs.rate_limiter_def = dict(rate_limiter_override)
    if not plugin_defs.cost_tracker_def and pack.get("cost_tracker"):
        cost_tracker_override = pack.get("cost_tracker")
        if isinstance(cost_tracker_override, Mapping):
            plugin_defs.cost_tracker_def = dict(cost_tracker_override)
    if not plugin_defs.prompt_defaults and pack.get("prompt_defaults"):
        pack_prompt_defaults = pack.get("prompt_defaults")
        if isinstance(pack_prompt_defaults, Mapping):
            plugin_defs.prompt_defaults = dict(pack_prompt_defaults)
    if not plugin_defs.concurrency_config and pack.get("concurrency"):
        concurrency_override = pack.get("concurrency")
        if isinstance(concurrency_override, Mapping):
            plugin_defs.concurrency_config = dict(concurrency_override)

    pack_early_stop_defs = normalize_early_stop_definitions(pack.get("early_stop_plugins")) or []
    if not pack_early_stop_defs and pack.get("early_stop"):
        pack_early_stop_defs = normalize_early_stop_definitions(pack.get("early_stop")) or []
    if pack_early_stop_defs:
        plugin_defs.early_stop_plugin_defs = pack_early_stop_defs + plugin_defs.early_stop_plugin_defs


def _resolve_sink_definitions(
    plugin_defs: PluginDefinitions,
    profile_data: Mapping[str, Any],
    prompt_packs: Mapping[str, Any],
) -> None:
    """Populate sink definitions when missing, using suite defaults fallbacks."""

    if plugin_defs.sink_defs:
        return
    suite_defaults_cfg = profile_data.get("suite_defaults")
    fallback = _sinks_from_suite_defaults(suite_defaults_cfg, prompt_packs)
    if fallback:
        plugin_defs.sink_defs = fallback


def _sinks_from_suite_defaults(
    suite_defaults_cfg: Any,
    prompt_packs: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Derive sink definitions from suite defaults or referenced prompt packs."""

    if not isinstance(suite_defaults_cfg, Mapping):
        return []
    defaults_sinks = suite_defaults_cfg.get("sinks")
    if isinstance(defaults_sinks, list) and defaults_sinks:
        return defaults_sinks
    defaults_pack_name = suite_defaults_cfg.get("prompt_pack")
    if defaults_pack_name:
        pack_cfg = prompt_packs.get(defaults_pack_name)
        if isinstance(pack_cfg, Mapping):
            pack_sinks = pack_cfg.get("sinks")
            if isinstance(pack_sinks, list) and pack_sinks:
                return pack_sinks
    return []


def _instantiate_sinks(sink_defs: List[Dict[str, Any]]) -> List[Any]:
    """Instantiate sink plugins with security level metadata."""

    instances: List[Any] = []
    for definition in sink_defs:
        instances.append(_instantiate_plugin(definition, "sink", registry.create_sink))
    return instances


def _build_orchestrator_config(
    prompt_config: PromptConfiguration,
    plugin_defs: PluginDefinitions,
    prompt_pack_name: str | None,
    profile_data: Mapping[str, Any],
) -> OrchestratorConfig:
    """Construct the orchestrator configuration object."""

    return OrchestratorConfig(
        llm_prompt=prompt_config.prompts,
        prompt_fields=prompt_config.prompt_fields,
        prompt_aliases=prompt_config.prompt_aliases,
        criteria=prompt_config.criteria,
        row_plugin_defs=plugin_defs.row_plugins,
        aggregator_plugin_defs=plugin_defs.aggregator_plugins,
        baseline_plugin_defs=plugin_defs.baseline_plugins,
        validation_plugin_defs=plugin_defs.validation_plugins,
        sink_defs=plugin_defs.sink_defs,
        prompt_pack=prompt_pack_name,
        retry_config=profile_data.get("retry"),
        checkpoint_config=profile_data.get("checkpoint"),
        llm_middleware_defs=plugin_defs.llm_middlewares,
        prompt_defaults=plugin_defs.prompt_defaults,
        concurrency_config=plugin_defs.concurrency_config,
        early_stop_config=plugin_defs.early_stop_config,
        early_stop_plugin_defs=plugin_defs.early_stop_plugin_defs or None,
    )


def _prepare_suite_defaults(
    suite_defaults_cfg: Any,
    prompt_packs: Mapping[str, Any],
) -> Dict[str, Any]:
    """Merge suite defaults with any referenced prompt pack overrides."""

    suite_defaults = dict(suite_defaults_cfg or {})
    pack_name = suite_defaults.get("prompt_pack")
    if not pack_name:
        return suite_defaults
    pack = prompt_packs.get(pack_name)
    if not isinstance(pack, Mapping):
        return suite_defaults

    suite_defaults.setdefault("prompts", pack.get("prompts"))
    suite_defaults.setdefault("prompt_fields", pack.get("prompt_fields"))
    suite_defaults.setdefault("criteria", pack.get("criteria"))
    suite_defaults.setdefault("row_plugins", pack.get("row_plugins", []) or [])
    suite_defaults.setdefault("aggregator_plugins", pack.get("aggregator_plugins", []) or [])
    suite_defaults.setdefault("baseline_plugins", pack.get("baseline_plugins", []) or [])
    suite_defaults.setdefault("validation_plugins", pack.get("validation_plugins", []) or [])
    suite_defaults.setdefault("llm_middlewares", pack.get("llm_middlewares", []) or [])
    suite_defaults.setdefault("sinks", pack.get("sinks", []) or [])
    if pack.get("rate_limiter"):
        rate_limiter_override = pack.get("rate_limiter")
        if isinstance(rate_limiter_override, Mapping):
            suite_defaults.setdefault("rate_limiter", dict(rate_limiter_override))
    if pack.get("cost_tracker"):
        cost_tracker_override = pack.get("cost_tracker")
        if isinstance(cost_tracker_override, Mapping):
            suite_defaults.setdefault("cost_tracker", dict(cost_tracker_override))
    if pack.get("concurrency"):
        concurrency_override = pack.get("concurrency")
        if isinstance(concurrency_override, Mapping):
            suite_defaults.setdefault("concurrency", dict(concurrency_override))
    if pack.get("early_stop"):
        early_stop_override = pack.get("early_stop")
        if isinstance(early_stop_override, Mapping):
            suite_defaults.setdefault("early_stop", dict(early_stop_override))
    if pack.get("early_stop_plugins"):
        suite_defaults.setdefault("early_stop_plugins", pack.get("early_stop_plugins"))
    return suite_defaults


def load_settings(path: str | Path, profile: str = "default") -> Settings:
    """Load orchestrator settings from YAML and materialize runtime objects."""

    config_path = Path(path)
    profile_data = _read_profile_data(config_path, profile)
    prompt_packs = profile_data.pop("prompt_packs", {})
    prompt_pack_name = profile_data.get("prompt_pack")
    pack = prompt_packs.get(prompt_pack_name) if prompt_pack_name else None

    datasource = _instantiate_plugin(profile_data["datasource"], "datasource", registry.create_datasource)
    llm = _instantiate_plugin(profile_data["llm"], "llm", registry.create_llm)

    prompt_config = _collect_prompt_configuration(profile_data)
    plugin_defs = _collect_plugin_definitions(profile_data)
    _apply_prompt_pack_overrides(pack, prompt_config, plugin_defs)
    _resolve_sink_definitions(plugin_defs, profile_data, prompt_packs)

    sinks = _instantiate_sinks(plugin_defs.sink_defs)
    rate_limiter = create_rate_limiter(plugin_defs.rate_limiter_def)
    cost_tracker = create_cost_tracker(plugin_defs.cost_tracker_def)

    orchestrator_config = _build_orchestrator_config(
        prompt_config,
        plugin_defs,
        prompt_pack_name,
        profile_data,
    )

    suite_root = profile_data.get("suite_root")
    suite_defaults = _prepare_suite_defaults(profile_data.get("suite_defaults"), prompt_packs)

    return Settings(
        datasource=datasource,
        llm=llm,
        sinks=sinks,
        orchestrator_config=orchestrator_config,
        suite_root=Path(suite_root) if suite_root else None,
        suite_defaults=suite_defaults,
        rate_limiter=rate_limiter,
        cost_tracker=cost_tracker,
        prompt_packs=prompt_packs,
        prompt_pack=prompt_pack_name,
    )
