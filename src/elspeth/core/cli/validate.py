from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from elspeth.core.experiments.validation import validate_plugin_schemas
from elspeth.core.orchestrator import ExperimentOrchestrator
from elspeth.core.validation.base import ConfigurationError

logger = logging.getLogger(__name__)


def validate_schemas_command(args: Any, settings: Any, suite_root: Path | None) -> None:
    """Validate datasource schema compatibility without running experiments.

    Mirrors the existing CLI behaviour while keeping the top-level CLI
    module slimmer for maintainability.
    """
    logger.info("Validating datasource schema compatibility...")

    try:
        # Load DataFrame from datasource
        df = settings.datasource.load()
        logger.info("\u2713 Datasource loaded successfully: %d rows, %d columns", len(df), len(df.columns))

        # Check if schema is attached
        datasource_schema = df.attrs.get("schema") if hasattr(df, "attrs") else None

        if not datasource_schema:
            # No schema attached: subcommand should fail; legacy flag prints guidance
            logger.warning("\u26a0 No schema defined - validation skipped")
            logger.warning("  Consider adding a schema declaration to your datasource configuration")
            if getattr(args, "command", None) == "validate-schemas":
                print("\n❌ Datasource has no declared schema (see logs for guidance)")
                raise SystemExit(1)
            print("\n⚠️  No schema validation performed")
            print("   Tip: Add a 'schema' section to your datasource configuration for type safety")
            return

        # If LLM client not provided in settings (legacy or partial context),
        # perform basic success reporting without plugin compatibility.
        if not hasattr(settings, "llm"):
            logger.info("\u2713 Schema found: %s", datasource_schema.__name__)
            print("\n✅ Schema validation successful!")
            print(f"   Datasource: {settings.datasource.__class__.__name__}")
            print(f"   Schema: {datasource_schema.__name__}")
            print(f"   Columns: {', '.join(datasource_schema.__annotations__.keys())}")
            return

        # Build orchestrator to construct plugin instances then validate compatibility
        orchestrator = ExperimentOrchestrator(
            datasource=settings.datasource,
            llm_client=settings.llm,
            sinks=settings.sinks,
            config=settings.orchestrator_config,
            rate_limiter=getattr(settings, "rate_limiter", None),
            cost_tracker=getattr(settings, "cost_tracker", None),
            suite_root=getattr(settings, "suite_root", None),
            config_path=getattr(settings, "config_path", None),
        )

        # Perform plugin compatibility checks using the runner's validation routine
        validate_plugin_schemas(
            datasource_schema,
            row_plugins=orchestrator.experiment_runner.row_plugins or [],
            aggregator_plugins=orchestrator.experiment_runner.aggregator_plugins or [],
            validation_plugins=orchestrator.experiment_runner.validation_plugins or [],
        )

        # Prompt fields preflight: ensure all prompt_fields exist in datasource schema
        fields = list(getattr(datasource_schema, "__annotations__", {}).keys())
        prompt_fields = list(getattr(settings.orchestrator_config, "prompt_fields", []) or [])
        if prompt_fields:
            missing = [f for f in prompt_fields if f not in fields]
            if missing:
                msg = f"Missing prompt_fields in datasource schema: {missing}. Declared fields: {fields}"
                logger.error(msg)
                print(f"\n❌ {msg}")
                raise SystemExit(1)

        # Enforce sink declarations for data movement: requires produces()/consumes() returning lists
        for sink in settings.sinks or []:
            produces = getattr(sink, "produces", None)
            consumes = getattr(sink, "consumes", None)
            if not callable(produces) or not callable(consumes):
                msg = f"Sink '{getattr(sink, 'name', sink.__class__.__name__)}' must implement produces() and consumes()."
                logger.error(msg)
                print(f"\n❌ {msg}")
                raise SystemExit(1)
            try:
                prod = produces()
                cons = consumes()
            except Exception as exc:  # pragma: no cover - defensive
                msg = f"Sink '{getattr(sink, 'name', sink.__class__.__name__)}' produces()/consumes() raised: {exc}"
                logger.error(msg)
                print(f"\n❌ {msg}")
                raise SystemExit(1)
            if not isinstance(prod, list) or not isinstance(cons, list):
                msg = f"Sink '{getattr(sink, 'name', sink.__class__.__name__)}' produces()/consumes() must return lists."
                logger.error(msg)
                print(f"\n❌ {msg}")
                raise SystemExit(1)

        # Report success with some helpful context
        row_plugins = [p.name for p in (orchestrator.experiment_runner.row_plugins or [])]
        agg_plugins = [p.name for p in (orchestrator.experiment_runner.aggregator_plugins or [])]
        val_plugins = [p.name for p in (orchestrator.experiment_runner.validation_plugins or [])]

        logger.info("\u2713 Schema found: %s", datasource_schema.__name__)
        logger.info("  Columns: %s", list(datasource_schema.__annotations__.keys()))
        logger.info("\u2713 Plugin compatibility checks passed")
        print("\n✅ Schema validation successful!")
        print(f"   Datasource: {settings.datasource.__class__.__name__}")
        print(f"   Schema: {datasource_schema.__name__}")
        print(f"   Columns: {', '.join(datasource_schema.__annotations__.keys())}")
        if row_plugins:
            print(f"   Row plugins: {', '.join(row_plugins)}")
        if agg_plugins:
            print(f"   Aggregators: {', '.join(agg_plugins)}")
        if val_plugins:
            print(f"   Validation plugins: {', '.join(val_plugins)}")

    except ConfigurationError as exc:
        logger.error("\u2717 Configuration error during schema validation: %s", exc)
        print(f"\n❌ Configuration error: {exc}")
        raise SystemExit(1)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("\u2717 Schema validation failed: %s", exc, exc_info=True)
        print(f"\n❌ Schema validation failed: {exc}")
        raise SystemExit(1)


__all__ = ["validate_schemas_command"]
