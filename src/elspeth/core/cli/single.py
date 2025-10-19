from __future__ import annotations

from typing import Any

import pandas as pd

from .common import create_signed_bundle, ensure_artifacts_dir, write_simple_artifacts


def run_single(args: Any, settings: Any) -> None:
    """Execute a single experiment using the provided settings.

    Mirrors legacy CLI behavior while delegating artifact handling to this module.
    """
    import logging
    from pathlib import Path

    from elspeth.core.orchestrator import ExperimentOrchestrator
    from elspeth.core.security.secure_mode import SecureMode, get_secure_mode

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
        if get_secure_mode() == SecureMode.STRICT and payload.get("failures"):
            logger.error("STRICT mode: sink failures detected; aborting with non-zero exit")
            raise SystemExit(1)
    except Exception:
        pass


def maybe_write_artifacts_single(args: Any, settings: Any, payload: dict[str, Any], df: pd.DataFrame) -> None:
    art_base = getattr(args, "artifacts_dir", None)
    if art_base is None and not getattr(args, "signed_bundle", False):
        return
    art_dir = ensure_artifacts_dir(art_base)
    write_simple_artifacts(art_dir, "single", payload, settings)
    if getattr(args, "signed_bundle", False):
        create_signed_bundle(
            art_dir,
            "single",
            payload,
            settings,
            df,
            signing_key_env=getattr(args, "signing_key_env", "ELSPETH_SIGNING_KEY"),
        )


__all__ = ["maybe_write_artifacts_single", "run_single"]
