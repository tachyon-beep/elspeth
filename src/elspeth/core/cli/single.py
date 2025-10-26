"""Single-run execution helpers used by the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .common import (
    create_signed_bundle,
    ensure_artifacts_dir,
    maybe_publish_artifacts_bundle,
    write_simple_artifacts,
)


def run_single(args: Any, settings: Any) -> None:
    """Execute a single experiment using the provided settings.

    Mirrors legacy CLI behavior while delegating artifact handling to this module.
    """
    import logging  # pylint: disable=import-outside-toplevel
    from pathlib import Path  # pylint: disable=import-outside-toplevel

    from elspeth.core.orchestrator import ExperimentOrchestrator  # pylint: disable=import-outside-toplevel
    from elspeth.core.security.secure_mode import SecureMode, get_secure_mode  # pylint: disable=import-outside-toplevel

    logger = logging.getLogger(__name__)

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
        try:
            if get_secure_mode() == SecureMode.STRICT:
                logger.error("STRICT mode: sink error during run; aborting with non-zero exit: %s", exc)
                raise SystemExit(1)
        except Exception:
            logger.debug("Secure mode utilities unavailable; continuing to re-raise original exception", exc_info=True)
        raise

    for failure in payload["failures"]:
        retry = failure.get("retry") or {}
        attempts = retry.get("attempts")
        logger.error(
            "Row processing failed after %s attempts: %s",
            attempts if attempts is not None else 1,
            failure.get("error"),
        )

    rows = [dict(r.get("row") or {}) for r in payload.get("results", [])]
    df = pd.DataFrame(rows)

    if getattr(args, "output_csv", None):
        output_path: Path = args.output_csv
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("Saved dataset to %s", output_path)

    head = getattr(args, "head", 0)
    if head and head > 0 and not df.empty:
        with pd.option_context("display.max_columns", None):
            print(df.head(head).to_string(index=False))

    maybe_write_artifacts_single(args, settings, payload, df)
    try:
        if get_secure_mode() == SecureMode.STRICT and payload["failures"]:
            logger.error("STRICT mode: sink failures detected; aborting with non-zero exit")
            raise SystemExit(1)
    except Exception:
        logger.debug("Secure mode utilities unavailable after run; continuing without exit enforcement", exc_info=True)


def maybe_write_artifacts_single(args: Any, settings: Any, payload: dict[str, Any], df: pd.DataFrame) -> None:
    """Optionally persist CLI artifacts and publish a signed bundle."""
    art_base = getattr(args, "artifacts_dir", None)
    if art_base is None and not getattr(args, "signed_bundle", False):
        return
    art_dir = ensure_artifacts_dir(art_base)
    write_simple_artifacts(art_dir, "single", payload, settings)
    if getattr(args, "signed_bundle", False):
        # ADR-002: Extract operating_level from metadata for bundle creation
        # For single runs, metadata.security_level is the pipeline operating level
        operating_level = payload.get("metadata", {}).get("security_level")

        bundle_dir = create_signed_bundle(
            art_dir,
            "single",
            payload,
            settings,
            df,
            signing_key_env=getattr(args, "signing_key_env", "ELSPETH_SIGNING_KEY"),
            operating_level=operating_level,
        )
        if bundle_dir:
            maybe_publish_artifacts_bundle(
                bundle_dir,
                plugin_name=getattr(args, "artifact_sink_plugin", None),
                config_path=getattr(args, "artifact_sink_config", None),
                operating_level=operating_level,
            )


__all__ = ["maybe_write_artifacts_single", "run_single"]
