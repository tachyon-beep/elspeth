from __future__ import annotations

from typing import Any


def strip_metrics_plugins(settings: Any) -> None:
    """Remove selected metrics plugins in settings and prompt packs when disabled.

    Mirrors the legacy CLI behavior to keep runtime semantics identical while
    relocating the logic for maintainability.
    """
    row_names = {"score_extractor"}
    agg_names = {"score_stats", "score_recommendation"}
    baseline_names = {"score_delta"}

    def _filter(defs, names):
        if not defs:
            return defs
        return [entry for entry in defs if entry.get("name") not in names]

    cfg = settings.orchestrator_config
    cfg.row_plugin_defs = _filter(cfg.row_plugin_defs, row_names)
    cfg.aggregator_plugin_defs = _filter(cfg.aggregator_plugin_defs, agg_names)
    cfg.baseline_plugin_defs = _filter(cfg.baseline_plugin_defs, baseline_names)

    defaults = settings.suite_defaults or {}
    if "row_plugins" in defaults:
        defaults["row_plugins"] = _filter(defaults.get("row_plugins"), row_names)
    if "aggregator_plugins" in defaults:
        defaults["aggregator_plugins"] = _filter(defaults.get("aggregator_plugins"), agg_names)
    if "baseline_plugins" in defaults:
        defaults["baseline_plugins"] = _filter(defaults.get("baseline_plugins"), baseline_names)

    for pack in settings.prompt_packs.values():
        if isinstance(pack, dict):
            if "row_plugins" in pack:
                pack["row_plugins"] = _filter(pack.get("row_plugins"), row_names)
            if "aggregator_plugins" in pack:
                pack["aggregator_plugins"] = _filter(pack.get("aggregator_plugins"), agg_names)
            if "baseline_plugins" in pack:
                pack["baseline_plugins"] = _filter(pack.get("baseline_plugins"), baseline_names)


def configure_sink_dry_run(settings: Any, *, enable_live: bool) -> None:
    """Toggle dry-run behaviour for sinks supporting remote writes."""
    dry_run = not enable_live

    for sink in settings.sinks:
        if hasattr(sink, "dry_run"):
            setattr(sink, "dry_run", dry_run)

    def _update_defs(defs):
        if not defs:
            return defs
        updated = []
        for entry in defs:
            options = dict(entry.get("options", {}))
            if entry.get("plugin") in {"github_repo", "azure_devops_repo"} or "dry_run" in options:
                options["dry_run"] = dry_run
            payload = {"plugin": entry.get("plugin"), "options": options}
            if entry.get("security_level") is not None:
                payload["security_level"] = entry.get("security_level")
            if entry.get("determinism_level") is not None:
                payload["determinism_level"] = entry.get("determinism_level")
            updated.append(payload)
        return updated

    config = settings.orchestrator_config
    config.sink_defs = _update_defs(config.sink_defs)

    suite_defaults = settings.suite_defaults or {}
    if "sinks" in suite_defaults:
        suite_defaults["sinks"] = _update_defs(suite_defaults.get("sinks"))

    for pack in settings.prompt_packs.values():
        if isinstance(pack, dict) and pack.get("sinks"):
            pack["sinks"] = _update_defs(pack.get("sinks"))


__all__ = ["strip_metrics_plugins", "configure_sink_dry_run"]
