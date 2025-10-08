"""Config loader for orchestrator settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from dmp.core.orchestrator import OrchestratorConfig
from dmp.core.registry import registry
from dmp.core.controls import create_rate_limiter, create_cost_tracker
from dmp.core.experiments.plugin_registry import normalize_early_stop_definitions


@dataclass
class Settings:
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


def _merge_pack(base: Dict[str, Any], pack: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(pack)
    merged.update(base)
    return merged


def load_settings(path: str | Path, profile: str = "default") -> Settings:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_data = dict(data.get(profile, {}))

    prompt_packs = profile_data.pop("prompt_packs", {})
    prompt_pack_name = profile_data.get("prompt_pack")
    pack = prompt_packs.get(prompt_pack_name) if prompt_pack_name else None

    datasource_cfg = profile_data["datasource"]
    datasource = registry.create_datasource(
        datasource_cfg["plugin"], datasource_cfg.get("options", {})
    )

    llm_cfg = profile_data["llm"]
    llm = registry.create_llm(llm_cfg["plugin"], llm_cfg.get("options", {}))

    row_plugin_defs: List[Dict[str, Any]] = profile_data.get("row_plugins", [])
    aggregator_plugin_defs: List[Dict[str, Any]] = profile_data.get("aggregator_plugins", [])
    baseline_plugin_defs: List[Dict[str, Any]] = profile_data.get("baseline_plugins", [])
    sink_defs: List[Dict[str, Any]] = profile_data.get("sinks", [])
    rate_limiter_def = profile_data.get("rate_limiter")
    cost_tracker_def = profile_data.get("cost_tracker")
    llm_middleware_defs: List[Dict[str, Any]] = profile_data.get("llm_middlewares", [])
    prompt_defaults = profile_data.get("prompt_defaults")
    concurrency_config = profile_data.get("concurrency")
    early_stop_config = profile_data.get("early_stop")
    early_stop_plugin_defs = normalize_early_stop_definitions(profile_data.get("early_stop_plugins")) or []
    if not early_stop_plugin_defs and early_stop_config:
        early_stop_plugin_defs = normalize_early_stop_definitions(early_stop_config)

    prompts = profile_data.get("prompts", {})
    prompt_fields = profile_data.get("prompt_fields")
    prompt_aliases = profile_data.get("prompt_aliases")
    criteria = profile_data.get("criteria")

    if pack:
        if pack_prompts := pack.get("prompts"):
            prompts = _merge_pack(prompts, pack_prompts)
        if not prompt_fields:
            prompt_fields = pack.get("prompt_fields")
        if not criteria:
            criteria = pack.get("criteria")
        row_plugin_defs = list(pack.get("row_plugins", [])) + row_plugin_defs
        aggregator_plugin_defs = list(pack.get("aggregator_plugins", [])) + aggregator_plugin_defs
        baseline_plugin_defs = list(pack.get("baseline_plugins", [])) + baseline_plugin_defs
        llm_middleware_defs = list(pack.get("llm_middlewares", [])) + llm_middleware_defs
        if not sink_defs:
            sink_defs = pack.get("sinks", [])
        if not rate_limiter_def and pack.get("rate_limiter"):
            rate_limiter_def = pack.get("rate_limiter")
        if not cost_tracker_def and pack.get("cost_tracker"):
            cost_tracker_def = pack.get("cost_tracker")
        if not prompt_defaults and pack.get("prompt_defaults"):
            prompt_defaults = pack.get("prompt_defaults")
        if not concurrency_config and pack.get("concurrency"):
            concurrency_config = pack.get("concurrency")
        pack_early_stop_defs = normalize_early_stop_definitions(pack.get("early_stop_plugins")) or []
        if not pack_early_stop_defs and pack.get("early_stop"):
            pack_early_stop_defs = normalize_early_stop_definitions(pack.get("early_stop"))
        if pack_early_stop_defs:
            early_stop_plugin_defs = pack_early_stop_defs + early_stop_plugin_defs

    sinks = [registry.create_sink(item["plugin"], item.get("options", {})) for item in sink_defs]

    rate_limiter = create_rate_limiter(rate_limiter_def)
    cost_tracker = create_cost_tracker(cost_tracker_def)

    orchestrator_config = OrchestratorConfig(
        llm_prompt=prompts,
        prompt_fields=prompt_fields,
        prompt_aliases=prompt_aliases,
        criteria=criteria,
        row_plugin_defs=row_plugin_defs,
        aggregator_plugin_defs=aggregator_plugin_defs,
        baseline_plugin_defs=baseline_plugin_defs,
        sink_defs=sink_defs,
        prompt_pack=prompt_pack_name,
        retry_config=profile_data.get("retry"),
        checkpoint_config=profile_data.get("checkpoint"),
        llm_middleware_defs=llm_middleware_defs,
        prompt_defaults=prompt_defaults,
        concurrency_config=concurrency_config,
        early_stop_config=early_stop_config,
        early_stop_plugin_defs=early_stop_plugin_defs or None,
    )

    suite_root = profile_data.get("suite_root")
    suite_defaults = dict(profile_data.get("suite_defaults", {}))
    if suite_defaults.get("prompt_pack"):
        pack = prompt_packs.get(suite_defaults["prompt_pack"])
        if pack:
            suite_defaults.setdefault("prompts", pack.get("prompts"))
            suite_defaults.setdefault("prompt_fields", pack.get("prompt_fields"))
            suite_defaults.setdefault("criteria", pack.get("criteria"))
            suite_defaults.setdefault("row_plugins", pack.get("row_plugins", []))
            suite_defaults.setdefault("aggregator_plugins", pack.get("aggregator_plugins", []))
            suite_defaults.setdefault("baseline_plugins", pack.get("baseline_plugins", []))
            suite_defaults.setdefault("llm_middlewares", pack.get("llm_middlewares", []))
            suite_defaults.setdefault("sinks", pack.get("sinks", []))
            if pack.get("rate_limiter"):
                suite_defaults.setdefault("rate_limiter", pack.get("rate_limiter"))
            if pack.get("cost_tracker"):
                suite_defaults.setdefault("cost_tracker", pack.get("cost_tracker"))
            if pack.get("concurrency"):
                suite_defaults.setdefault("concurrency", pack.get("concurrency"))
            if pack.get("early_stop"):
                suite_defaults.setdefault("early_stop", pack.get("early_stop"))
            if pack.get("early_stop_plugins"):
                suite_defaults.setdefault("early_stop_plugins", pack.get("early_stop_plugins"))

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
