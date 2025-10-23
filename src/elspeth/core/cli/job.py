"""Ad-hoc job execution helpers used by the CLI entrypoint."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def execute_job_file(job_config: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    """Run an ad-hoc job config and return (payload, DataFrame rows).

    This function isolates the job execution path to improve CLI maintainability.
    The caller is responsible for preview printing and artifact handling.
    """
    try:
        from elspeth.core.experiments.job_runner import run_job_file  # import inside to avoid CLI import bloat
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Job execution unavailable: %s", exc)
        raise SystemExit(1) from exc

    try:
        payload = run_job_file(job_config)
        rows = [_record_to_row(record) for record in payload.get("results", [])]
        df = pd.DataFrame(rows)
        return payload, df
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        logger.exception("Job execution failed")
        raise SystemExit(1) from exc


def _record_to_row(record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record.get("row") or {})

    def consume_response(prefix: str, response: dict[str, Any] | None) -> None:
        if not response:
            return
        content = response.get("content")
        if content is not None:
            row[prefix] = content
        metrics = response.get("metrics")
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                row[f"{prefix}_metric_{key}"] = value

    consume_response("llm_content", record.get("response"))
    for name, response in (record.get("responses") or {}).items():
        consume_response(f"llm_{name}", response)

    for key, value in (record.get("metrics") or {}).items():
        row[f"metric_{key}"] = value

    retry_info = record.get("retry")
    if retry_info:
        row["retry_attempts"] = retry_info.get("attempts")
        row["retry_max_attempts"] = retry_info.get("max_attempts")
        history = retry_info.get("history")
        if history:
            import json

            row["retry_history"] = json.dumps(history)

    if "security_level" in record:
        row["security_level"] = record["security_level"]

    return row


__all__ = ["execute_job_file"]
