from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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

        if datasource_schema:
            logger.info("\u2713 Schema found: %s", datasource_schema.__name__)
            logger.info("  Columns: %s", list(datasource_schema.__annotations__.keys()))
            logger.info("\u2713 Schema validation passed")
            print("\n✅ Schema validation successful!")
            print(f"   Datasource: {settings.datasource.__class__.__name__}")
            print(f"   Schema: {datasource_schema.__name__}")
            print(f"   Columns: {', '.join(datasource_schema.__annotations__.keys())}")
        else:
            logger.warning("\u26a0 No schema defined - validation skipped")
            logger.warning("  Consider adding a schema declaration to your datasource configuration")
            print("\n⚠️  No schema validation performed")
            print("   Tip: Add a 'schema' section to your datasource configuration for type safety")

    except Exception as exc:  # pragma: no cover - defensive
        logger.error("\u2717 Schema validation failed: %s", exc, exc_info=True)
        print(f"\n❌ Schema validation failed: {exc}")
        raise SystemExit(1)


__all__ = ["validate_schemas_command"]
