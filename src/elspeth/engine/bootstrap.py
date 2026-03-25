"""Programmatic pipeline bootstrap — reusable entry point for dependency resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from elspeth.core.dependency_config import (
    CommencementGateResult,
    DependencyRunResult,
    PreflightResult,
)
from elspeth.engine.orchestrator.types import RunResult


def bootstrap_and_run(settings_path: Path) -> RunResult:
    """Load config, instantiate plugins, build graph, run pipeline.

    This is the programmatic equivalent of ``elspeth run --execute``.
    Used by the dependency resolver to run sub-pipelines.

    Handles dependency resolution and commencement gates if configured in
    the pipeline settings. Dependency sub-pipelines are resolved recursively
    (cycle detection runs first). Commencement gates evaluate after dependencies
    complete and collection probes report.

    Does NOT handle:
    - Output formatting (no typer, no console messages)
    - Passphrase prompting (encrypted DBs not supported for dependency runs)
    - Secret resolution (secrets are inherited from the parent process environment)

    Args:
        settings_path: Absolute or relative path to pipeline settings YAML.

    Returns:
        RunResult from orchestrator.run()

    Raises:
        Any exception from config loading, plugin instantiation, graph validation,
        or pipeline execution. Caller is responsible for error handling.
    """
    from elspeth.cli import _orchestrator_context
    from elspeth.cli_helpers import instantiate_plugins_from_config
    from elspeth.core.config import load_settings
    from elspeth.core.dag import ExecutionGraph
    from elspeth.core.landscape import LandscapeDB
    from elspeth.core.payload_store import FilesystemPayloadStore

    # Phase 1: Load and validate config
    # No secret resolution — secrets are inherited from the parent process
    # environment (already populated by root pipeline's _load_settings_with_secrets)
    config = load_settings(settings_path)

    # Phase 2: Instantiate plugins
    plugins = instantiate_plugins_from_config(config)

    # Phase 3: Build and validate execution graph
    # Exclude export sink from graph (same logic as CLI)
    execution_sinks = plugins.sinks
    if config.landscape.export.enabled and config.landscape.export.sink:
        export_sink_name = config.landscape.export.sink
        execution_sinks = {k: v for k, v in plugins.sinks.items() if k != export_sink_name}

    graph = ExecutionGraph.from_plugin_instances(
        source=plugins.source,
        source_settings=plugins.source_settings,
        transforms=plugins.transforms,
        sinks=execution_sinks,
        aggregations=plugins.aggregations,
        gates=list(config.gates),
        coalesce_settings=list(config.coalesce) if config.coalesce else None,
    )
    graph.validate()

    # Phase 3.5: Dependency resolution (if configured)
    dependency_results: list[DependencyRunResult] = []
    gate_results: list[CommencementGateResult] = []
    if config.depends_on:
        from elspeth.engine.dependency_resolver import detect_cycles, resolve_dependencies

        # Cycle detection first (cheap, reads only depends_on keys from YAML)
        detect_cycles(settings_path)

        # Run dependencies sequentially — each calls bootstrap_and_run() recursively.
        # Design note: sub-pipelines that declare their own depends_on will also
        # resolve their dependencies recursively. Cycle detection prevents infinite
        # loops. Diamond dependencies (A→B, A→C, B→D, C→D) cause D to run twice —
        # acceptable for correctness since each run produces its own audit trail.
        dependency_results = resolve_dependencies(
            depends_on=config.depends_on,
            parent_settings_path=settings_path,
        )

    # Phase 3.6: Commencement gates (if configured)
    if config.commencement_gates:
        from elspeth.engine.commencement import build_preflight_context, evaluate_commencement_gates
        from elspeth.plugins.infrastructure.probe_factory import build_collection_probes

        # Build probes and execute them
        probes = build_collection_probes(config.collection_probes)
        probe_results = {}
        for probe in probes:
            result = probe.probe()
            probe_results[result.collection] = {
                "reachable": result.reachable,
                "count": result.count,
            }

        # Convert dependency results to gate-accessible dict
        dep_run_dict = {
            r.name: {
                "run_id": r.run_id,
                "settings_hash": r.settings_hash,
                "duration_ms": r.duration_ms,
                "indexed_at": r.indexed_at,
            }
            for r in dependency_results
        }

        context = build_preflight_context(
            dependency_results=dep_run_dict,
            collection_probes=probe_results,
        )
        gate_results = evaluate_commencement_gates(config.commencement_gates, context)

    # Build pre-flight result for audit recording (passed through to orchestrator)
    preflight = None
    if dependency_results or gate_results:
        preflight = PreflightResult(
            dependency_runs=tuple(dependency_results),
            gate_results=tuple(gate_results),
        )

    # Phase 4: Construct infrastructure and run
    db = LandscapeDB.from_url(
        config.landscape.url,
        dump_to_jsonl=config.landscape.dump_to_jsonl,
        dump_to_jsonl_path=config.landscape.dump_to_jsonl_path,
        dump_to_jsonl_fail_on_error=config.landscape.dump_to_jsonl_fail_on_error,
        dump_to_jsonl_include_payloads=config.landscape.dump_to_jsonl_include_payloads,
        dump_to_jsonl_payload_base_path=(
            str(config.payload_store.base_path)
            if config.landscape.dump_to_jsonl_payload_base_path is None
            else config.landscape.dump_to_jsonl_payload_base_path
        ),
    )

    if config.payload_store.backend != "filesystem":
        raise ValueError(f"Unsupported payload store backend '{config.payload_store.backend}'. Only 'filesystem' is currently supported.")
    payload_store = FilesystemPayloadStore(config.payload_store.base_path)

    output_format: Literal["console", "json"] = "json"
    try:
        with _orchestrator_context(
            config,
            graph,
            plugins,
            db=db,
            output_format=output_format,
        ) as ctx:
            return ctx.orchestrator.run(
                ctx.pipeline_config,
                graph=graph,
                settings=config,
                payload_store=payload_store,
                preflight_results=preflight,
            )
    finally:
        db.close()
