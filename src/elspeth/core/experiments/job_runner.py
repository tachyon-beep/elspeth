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
  # If True and middleware init fails, the job aborts; otherwise it degrades
  # gracefully and proceeds without middlewares (runner.llm_middlewares=[]).
  llm_middlewares_required: false
  sinks:
    - plugin: csv
      security_level: OFFICIAL
      options: { path: outputs/job_results.csv }

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.pipeline.artifact_pipeline import ArtifactPipeline, SinkBinding
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.llm import create_llm_from_definition
from elspeth.core.registries.sink import sink_registry
from elspeth.core.security import ensure_determinism_level, ensure_security_level

logger = logging.getLogger(__name__)


def _context_from_defaults(job: Mapping[str, Any]) -> PluginContext:
    # If job-level security not specified, infer the most restrictive level
    # declared by any plugin in the job to avoid false "conflict" errors when
    # per-plugin overrides are stricter than the default.
    job_sec = job.get("security_level")
    if job_sec is None:
        candidates: list[SecurityLevel] = []
        ds = job.get("datasource") or {}
        if ds.get("security_level") is not None:
            candidates.append(ensure_security_level(ds.get("security_level")))
        llm = job.get("llm") or {}
        if llm.get("security_level") is not None:
            candidates.append(ensure_security_level(llm.get("security_level")))
        for entry in job.get("sinks", []) or []:
            if entry.get("security_level") is not None:
                candidates.append(ensure_security_level(entry.get("security_level")))
        if candidates:
            # Choose the most restrictive level (enum comparison)
            sec = max(candidates)
        else:
            sec = ensure_security_level(None)
    else:
        sec = ensure_security_level(job_sec)
    det = ensure_determinism_level(job.get("determinism_level"))
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
    # ADR-002-B: Do NOT merge security_level into options (plugin-author-owned)
    # Only merge determinism_level (user-configurable)
    opts = dict(defn.get("options", {}) or {})
    if defn.get("determinism_level") is not None:
        opts["determinism_level"] = defn.get("determinism_level")
    return datasource_registry.create(name, opts, parent_context=ctx)


def _create_sinks(defs: Sequence[Mapping[str, Any]], ctx: PluginContext):
    sinks = []
    for entry in defs:
        plugin = entry.get("plugin") or entry.get("name")
        if not isinstance(plugin, str) or not plugin:
            raise ValueError("sink.plugin must be a non-empty string")
        # ADR-002-B: Do NOT merge security_level into options (plugin-author-owned)
        # Only merge determinism_level (user-configurable)
        raw_options = dict(entry.get("options", {}) or {})
        # Extract artifacts section so it doesn't get passed to constructor
        artifacts_cfg = raw_options.pop("artifacts", None)
        if entry.get("determinism_level") is not None:
            raw_options["determinism_level"] = entry.get("determinism_level")
        sink = sink_registry.create(plugin, raw_options, parent_context=ctx)
        # Attach artifact metadata used by ArtifactPipeline binding preparation
        setattr(sink, "_elspeth_artifact_config", artifacts_cfg or {})
        setattr(sink, "_elspeth_plugin_name", plugin)
        base_name = entry.get("name") if isinstance(entry.get("name"), str) and entry.get("name") else plugin
        setattr(sink, "_elspeth_sink_name", base_name)
        sinks.append(sink)
    return sinks


def _build_sink_bindings(sinks: Sequence[Any], *, default_context: PluginContext) -> list[SinkBinding]:
    bindings: list[SinkBinding] = []
    for index, sink in enumerate(sinks):
        artifact_config = getattr(sink, "_elspeth_artifact_config", {}) or {}
        plugin = getattr(sink, "_elspeth_plugin_name", sink.__class__.__name__)
        base_id = getattr(sink, "_elspeth_sink_name", plugin)
        sink_id = f"{base_id}:{index}"
        security_level = getattr(sink, "_elspeth_security_level", None)
        if security_level is None:
            # Fall back to plugin context if present; otherwise use job-level
            security_level = getattr(getattr(sink, "plugin_context", None), "security_level", default_context.security_level)
        if security_level is not None and not isinstance(security_level, SecurityLevel):
            security_level = ensure_security_level(security_level)
        bindings.append(
            SinkBinding(
                id=sink_id,
                plugin=plugin,
                sink=sink,
                artifact_config=artifact_config,
                original_index=index,
                security_level=security_level,
            )
        )
    return bindings


def run_job_config(job: Mapping[str, Any]) -> dict[str, Any]:
    """Execute an in-memory job definition and return the result payload."""
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

        llm = create_llm_from_definition(
            {
                "plugin": llm_def.get("plugin"),
                "options": llm_def.get("options", {}),
                "security_level": llm_def.get("security_level"),
                "determinism_level": llm_def.get("determinism_level"),
            },
            parent_context=ctx,
        )

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
        # Middlewares are optional by default; create via registry if declared
        try:
            from elspeth.core.registries.middleware import create_middleware

            mw_defs = list(job.get("llm_middlewares", []) or [])
            mw_required = bool(job.get("llm_middlewares_required", False))
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
            # If middleware registry is not available or invalid config, decide whether to fail or degrade.
            if mw_defs and mw_required:
                # Middlewares declared and required: fail the job explicitly.
                raise RuntimeError(f"LLM middleware initialization failed; cannot continue without middlewares: {exc}") from exc
            # Graceful degradation: proceed without middlewares, and make it explicit.
            logger.warning("LLM middleware init failed; continuing without middlewares: %s", exc)
            runner.llm_middlewares = []

        payload_out = runner.run(df)
        # Schema contract: ensure top-level 'failures' key is present for
        # downstream consumers that expect a stable payload shape.
        payload_out.setdefault("failures", [])
        return payload_out

    # Identity: no LLM present -> write rows as-is via ArtifactPipeline
    results = [{"row": row.to_dict()} for _, row in df.iterrows()]
    payload: dict[str, Any] = {"results": results}
    metadata: dict[str, Any] = {
        "rows": len(results),
        "name": job.get("name", "job"),
        "security_level": ctx.security_level,
        "determinism_level": ctx.determinism_level,
    }
    payload["metadata"] = metadata

    failures: list[dict[str, Any]] = []
    bindings = _build_sink_bindings(sinks, default_context=ctx)
    pipeline = ArtifactPipeline(bindings)
    pipeline.execute(payload, metadata, on_error="continue", failures=failures)
    # Always include failures for schema consistency
    payload["failures"] = failures
    if failures:
        logger.warning(
            "%d sink(s) failed during job write: %s",
            len(failures),
            ", ".join(f["sink"] for f in failures),
        )
    return payload


def run_job_file(path: str | Path) -> dict[str, Any]:
    """Load a job config from file, run it, and return the result payload."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Failed to read job config file: {path}") from exc
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Failed to parse YAML job config file: {path}") from exc
    job = data.get("job") or data
    return run_job_config(job)
