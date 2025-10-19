from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink

from .common import create_signed_bundle, ensure_artifacts_dir


def clone_suite_sinks(base_sinks: list, experiment_name: str) -> list:
    cloned = []
    for sink in base_sinks:
        security_level = getattr(sink, "_elspeth_security_level", None)
        determinism_level = getattr(sink, "_elspeth_determinism_level", getattr(sink, "determinism_level", None))
        if isinstance(sink, CsvResultSink):
            base_path = Path(sink.path)
            new_path = base_path.with_name(f"{experiment_name}_{base_path.name}")
            cloned.append(
                CsvResultSink(
                    path=str(new_path),
                    overwrite=sink.overwrite,
                    on_error=sink.on_error,
                    sanitize_formulas=sink.sanitize_formulas,
                    sanitize_guard=sink.sanitize_guard,
                )
            )
            if security_level:
                setattr(cloned[-1], "_elspeth_security_level", security_level)
            if determinism_level:
                setattr(cloned[-1], "_elspeth_determinism_level", determinism_level)
                setattr(cloned[-1], "determinism_level", determinism_level)
        else:
            cloned.append(sink)
            if determinism_level:
                setattr(cloned[-1], "_elspeth_determinism_level", determinism_level)
                setattr(cloned[-1], "determinism_level", determinism_level)
    return cloned


def assemble_suite_defaults(settings) -> dict:
    config = settings.orchestrator_config
    defaults: dict[str, Any] = {
        "prompt_system": config.llm_prompt.get("system", ""),
        "prompt_template": config.llm_prompt.get("user", ""),
        "prompt_fields": config.prompt_fields,
        "criteria": config.criteria,
        "prompt_packs": settings.prompt_packs,
    }
    optional_overrides = {
        "prompt_pack": config.prompt_pack,
        "row_plugin_defs": config.row_plugin_defs,
        "aggregator_plugin_defs": config.aggregator_plugin_defs,
        "baseline_plugin_defs": config.baseline_plugin_defs,
        "validation_plugin_defs": config.validation_plugin_defs,
        "sink_defs": config.sink_defs,
        "llm_middleware_defs": config.llm_middleware_defs,
        "prompt_defaults": config.prompt_defaults,
        "concurrency_config": config.concurrency_config,
        "early_stop_plugin_defs": config.early_stop_plugin_defs,
        "early_stop_config": config.early_stop_config,
    }
    for key, value in optional_overrides.items():
        if value:
            defaults[key] = value

    suite_defaults = settings.suite_defaults or {}
    passthrough_keys = {
        k: v
        for k, v in suite_defaults.items()
        if k
        not in {
            "row_plugins",
            "aggregator_plugins",
            "sinks",
            "baseline_plugins",
            "llm_middlewares",
            "early_stop_plugins",
            "early_stop_plugin_defs",
        }
    }
    defaults.update(passthrough_keys)

    plugin_mappings = {
        "row_plugin_defs": ["row_plugins"],
        "aggregator_plugin_defs": ["aggregator_plugins"],
        "baseline_plugin_defs": ["baseline_plugins"],
        "validation_plugin_defs": ["validation_plugins"],
        "llm_middleware_defs": ["llm_middlewares"],
        "sink_defs": ["sinks"],
        "prompt_pack": ["prompt_pack"],
        "rate_limiter_def": ["rate_limiter"],
        "cost_tracker_def": ["cost_tracker"],
    }
    for target, sources in plugin_mappings.items():
        for candidate in sources:
            if candidate in suite_defaults:
                defaults[target] = suite_defaults[candidate]
                break
    if settings.rate_limiter:
        defaults["rate_limiter"] = settings.rate_limiter
    if settings.cost_tracker:
        defaults["cost_tracker"] = settings.cost_tracker
    return defaults


def maybe_write_artifacts_suite(args: Any, settings: Any, suite: Any, results: dict[str, Any]) -> None:
    art_base = getattr(args, "artifacts_dir", None)
    if art_base is None and not getattr(args, "signed_bundle", False):
        return
    art_dir = ensure_artifacts_dir(art_base)
    # Write each experiment payload and the suite config
    (art_dir / "suite.json").write_text(
        json.dumps({k: v["payload"] for k, v in results.items()}, indent=2, sort_keys=True), encoding="utf-8"
    )
    try:
        cfg_path = Path(getattr(settings, "config_path", ""))
        if cfg_path and cfg_path.exists():
            (art_dir / "settings.yaml").write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    except (OSError, UnicodeError):
        pass
    if getattr(args, "signed_bundle", False):
        # For bundle, assemble a combined payload and pass the original DataFrame from datasource
        combined: dict[str, Any] = {"results": []}
        for _, entry in results.items():
            combined["results"].extend(entry["payload"].get("results", []))
        try:
            df = settings.datasource.load()
        except (OSError, RuntimeError, ValueError):
            df = pd.DataFrame()
        create_signed_bundle(
            art_dir,
            "suite",
            combined,
            settings,
            df,
            signing_key_env=getattr(args, "signing_key_env", "ELSPETH_SIGNING_KEY"),
        )


__all__ = ["clone_suite_sinks", "assemble_suite_defaults", "maybe_write_artifacts_suite"]

