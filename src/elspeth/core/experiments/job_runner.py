"""Ad-hoc job runner for one-off datasource->transform->sink pipelines.

This provides a lightweight way to pass a self-contained job config
describing a datasource, optional LLM transform with prompts, and sinks.

Schema (minimal):

job:
  security_level: OFFICIAL  # optional default
  determinism_level: high   # optional default
  datasource:
    plugin: csv_local
    security_level: OFFICIAL
    options: { path: data.csv, retain_local: true }
  llm:                       # optional; if omitted, writes identity rows
    plugin: mock
    security_level: OFFICIAL
    options: { seed: 42 }
  prompt:                    # required if llm present
    system: "..."
    user: "..."
    fields: [A, B, C]
  llm_middlewares:           # optional
    - name: prompt_shield
      options: {}
  sinks:
    - plugin: csv
      security_level: OFFICIAL
      options: { path: outputs/job_results.csv }

"""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Any, Mapping, Sequence

import yaml

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.llm import create_llm_from_definition
from elspeth.core.registries.sink import sink_registry
from elspeth.core.security import normalize_determinism_level, normalize_security_level

logger = logging.getLogger(__name__)


def _context_from_defaults(job: Mapping[str, Any]) -> PluginContext:
    sec = normalize_security_level(job.get("security_level"))
    det = normalize_determinism_level(job.get("determinism_level"))
    return PluginContext(
        plugin_name="job",
        plugin_kind="orchestrator",
        security_level=sec,
        determinism_level=det,
        provenance=("job_config",),
    )


def _create_datasource(defn: Mapping[str, Any], ctx: PluginContext):
    name = defn.get("plugin")
    if not isinstance(name, str) or not name:
        raise ValueError("datasource.plugin must be a non-empty string")
    return datasource_registry.create(name, defn.get("options", {}), parent_context=ctx)


def _create_sinks(defs: Sequence[Mapping[str, Any]], ctx: PluginContext):
    sinks = []
    for entry in defs:
        name = entry.get("plugin") or entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("sink.plugin must be a non-empty string")
        opts = entry.get("options", {})
        sinks.append(sink_registry.create(name, opts, parent_context=ctx))
    return sinks


def run_job_config(job: Mapping[str, Any]) -> dict[str, Any]:
    ctx = _context_from_defaults(job)

    # Datasource
    ds_def = job.get("datasource") or {}
    datasource = _create_datasource(ds_def, ctx)
    df = datasource.load()

    # Sinks
    sinks_def = job.get("sinks") or []
    sinks = _create_sinks(sinks_def, ctx)

    # Optional LLM transform
    llm_def = job.get("llm")
    if llm_def:
        prompt = job.get("prompt") or {}
        system = prompt.get("system", "")
        user = prompt.get("user", "")
        fields = list(prompt.get("fields", []))

        llm = create_llm_from_definition({"plugin": llm_def.get("plugin"), "options": llm_def.get("options", {}), "security_level": llm_def.get("security_level")}, parent_context=ctx)

        runner = ExperimentRunner(
            llm_client=llm,
            sinks=sinks,
            prompt_system=system,
            prompt_template=user,
            prompt_fields=fields,
            experiment_name=job.get("name", "job"),
            security_level=ctx.security_level,
            determinism_level=ctx.determinism_level,
        )
        # Middlewares are optional; create via registry if declared
        try:
            from elspeth.core.registries.middleware import create_middleware

            mw_defs = list(job.get("llm_middlewares", []) or [])
            if mw_defs:
                mws = []
                for entry in mw_defs:
                    defn = {
                        "name": entry.get("name") or entry.get("plugin"),
                        "options": entry.get("options", {}),
                        "security_level": entry.get("security_level"),
                    }
                    mws.append(create_middleware(defn, parent_context=ctx))
                runner.llm_middlewares = mws
        except (ImportError, ValueError) as exc:
            # If middleware registry not available or invalid config, continue without middlewares
            logger.warning("LLM middleware init failed; continuing without middlewares: %s", exc)

        payload_out = runner.run(df)
        return payload_out

    # Identity: no LLM present -> write rows as-is
    results = []
    for _, row in df.iterrows():
        results.append({"row": row.to_dict()})
    payload: dict[str, Any] = {"results": results, "metadata": {"rows": len(results)}}
    # Directly write to sinks
    for sink in sinks:
        try:
            sink.write(payload, metadata={"name": job.get("name", "job")})
        except (OSError, RuntimeError, ValueError) as exc:
            # Continue on sink failures to maximize delivery, but record the error for auditability
            sink_name = getattr(sink, "__class__", type(sink)).__name__
            logger.warning("Sink write failed; skipping sink '%s': %s", sink_name, exc)
    return payload


def run_job_file(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    job = data.get("job") or data
    return run_job_config(job)
