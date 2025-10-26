"""Config loader for orchestrator settings."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

import elspeth.core.registries.llm as _llm_module
from elspeth.core.controls import create_cost_tracker, create_rate_limiter
from elspeth.core.experiments.plugin_registry import normalize_early_stop_definitions
from elspeth.core.orchestrator import OrchestratorConfig
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.sink import sink_registry
from elspeth.core.security import coalesce_determinism_level, coalesce_security_level
from elspeth.core.validation.base import ConfigurationError


@dataclass
class Settings:
    """Fully hydrated configuration for orchestrator execution."""

    datasource: Any
    llm: Any
    sinks: Any
    orchestrator_config: OrchestratorConfig
    suite_root: Path | None = None
    config_path: Path | None = None
    suite_defaults: dict[str, Any] = field(default_factory=dict)
    rate_limiter: Any | None = None
    cost_tracker: Any | None = None
    prompt_packs: dict[str, Any] = field(default_factory=dict)
    prompt_pack: str | None = None


@dataclass
class PromptConfiguration:
    """Encapsulates prompt-related configuration for orchestrator setup."""

    prompts: dict[str, Any]
    prompt_fields: Any
    prompt_aliases: Any
    criteria: Any


@dataclass
class PluginDefinitions:
    """Holds plugin definition sections prior to instantiation."""

    row_plugins: list[dict[str, Any]]
    aggregator_plugins: list[dict[str, Any]]
    baseline_plugins: list[dict[str, Any]]
    validation_plugins: list[dict[str, Any]]
    sink_defs: list[dict[str, Any]]
    llm_middlewares: list[dict[str, Any]]
    prompt_defaults: dict[str, Any] | None
    concurrency_config: dict[str, Any] | None
    rate_limiter_def: dict[str, Any] | None
    cost_tracker_def: dict[str, Any] | None
    early_stop_config: dict[str, Any] | None
    early_stop_plugin_defs: list[dict[str, Any]]


def _extract_optional_mapping(source: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    """Return a copy of the mapping stored under ``key`` or ``None``."""

    value = source.get(key)
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _collect_plugin_list(profile_data: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    """Materialize plugin definition lists while handling falsy values."""

    entries = profile_data.get(key) or []
    if isinstance(entries, list):
        return list(entries)
    return [entries]


def _resolve_early_stop_sections(profile_data: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Resolve early-stop configuration and plugin definitions."""

    early_stop_config = _extract_optional_mapping(profile_data, "early_stop")
    plugin_defs = normalize_early_stop_definitions(profile_data.get("early_stop_plugins")) or []
    if not plugin_defs and early_stop_config:
        plugin_defs = normalize_early_stop_definitions(early_stop_config) or []
    return early_stop_config, plugin_defs


def _prepare_plugin_definition(definition: Mapping[str, Any], context: str) -> tuple[dict[str, Any], str, str, tuple[str, ...]]:
    """Extract options, normalized security level, determinism level, and provenance.

    ADR-002-B: security_level is now optional in configuration (plugin-author-owned).
    If not provided, will be "UNCLASSIFIED" as default for legacy compatibility.
    """

    options = dict(definition.get("options", {}) or {})

    # Handle security_level (ADR-002-B: optional, plugin-author-owned)
    entry_sec_level = definition.get("security_level")
    options_sec_level = options.get("security_level")
    sources: list[str] = []
    if entry_sec_level is not None:
        sources.append(f"{context}.definition.security_level")
    if options_sec_level is not None:
        sources.append(f"{context}.options.security_level")

    # If no security_level provided, use UNOFFICIAL as default (legacy compatibility)
    if entry_sec_level is None and options_sec_level is None:
        sec_level = "UNOFFICIAL"
        sources.append(f"{context}.default")
    else:
        try:
            sec_level = coalesce_security_level(entry_sec_level, options_sec_level)
        except ValueError as exc:
            raise ConfigurationError(f"{context}: {exc}") from exc

    # Handle determinism_level
    entry_det_level = definition.get("determinism_level")
    options_det_level = options.get("determinism_level")
    if entry_det_level is not None:
        sources.append(f"{context}.definition.determinism_level")
    if options_det_level is not None:
        sources.append(f"{context}.options.determinism_level")
    try:
        det_level = coalesce_determinism_level(entry_det_level, options_det_level)
    except ValueError as exc:
        raise ConfigurationError(f"{context}: {exc}") from exc

    # ADR-002-B: Do NOT pass security_level to plugin payload (plugin-author-owned)
    # Only pass determinism_level (user-configurable)
    options["determinism_level"] = det_level
    provenance = tuple(sources or (f"{context}.resolved",))
    return options, sec_level, det_level, provenance


