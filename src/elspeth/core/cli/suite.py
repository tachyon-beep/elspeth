"""Helpers for orchestration suite management used by the CLI."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from elspeth.core.experiments import ExperimentSuite, ExperimentSuiteRunner
from elspeth.core.security.secure_mode import SecureMode, get_secure_mode
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink

from .common import create_signed_bundle, ensure_artifacts_dir, maybe_publish_artifacts_bundle


def clone_suite_sinks(base_sinks: list, experiment_name: str) -> list:
    """Clone sink definitions for a specific experiment namespace."""
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
    """Build suite-level defaults dict from settings and orchestrator config."""
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
    """Optionally persist per-experiment payloads and the suite config as artifacts."""
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
        bundle_dir = create_signed_bundle(
            art_dir,
            "suite",
            combined,
            settings,
            df,
            signing_key_env=getattr(args, "signing_key_env", "ELSPETH_SIGNING_KEY"),
        )
        if bundle_dir:
            maybe_publish_artifacts_bundle(
                bundle_dir,
                plugin_name=getattr(args, "artifact_sink_plugin", None),
                config_path=getattr(args, "artifact_sink_config", None),
            )


__all__ = [
    "clone_suite_sinks",
    "assemble_suite_defaults",
    "maybe_write_artifacts_suite",
    "handle_suite_management",
    "run_suite",
]


def handle_suite_management(args: Any, suite_root: Path | None) -> ExperimentSuite | None:
    """Process template/export/report requests before running experiments."""
    from elspeth.core.experiments.tools import (  # pylint: disable=import-outside-toplevel  # noqa: I001
        create_experiment_template,
        export_suite_configuration,
    )

    logger = logging.getLogger(__name__)
    export_path = getattr(args, "export_suite_config", None)
    template_name = getattr(args, "create_experiment_template", None)
    reports_dir = getattr(args, "reports_dir", None)
    template_base = getattr(args, "template_base", None)
    management_requested = any([export_path, template_name, reports_dir])
    if not management_requested:
        return None
    if suite_root is None:
        raise SystemExit("Suite root is required for template creation, export, or report generation.")

    suite_instance = ExperimentSuite.load(suite_root)
    if template_name:
        destination = create_experiment_template(
            suite_instance,
            template_name,
            base_experiment=template_base,
        )
        logger.info("Created experiment template at %s", destination)
        suite_instance = ExperimentSuite.load(suite_root)
    if export_path:
        export_suite_configuration(suite_instance, export_path)
        logger.info("Exported suite configuration to %s", export_path)
    return suite_instance


def run_suite(
    args: Any,
    settings: Any,
    suite_root: Path,
    *,
    preflight: Mapping[str, Any] | None = None,
    suite: ExperimentSuite | None = None,
) -> None:
    """Execute all experiments declared in a suite configuration."""
    logger = logging.getLogger(__name__)
    logger.info("Running suite at %s", suite_root)
    suite = suite or ExperimentSuite.load(suite_root)
    df = settings.datasource.load()
    suite_runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=settings.llm,
        sinks=settings.sinks,
        suite_root=settings.suite_root,
        config_path=settings.config_path,
    )
    defaults = assemble_suite_defaults(settings)
    results = suite_runner.run(
        df,
        defaults=defaults,
        sink_factory=lambda exp: clone_suite_sinks(settings.sinks, exp.name),
        preflight_info=dict(preflight) if isinstance(preflight, Mapping) else preflight,
    )
    for name, entry in results.items():
        logger.info("Experiment %s completed with %s rows", name, len(entry["payload"].get("results", [])))
    reports_dir = getattr(args, "reports_dir", None)
    if reports_dir:
        if getattr(args, "single_run", False):
            logger.warning("Report generation skipped: reports require suite execution.")
        else:
            try:  # import late to allow test monkeypatching cli.SuiteReportGenerator
                from elspeth.cli import SuiteReportGenerator as _SRG  # pylint: disable=import-outside-toplevel
            except Exception:  # pragma: no cover - fallback
                from elspeth.tools.reporting import SuiteReportGenerator as _SRG  # pylint: disable=import-outside-toplevel
            _SRG(suite, results).generate_all_reports(reports_dir)
    maybe_write_artifacts_suite(args, settings, suite, results)
    try:
        if get_secure_mode() == SecureMode.STRICT:
            any_failures = any(entry["payload"]["failures"] for entry in results.values())
            if any_failures:
                logger.error("STRICT mode: sink failures detected in suite; aborting with non-zero exit")
                raise SystemExit(1)
    except Exception:
        logger.debug("Secure mode utilities unavailable after suite; continuing without exit enforcement", exc_info=True)
