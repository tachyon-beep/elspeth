"""Command-line entry point for local experimentation.

For now the CLI focuses on hydrating experiment input data from Azure Blob
Storage using the configuration profiles defined in ``config/blob_store.yaml``.
Future work will layer in the experiment runner once additional modules land.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Iterable, Any, Dict, Mapping

import pandas as pd

from dmp.config import load_settings
from dmp.core.orchestrator import ExperimentOrchestrator
from dmp.core.experiments import ExperimentSuiteRunner, ExperimentSuite
from dmp.plugins.outputs.csv_file import CsvResultSink
from dmp.core.controls import create_rate_limiter, create_cost_tracker
from dmp.core.validation import validate_settings, validate_suite

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DMP data bootstrap CLI")
    parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        help="Path to orchestrator settings YAML",
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="Settings profile to load",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=5,
        help="Number of rows to display as a quick preview (0 to skip)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        help="Optional local path to persist the downloaded dataset",
    )
    parser.add_argument(
        "--suite-root",
        type=Path,
        help="Override suite root directory (if unset, uses settings)",
    )
    parser.add_argument(
        "--single-run",
        action="store_true",
        help="Force single experiment run even if suite settings exist",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Set logging verbosity",
    )
    parser.add_argument(
        "--disable-metrics",
        action="store_true",
        help="Disable metrics/statistical plugins from the loaded settings",
    )
    parser.add_argument(
        "--live-outputs",
        action="store_true",
        help="Allow sinks to perform live writes (disables repo dry-run modes)",
    )
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


def format_preview(df: pd.DataFrame, head: int) -> str:
    """Convert the dataframe preview into a printable string."""

    preview = df.head(head) if head > 0 else df.head(0)
    with pd.option_context("display.max_columns", None):
        return preview.to_string(index=False)


def _flatten_value(target: Dict[str, Any], prefix: str, value: Any) -> None:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            next_prefix = f"{prefix}_{key}" if prefix else key
            _flatten_value(target, next_prefix, inner)
    else:
        target[prefix] = value


def _result_to_row(record: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(record.get("row") or {})

    def consume_response(prefix: str, response: Mapping[str, Any] | None) -> None:
        if not response:
            return
        content = response.get("content")
        if content is not None:
            row[prefix] = content
        metrics = response.get("metrics")
        if isinstance(metrics, Mapping):
            for key, value in metrics.items():
                _flatten_value(row, f"{prefix}_metric_{key}", value)

    consume_response("llm_content", record.get("response"))
    for name, response in (record.get("responses") or {}).items():
        consume_response(f"llm_{name}", response)

    for key, value in (record.get("metrics") or {}).items():
        _flatten_value(row, f"metric_{key}", value)

    retry_info = record.get("retry")
    if retry_info:
        row["retry_attempts"] = retry_info.get("attempts")
        row["retry_max_attempts"] = retry_info.get("max_attempts")
        history = retry_info.get("history")
        if history:
            row["retry_history"] = json.dumps(history)

    if "security_level" in record:
        row["security_level"] = record["security_level"]

    return row


def run(args: argparse.Namespace) -> None:
    configure_logging(args.log_level)
    settings_report = validate_settings(args.settings, profile=args.profile)
    for warning in settings_report.warnings:
        logger.warning(warning.format())
    settings_report.raise_if_errors()
    settings = load_settings(args.settings, profile=args.profile)
    if args.disable_metrics:
        _strip_metrics_plugins(settings)
    _configure_sink_dry_run(settings, enable_live=args.live_outputs)
    suite_root = args.suite_root or settings.suite_root

    if suite_root and not args.single_run:
        suite_validation = validate_suite(suite_root)
        for warning in suite_validation.report.warnings:
            logger.warning(warning.format())
        suite_validation.report.raise_if_errors()
        _run_suite(args, settings, suite_root, preflight=suite_validation.preflight)
    else:
        _run_single(args, settings)


def _run_single(args: argparse.Namespace, settings) -> None:
    logger.info("Running single experiment")
    orchestrator = ExperimentOrchestrator(
        datasource=settings.datasource,
        llm_client=settings.llm,
        sinks=settings.sinks,
        config=settings.orchestrator_config,
        rate_limiter=settings.rate_limiter,
        cost_tracker=settings.cost_tracker,
    )
    payload = orchestrator.run()

    for failure in payload.get("failures", []):
        retry = failure.get("retry") or {}
        attempts = retry.get("attempts")
        logger.error(
            "Row processing failed after %s attempts: %s",
            attempts if attempts is not None else 1,
            failure.get("error"),
        )

    rows = [_result_to_row(result) for result in payload["results"]]
    df = pd.DataFrame(rows)

    if args.output_csv:
        output_path: Path = args.output_csv
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("Saved dataset to %s", output_path)

    if args.head and args.head > 0 and not df.empty:
        print(format_preview(df, args.head))


def _clone_suite_sinks(base_sinks: list, experiment_name: str) -> list:
    cloned = []
    for sink in base_sinks:
        if isinstance(sink, CsvResultSink):
            base_path = Path(sink.path)
            new_path = base_path.with_name(f"{experiment_name}_{base_path.name}")
            cloned.append(CsvResultSink(path=new_path, overwrite=True))
        else:
            cloned.append(sink)
    return cloned


def _run_suite(args: argparse.Namespace, settings, suite_root: Path, *, preflight: dict | None = None) -> None:
    logger.info("Running suite at %s", suite_root)
    suite = ExperimentSuite.load(suite_root)
    df = settings.datasource.load()
    suite_runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=settings.llm,
        sinks=settings.sinks,
    )

    defaults = {
        "prompt_system": settings.orchestrator_config.llm_prompt.get("system", ""),
        "prompt_template": settings.orchestrator_config.llm_prompt.get("user", ""),
        "prompt_fields": settings.orchestrator_config.prompt_fields,
        "criteria": settings.orchestrator_config.criteria,
    }
    defaults["prompt_packs"] = settings.prompt_packs
    if settings.orchestrator_config.prompt_pack:
        defaults["prompt_pack"] = settings.orchestrator_config.prompt_pack
    if settings.orchestrator_config.row_plugin_defs:
        defaults["row_plugin_defs"] = settings.orchestrator_config.row_plugin_defs
    if settings.orchestrator_config.aggregator_plugin_defs:
        defaults["aggregator_plugin_defs"] = settings.orchestrator_config.aggregator_plugin_defs
    if settings.orchestrator_config.baseline_plugin_defs:
        defaults["baseline_plugin_defs"] = settings.orchestrator_config.baseline_plugin_defs
    if settings.orchestrator_config.sink_defs:
        defaults["sink_defs"] = settings.orchestrator_config.sink_defs
    if settings.orchestrator_config.llm_middleware_defs:
        defaults["llm_middleware_defs"] = settings.orchestrator_config.llm_middleware_defs
    if settings.orchestrator_config.prompt_defaults:
        defaults["prompt_defaults"] = settings.orchestrator_config.prompt_defaults
    if settings.orchestrator_config.concurrency_config:
        defaults["concurrency_config"] = settings.orchestrator_config.concurrency_config
    if settings.orchestrator_config.early_stop_plugin_defs:
        defaults["early_stop_plugin_defs"] = settings.orchestrator_config.early_stop_plugin_defs
    if settings.orchestrator_config.early_stop_config:
        defaults["early_stop_config"] = settings.orchestrator_config.early_stop_config

    suite_defaults = settings.suite_defaults or {}
    defaults.update(
        {
            k: v
            for k, v in suite_defaults.items()
            if k
            not in {"row_plugins", "aggregator_plugins", "sinks", "baseline_plugins", "llm_middlewares", "early_stop_plugins", "early_stop_plugin_defs"}
        }
    )
    if "row_plugins" in suite_defaults:
        defaults["row_plugin_defs"] = suite_defaults["row_plugins"]
    if "aggregator_plugins" in suite_defaults:
        defaults["aggregator_plugin_defs"] = suite_defaults["aggregator_plugins"]
    if "baseline_plugins" in suite_defaults:
        defaults["baseline_plugin_defs"] = suite_defaults["baseline_plugins"]
    if "llm_middlewares" in suite_defaults:
        defaults["llm_middleware_defs"] = suite_defaults["llm_middlewares"]
    if "prompt_defaults" in suite_defaults:
        defaults["prompt_defaults"] = suite_defaults["prompt_defaults"]
    if "concurrency" in suite_defaults:
        defaults["concurrency_config"] = suite_defaults["concurrency"]
    if "early_stop_plugin_defs" in suite_defaults:
        defaults["early_stop_plugin_defs"] = suite_defaults["early_stop_plugin_defs"]
    if "early_stop_plugins" in suite_defaults:
        defaults["early_stop_plugin_defs"] = suite_defaults["early_stop_plugins"]
    if "early_stop" in suite_defaults:
        defaults["early_stop_config"] = suite_defaults["early_stop"]
    if "sinks" in suite_defaults:
        defaults["sink_defs"] = suite_defaults["sinks"]
    if settings.rate_limiter:
        defaults["rate_limiter"] = settings.rate_limiter
    if settings.cost_tracker:
        defaults["cost_tracker"] = settings.cost_tracker
    if "rate_limiter" in suite_defaults:
        defaults["rate_limiter_def"] = suite_defaults["rate_limiter"]
    if "cost_tracker" in suite_defaults:
        defaults["cost_tracker_def"] = suite_defaults["cost_tracker"]
    if "prompt_pack" in suite_defaults:
        defaults["prompt_pack"] = suite_defaults["prompt_pack"]

    results = suite_runner.run(
        df,
        defaults=defaults,
        sink_factory=lambda exp: _clone_suite_sinks(settings.sinks, exp.name),
        preflight_info=preflight,
    )

    for name, entry in results.items():
        logger.info("Experiment %s completed with %s rows", name, len(entry["payload"]["results"]))


def _strip_metrics_plugins(settings) -> None:
    """Remove metrics plugins from settings and prompt packs when disabled."""

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


def _configure_sink_dry_run(settings, enable_live: bool) -> None:
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
            updated.append({"plugin": entry.get("plugin"), "options": options})
        return updated

    config = settings.orchestrator_config
    config.sink_defs = _update_defs(config.sink_defs)

    suite_defaults = settings.suite_defaults or {}
    if "sinks" in suite_defaults:
        suite_defaults["sinks"] = _update_defs(suite_defaults.get("sinks"))

    for pack in settings.prompt_packs.values():
        if isinstance(pack, dict) and pack.get("sinks"):
            pack["sinks"] = _update_defs(pack.get("sinks"))


def main(argv: Iterable[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    run(args)


if __name__ == "__main__":  # pragma: no cover
    main()