def _merge_pack(base: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    """Merge prompt pack defaults into an existing dict without mutating inputs."""

    merged = dict(pack)
    merged.update(base)
    return merged


def _read_profile_data(config_path: Path, profile: str) -> dict[str, Any]:
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
    factory: Callable[..., Any],
) -> Any:
    """Instantiate a plugin and apply the resolved security and determinism levels.

    ADR-002-B: security_level is NOT passed in payload (plugin-author-owned).
    Only determinism_level is passed (user-configurable).
    """

    if not isinstance(definition, Mapping):
        raise ConfigurationError(f"{context} configuration must be a mapping.")
    plugin_name = definition.get("plugin")
    if not plugin_name:
        raise ConfigurationError(f"{context} configuration must define a plugin name.")
    options, sec_level, det_level, provenance = _prepare_plugin_definition(definition, context)
    payload = dict(options)
    # ADR-002-B: Do NOT pass security_level (plugin-author-owned)
    # determinism_level already added to options in _prepare_plugin_definition
    # Be flexible with factory signature to support tests that monkeypatch
    # registry.create without provenance/parent_context kwargs. Use signature
    # introspection to decide which optional kwargs to pass, avoiding nested
    # try/except that could hide genuine signature issues.
    try:
        sig = inspect.signature(factory)
    except (ValueError, TypeError):  # builtins/c-callables may not have a signature
        sig = None

    kwargs: dict[str, Any] = {}
    if sig is not None:
        param_kinds = {name: p.kind for name, p in sig.parameters.items()}
        allows_kwargs = any(kind is inspect.Parameter.VAR_KEYWORD for kind in param_kinds.values())
        if "provenance" in param_kinds or allows_kwargs:
            kwargs["provenance"] = provenance
        if "parent_context" in param_kinds or allows_kwargs:
            kwargs["parent_context"] = None
        # ADR-001/002-B: Security is ALWAYS required (no backdoors), determinism still required
        if "require_determinism" in param_kinds or allows_kwargs:
            kwargs["require_determinism"] = True  # determinism still required
    else:
        # Best-effort default: pass only required positional args
        kwargs = {}

    return factory(plugin_name, payload, **kwargs)


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

    early_stop_config, early_stop_plugin_defs = _resolve_early_stop_sections(profile_data)
    rate_limiter_def = _extract_optional_mapping(profile_data, "rate_limiter")
    cost_tracker_def = _extract_optional_mapping(profile_data, "cost_tracker")
    concurrency_config = _extract_optional_mapping(profile_data, "concurrency")
    prompt_defaults = _extract_optional_mapping(profile_data, "prompt_defaults")

    return PluginDefinitions(
        row_plugins=_collect_plugin_list(profile_data, "row_plugins"),
        aggregator_plugins=_collect_plugin_list(profile_data, "aggregator_plugins"),
        baseline_plugins=_collect_plugin_list(profile_data, "baseline_plugins"),
        validation_plugins=_collect_plugin_list(profile_data, "validation_plugins"),
        sink_defs=_collect_plugin_list(profile_data, "sinks"),
        llm_middlewares=_collect_plugin_list(profile_data, "llm_middlewares"),
        prompt_defaults=prompt_defaults,
        concurrency_config=concurrency_config,
        rate_limiter_def=rate_limiter_def,
        cost_tracker_def=cost_tracker_def,
        early_stop_config=early_stop_config,
        early_stop_plugin_defs=early_stop_plugin_defs,
    )


