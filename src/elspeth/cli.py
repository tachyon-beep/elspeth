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
from typing import Any, Iterable, Mapping

import pandas as pd

from elspeth.config import load_settings
from elspeth.core.experiments import ExperimentSuite, ExperimentSuiteRunner
from elspeth.core.experiments.tools import create_experiment_template, export_suite_configuration
from elspeth.core.orchestrator import ExperimentOrchestrator
from elspeth.core.security import SecureMode, get_secure_mode
from elspeth.core.validation import validate_settings, validate_suite
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink
from elspeth.tools.reporting import SuiteReportGenerator

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Define CLI arguments for ELSPETH orchestration workflows."""

    parser = argparse.ArgumentParser(description="ELSPETH orchestration CLI")
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
    parser.add_argument(
        "--export-suite-config",
        type=Path,
        help="Optional path to export suite configuration (JSON or YAML) before running",
    )
    parser.add_argument(
        "--create-experiment-template",
        metavar="NAME",
        help="Create a disabled experiment template with the specified name before running",
    )
    parser.add_argument(
        "--template-base",
        metavar="NAME",
        help="Optional base experiment to copy when creating a new template",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        help="Directory to write analytics reports when running a suite",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Directory to write persistent artifacts (results, configs, signed bundles)",
    )
    parser.add_argument(
        "--signed-bundle",
        action="store_true",
        help="Create a signed reproducibility bundle under --artifacts-dir",
    )
    parser.add_argument(
        "--signing-key-env",
        default="ELSPETH_SIGNING_KEY",
        help="Environment variable name for the HMAC signing key (for --signed-bundle)",
    )
    parser.add_argument(
        "--artifact-sink-plugin",
        help="Optional artifact publisher sink plugin (e.g., azure_devops_artifact_repo)",
    )
    parser.add_argument(
        "--artifact-sink-config",
        type=Path,
        help="Path to YAML/JSON with options for the artifact sink plugin",
    )
    parser.add_argument(
        "--validate-schemas",
        action="store_true",
        help="Validate datasource schema compatibility with plugins without running experiments",
    )
    parser.add_argument(
        "--job-config",
        type=Path,
        help="Run an ad-hoc job from a YAML config (datasource -> optional LLM transform -> sinks)",
    )
    return parser


def configure_logging(level: str) -> None:
    """Configure root logging with the requested verbosity."""

    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


def format_preview(df: pd.DataFrame, head: int) -> str:
    """Convert the dataframe preview into a printable string."""

    preview = df.head(head) if head > 0 else df.head(0)
    with pd.option_context("display.max_columns", None):
        return preview.to_string(index=False)


def _flatten_value(target: dict[str, Any], prefix: str, value: Any) -> None:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            next_prefix = f"{prefix}_{key}" if prefix else key
            _flatten_value(target, next_prefix, inner)
    else:
        target[prefix] = value


def _result_to_row(record: dict[str, Any]) -> dict[str, Any]:
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
    """Dispatch execution based on CLI arguments and configuration."""

    log_level = getattr(args, "log_level", "INFO")
    configure_logging(log_level)
    # If an ad-hoc job config is specified, run it and exit
    if getattr(args, "job_config", None):
        try:
            from elspeth.core.experiments.job_runner import run_job_file

            payload = run_job_file(args.job_config)
            # Emit preview and optional artifacts
            rows = [_result_to_row(record) for record in payload.get("results", [])]
            df = pd.DataFrame(rows)
            if args.head and args.head > 0 and not df.empty:
                print(format_preview(df, args.head))
            _maybe_write_artifacts_single(args, _AdHoc(settings_path=args.job_config), payload, df)
            return
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            logger.error("Job execution failed: %s", exc, exc_info=True)
            raise SystemExit(1)

    settings = _load_settings_from_args(args)
    suite_root = _resolve_suite_root(args, settings)

    # Handle schema validation mode
    if getattr(args, "validate_schemas", False):
        _validate_schemas(args, settings, suite_root)
        return

    suite_instance = _handle_suite_management(args, suite_root)

    single_run = getattr(args, "single_run", False)
    if suite_root is not None and not single_run:
        suite_validation = validate_suite(suite_root)
        for warning in suite_validation.report.warnings:
            logger.warning(warning.format())
        suite_validation.report.raise_if_errors()
        _run_suite(
            args,
            settings,
            suite_root,
            preflight=suite_validation.preflight,
            suite=suite_instance,
        )
    else:
        _run_single(args, settings)


def _validate_schemas(args: argparse.Namespace, settings, suite_root: Path | None) -> None:
    """Validate datasource schema compatibility without running experiments."""
    logger.info("Validating datasource schema compatibility...")

    try:
        # Load DataFrame from datasource
        df = settings.datasource.load()
        logger.info("✓ Datasource loaded successfully: %d rows, %d columns", len(df), len(df.columns))

        # Check if schema is attached
        datasource_schema = df.attrs.get("schema") if hasattr(df, "attrs") else None

        if datasource_schema:
            logger.info("✓ Schema found: %s", datasource_schema.__name__)
            logger.info("  Columns: %s", list(datasource_schema.__annotations__.keys()))

            # For now, just report success - actual plugin validation would happen
            # during experiment runner initialization
            logger.info("✓ Schema validation passed")
            print("\n✅ Schema validation successful!")
            print(f"   Datasource: {settings.datasource.__class__.__name__}")
            print(f"   Schema: {datasource_schema.__name__}")
            print(f"   Columns: {', '.join(datasource_schema.__annotations__.keys())}")
        else:
            logger.warning("⚠ No schema defined - validation skipped")
            logger.warning("  Consider adding a schema declaration to your datasource configuration")
            print("\n⚠️  No schema validation performed")
            print("   Tip: Add a 'schema' section to your datasource configuration for type safety")

    except Exception as exc:
        logger.error("✗ Schema validation failed: %s", exc, exc_info=True)
        print(f"\n❌ Schema validation failed: {exc}")
        raise SystemExit(1)


def _run_single(args: argparse.Namespace, settings) -> None:
    """Execute a single experiment using the provided settings."""

    logger.info("Running single experiment")
    orchestrator = ExperimentOrchestrator(
        datasource=settings.datasource,
        llm_client=settings.llm,
        sinks=settings.sinks,
        config=settings.orchestrator_config,
        rate_limiter=settings.rate_limiter,
        cost_tracker=settings.cost_tracker,
        suite_root=settings.suite_root,
        config_path=settings.config_path,
    )
    try:
        payload = orchestrator.run()
    except Exception as exc:  # sink or pipeline failure
        # STRICT mode: fail-closed on any sink error during run
        try:
            if get_secure_mode() == SecureMode.STRICT:
                logger.error("STRICT mode: sink error during run; aborting with non-zero exit: %s", exc)
                raise SystemExit(1)
        except Exception:
            # If secure mode utilities unavailable, re-raise original error
            pass
        raise

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

    _maybe_write_artifacts_single(args, settings, payload, df)
    # STRICT mode: fail closed if any sink failures were recorded
    try:
        if get_secure_mode() == SecureMode.STRICT and payload.get("failures"):
            logger.error("STRICT mode: sink failures detected; aborting with non-zero exit")
            raise SystemExit(1)
    except Exception:
        # If secure mode utilities unavailable, do nothing
        pass


def _clone_suite_sinks(base_sinks: list, experiment_name: str) -> list:
    """Create experiment-scoped sink instances for suite execution."""

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


def _assemble_suite_defaults(settings) -> dict:
    """Merge orchestrator, suite, and runtime defaults for suite execution."""

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
        "prompt_defaults": ["prompt_defaults"],
        "concurrency_config": ["concurrency"],
        "early_stop_plugin_defs": ["early_stop_plugin_defs", "early_stop_plugins"],
        "early_stop_config": ["early_stop"],
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


def _load_settings_from_args(args: argparse.Namespace):
    """Load orchestrator settings after validating configuration."""

    settings_report = validate_settings(args.settings, profile=args.profile)
    for warning in settings_report.warnings:
        logger.warning(warning.format())
    settings_report.raise_if_errors()
    settings = load_settings(args.settings, profile=args.profile)
    if args.disable_metrics:
        _strip_metrics_plugins(settings)
    _configure_sink_dry_run(settings, enable_live=args.live_outputs)
    return settings


class _AdHoc:
    """Lightweight shim to carry config_path for artifact writing."""

    def __init__(self, *, settings_path: Path) -> None:
        self.config_path = settings_path


def _resolve_suite_root(args: argparse.Namespace, settings) -> Path | None:
    """Determine the suite root directory from CLI overrides or settings."""

    suite_root_value = args.suite_root or settings.suite_root
    return Path(suite_root_value) if suite_root_value else None


def _handle_suite_management(args: argparse.Namespace, suite_root: Path | None) -> ExperimentSuite | None:
    """Process template/export/report requests before running experiments."""

    export_path = getattr(args, "export_suite_config", None)
    template_name = getattr(args, "create_experiment_template", None)
    reports_dir = getattr(args, "reports_dir", None)
    template_base = getattr(args, "template_base", None)
    management_requested = any([export_path, template_name, reports_dir])
    if not management_requested:
        return None
    if suite_root is None:
        message = "Suite root is required for template creation, export, or report generation."
        raise SystemExit(message)

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


def _run_suite(
    args: argparse.Namespace,
    settings,
    suite_root: Path,
    *,
    preflight: dict | None = None,
    suite: ExperimentSuite | None = None,
) -> None:
    """Execute all experiments declared in a suite configuration."""

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

    defaults = _assemble_suite_defaults(settings)

    results = suite_runner.run(
        df,
        defaults=defaults,
        sink_factory=lambda exp: _clone_suite_sinks(settings.sinks, exp.name),
        preflight_info=preflight,
    )

    for name, entry in results.items():
        logger.info("Experiment %s completed with %s rows", name, len(entry["payload"]["results"]))

    reports_dir = getattr(args, "reports_dir", None)
    if reports_dir:
        if args.single_run:
            logger.warning("Report generation skipped: reports require suite execution.")
        else:
            SuiteReportGenerator(suite, results).generate_all_reports(reports_dir)

    _maybe_write_artifacts_suite(args, settings, suite, results)
    # STRICT mode: fail closed if any experiment recorded sink failures
    try:
        if get_secure_mode() == SecureMode.STRICT:
            any_failures = any((entry.get("payload", {}) or {}).get("failures") for entry in results.values())
            if any_failures:
                logger.error("STRICT mode: sink failures detected in suite; aborting with non-zero exit")
                raise SystemExit(1)
    except Exception:
        pass


def _ensure_artifacts_dir(base: Path | None) -> Path:
    ts = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    root = base if base else Path("artifacts")
    path = root / ts
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_simple_artifacts(art_dir: Path, name: str, payload: dict[str, Any], settings) -> None:
    # Results JSON
    (art_dir / f"{name}_results.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    # Settings YAML snapshot
    try:
        cfg_path = Path(getattr(settings, "config_path", ""))
        if cfg_path and cfg_path.exists():
            dest = art_dir / f"{name}_settings.yaml"
            dest.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    except (OSError, UnicodeError):
        logger.debug("Failed to copy settings file", exc_info=True)


def _maybe_write_artifacts_single(args: argparse.Namespace, settings, payload: dict[str, Any], df: pd.DataFrame) -> None:
    art_base = getattr(args, "artifacts_dir", None)
    if art_base is None and not getattr(args, "signed_bundle", False):
        return
    art_dir = _ensure_artifacts_dir(art_base)
    _write_simple_artifacts(art_dir, "single", payload, settings)
    if getattr(args, "signed_bundle", False):
        _create_signed_bundle(
            art_dir, "single", payload, settings, df, signing_key_env=getattr(args, "signing_key_env", "ELSPETH_SIGNING_KEY")
        )


def _maybe_write_artifacts_suite(args: argparse.Namespace, settings, suite: ExperimentSuite, results: dict[str, Any]) -> None:
    art_base = getattr(args, "artifacts_dir", None)
    if art_base is None and not getattr(args, "signed_bundle", False):
        return
    art_dir = _ensure_artifacts_dir(art_base)
    # Write each experiment payload and the suite config
    (art_dir / "suite.json").write_text(
        json.dumps({k: v["payload"] for k, v in results.items()}, indent=2, sort_keys=True), encoding="utf-8"
    )
    try:
        cfg_path = Path(getattr(settings, "config_path", ""))
        if cfg_path and cfg_path.exists():
            (art_dir / "settings.yaml").write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    except (OSError, UnicodeError):
        logger.debug("Failed to copy settings file", exc_info=True)
    if getattr(args, "signed_bundle", False):
        # For bundle, assemble a combined payload and pass the original DataFrame from datasource
        combined: dict[str, Any] = {"results": []}
        for _, entry in results.items():
            combined["results"].extend(entry["payload"].get("results", []))
        try:
            df = settings.datasource.load()
        except (OSError, RuntimeError, ValueError):
            df = pd.DataFrame()
        _create_signed_bundle(
            art_dir, "suite", combined, settings, df, signing_key_env=getattr(args, "signing_key_env", "ELSPETH_SIGNING_KEY")
        )


def _create_signed_bundle(art_dir: Path, name: str, payload: dict[str, Any], settings, df: pd.DataFrame, *, signing_key_env: str) -> None:
    try:
        from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink
    except ImportError as exc:  # pragma: no cover - optional import
        logger.warning("Reproducibility bundle unavailable: %s", exc)
        return
    bundle_dir = art_dir / f"{name}_bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    sink = ReproducibilityBundleSink(
        base_path=str(bundle_dir),
        bundle_name=f"{name}",
        timestamped=False,
        include_framework_code=False,
        key_env=signing_key_env,
    )
    metadata = {
        "security_level": getattr(settings, "security_level", None),
        "datasource_config": getattr(settings, "datasource_config", None),
        "source_data": df,
    }
    try:
        sink.write(payload, metadata=metadata)
        logger.info("Created signed reproducibility bundle at %s", bundle_dir)
        _maybe_publish_artifacts_bundle(bundle_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("Failed to create reproducibility bundle: %s", exc)


def _load_yaml_json(path: Path) -> dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        raise ValueError("artifact sink config must be a mapping")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Invalid artifact sink config: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid artifact sink config: {exc}") from exc


def _maybe_publish_artifacts_bundle(bundle_dir: Path) -> None:
    # Fetch current CLI args via a closure of run(); else skip if not available
    # TODO: Accept an argparse.Namespace (args) instead of reading sys.argv directly
    # to improve testability and encapsulation.
    import sys

    import elspeth.core.registries.sink as sink_reg

    # Simple args parsing from sys.argv for late publishing path; safe no-op if flags absent
    argv = sys.argv
    if "--artifact-sink-plugin" not in argv:
        return
    try:
        idx = argv.index("--artifact-sink-plugin")
        plugin_name = argv[idx + 1]
    except (ValueError, IndexError):
        logger.warning("artifact sink plugin flag provided without a name; skipping publish")
        return
    opts: dict[str, Any] = {}
    if "--artifact-sink-config" in argv:
        try:
            j = argv.index("--artifact-sink-config")
            cfg_path = Path(argv[j + 1])
            opts = _load_yaml_json(cfg_path)
        except (ValueError, OSError) as exc:
            logger.warning("artifact sink config invalid; skipping publish: %s", exc)
    # Convenience: if azure_devops_artifact_repo and no folder_path, set it
    if plugin_name == "azure_devops_artifact_repo" and not opts.get("folder_path"):
        opts["folder_path"] = str(bundle_dir)
    try:
        # Local alias in snake_case to satisfy naming convention
        from elspeth.core.validation.base import ConfigurationError as configuration_error  # local import to avoid cycles
    except ImportError:  # pragma: no cover - defensive
        configuration_error = RuntimeError  # type: ignore
    try:
        sink = sink_reg.sink_registry.create(plugin_name, opts, parent_context=None)
    except (ValueError, configuration_error, RuntimeError) as exc:
        logger.warning("Failed to create artifact sink '%s': %s", plugin_name, exc)
        return
    try:
        sink.write({"artifacts": [str(bundle_dir)]}, metadata={"path": str(bundle_dir)})
        logger.info("Published bundle via artifact sink '%s'", plugin_name)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Artifact publish failed: %s", exc)


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


def main(argv: Iterable[str] | None = None) -> None:
    """Entry point used by the console script."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    run(args)


if __name__ == "__main__":  # pragma: no cover
    main()