def _apply_prompt_config_overrides(pack: Mapping[str, Any], prompt_config: PromptConfiguration) -> None:
    """Apply prompt pack overrides to prompt configuration."""
    if pack_prompts := pack.get("prompts"):
        prompt_config.prompts = _merge_pack(prompt_config.prompts, pack_prompts)
    if not prompt_config.prompt_fields:
        prompt_config.prompt_fields = pack.get("prompt_fields")
    if not prompt_config.criteria:
        prompt_config.criteria = pack.get("criteria")


def _apply_plugin_list_overrides(pack: Mapping[str, Any], plugin_defs: PluginDefinitions) -> None:
    """Apply prompt pack overrides to plugin lists (prepend pack plugins)."""
    plugin_defs.row_plugins = list(pack.get("row_plugins", []) or []) + plugin_defs.row_plugins
    plugin_defs.aggregator_plugins = list(pack.get("aggregator_plugins", []) or []) + plugin_defs.aggregator_plugins
    plugin_defs.baseline_plugins = list(pack.get("baseline_plugins", []) or []) + plugin_defs.baseline_plugins
    plugin_defs.validation_plugins = list(pack.get("validation_plugins", []) or []) + plugin_defs.validation_plugins
    plugin_defs.llm_middlewares = list(pack.get("llm_middlewares", []) or []) + plugin_defs.llm_middlewares


def _apply_singleton_config_overrides(pack: Mapping[str, Any], plugin_defs: PluginDefinitions) -> None:
    """Apply prompt pack overrides to singleton configurations (only if not already set)."""
    if not plugin_defs.sink_defs:
        plugin_defs.sink_defs = list(pack.get("sinks", []) or [])

    # Helper to safely copy mapping if exists and target is not set
    def _set_if_mapping(target_attr: str, pack_key: str) -> None:
        if not getattr(plugin_defs, target_attr) and pack.get(pack_key):
            value = pack.get(pack_key)
            if isinstance(value, Mapping):
                setattr(plugin_defs, target_attr, dict(value))

    _set_if_mapping("rate_limiter_def", "rate_limiter")
    _set_if_mapping("cost_tracker_def", "cost_tracker")
    _set_if_mapping("prompt_defaults", "prompt_defaults")
    _set_if_mapping("concurrency_config", "concurrency")


def _apply_early_stop_overrides(pack: Mapping[str, Any], plugin_defs: PluginDefinitions) -> None:
    """Apply prompt pack early stop plugin overrides."""
    pack_early_stop_defs = normalize_early_stop_definitions(pack.get("early_stop_plugins")) or []
    if not pack_early_stop_defs:
        pack_early_stop_defs = normalize_early_stop_definitions(pack.get("early_stop")) or []
    if pack_early_stop_defs:
        plugin_defs.early_stop_plugin_defs = pack_early_stop_defs + plugin_defs.early_stop_plugin_defs


def _apply_prompt_pack_overrides(
    pack: Mapping[str, Any] | None,
    prompt_config: PromptConfiguration,
    plugin_defs: PluginDefinitions,
) -> None:
    """Apply prompt pack overrides to the prompt configuration and plugin definitions.

    This function delegates to smaller helper functions to reduce complexity:
    - _apply_prompt_config_overrides: Handles prompt-specific config
    - _apply_plugin_list_overrides: Handles plugin lists
    - _apply_singleton_config_overrides: Handles singleton configs
    - _apply_early_stop_overrides: Handles early stop plugins
    """
    if not pack or not isinstance(pack, Mapping):
        return

    _apply_prompt_config_overrides(pack, prompt_config)
    _apply_plugin_list_overrides(pack, plugin_defs)
    _apply_singleton_config_overrides(pack, plugin_defs)
    _apply_early_stop_overrides(pack, plugin_defs)


def _resolve_suite_defaults_pack(
    prompt_packs: Mapping[str, Any],
    pack_name: Any,
) -> Mapping[str, Any] | None:
    """Return the prompt pack mapping referenced by ``pack_name`` if available."""

    if not isinstance(prompt_packs, Mapping) or not pack_name:
        return None
    pack = prompt_packs.get(pack_name)
    return pack if isinstance(pack, Mapping) else None


def _merge_suite_default_scalars(suite_defaults: dict[str, Any], pack: Mapping[str, Any]) -> None:
    """Merge scalar prompt values when absent from suite defaults."""

    for key in ("prompts", "prompt_fields", "criteria"):
        suite_defaults.setdefault(key, pack.get(key))


def _merge_suite_default_lists(suite_defaults: dict[str, Any], pack: Mapping[str, Any]) -> None:
    """Merge list-based plugin defaults when absent from suite defaults."""

    list_keys = (
        "row_plugins",
        "aggregator_plugins",
        "baseline_plugins",
        "validation_plugins",
        "llm_middlewares",
        "sinks",
    )
    for key in list_keys:
        if key not in suite_defaults:
            suite_defaults[key] = _collect_plugin_list(pack, key)


def _merge_suite_default_mappings(suite_defaults: dict[str, Any], pack: Mapping[str, Any]) -> None:
    """Merge mapping-based overrides when absent from suite defaults."""

    for key in ("rate_limiter", "cost_tracker", "concurrency", "early_stop"):
        if key in suite_defaults:
            continue
        value = pack.get(key)
        if isinstance(value, Mapping):
            suite_defaults[key] = dict(value)


def _merge_suite_default_early_stop_plugins(suite_defaults: dict[str, Any], pack: Mapping[str, Any]) -> None:
    """Merge early-stop plugins override when absent from suite defaults."""

    if "early_stop_plugins" not in suite_defaults:
        plugins_override = pack.get("early_stop_plugins")
        if plugins_override:
            suite_defaults["early_stop_plugins"] = plugins_override


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
) -> list[dict[str, Any]]:
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


def _instantiate_sinks(sink_defs: list[dict[str, Any]]) -> list[Any]:
    """Instantiate sink plugins with security level metadata."""

    instances: list[Any] = []
    for definition in sink_defs:
        instances.append(_instantiate_plugin(definition, "sink", sink_registry.create))
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
        max_rows=profile_data.get("max_rows"),
    )


def _prepare_suite_defaults(
    suite_defaults_cfg: Any,
    prompt_packs: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge suite defaults with any referenced prompt pack overrides."""

    suite_defaults = dict(suite_defaults_cfg or {})
    pack = _resolve_suite_defaults_pack(prompt_packs, suite_defaults.get("prompt_pack"))
    if not pack:
        return suite_defaults

    _merge_suite_default_scalars(suite_defaults, pack)
    _merge_suite_default_lists(suite_defaults, pack)
    _merge_suite_default_mappings(suite_defaults, pack)
    _merge_suite_default_early_stop_plugins(suite_defaults, pack)
    return suite_defaults


def load_settings(path: str | Path, profile: str = "default") -> Settings:
    """Load orchestrator settings from YAML and materialize runtime objects."""

    config_path = Path(path)
    profile_data = _read_profile_data(config_path, profile)
    prompt_packs = profile_data.pop("prompt_packs", {})
    prompt_pack_name = profile_data.get("prompt_pack")
    pack = prompt_packs.get(prompt_pack_name) if prompt_pack_name else None

    datasource = _instantiate_plugin(profile_data["datasource"], "datasource", datasource_registry.create)
    # Resolve LLM registry dynamically to support test monkeypatching of llm_registry
    llm = _instantiate_plugin(profile_data["llm"], "llm", _llm_module.llm_registry.create)

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
        config_path=config_path,
        suite_defaults=suite_defaults,
        rate_limiter=rate_limiter,
        cost_tracker=cost_tracker,
        prompt_packs=prompt_packs,
        prompt_pack=prompt_pack_name,
    )
