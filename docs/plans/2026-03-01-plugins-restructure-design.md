# Plugins Directory Restructure Design

**Date:** 2026-03-01
**Status:** Approved
**Branch:** RC3.3-architectural-remediation

## Goal

Reorganize `src/elspeth/plugins/` from its current mixed layout into 4 clean subfolders aligned with the SDA model:

- **sources/** — all source plugin implementations
- **sinks/** — all sink plugin implementations
- **transforms/** — all transform plugin implementations (including LLM, Azure safety)
- **infrastructure/** — shared base classes, protocols, config, clients, batching, pooling

## Decisions

1. **Azure split apart.** `azure/blob_source.py` → `sources/`, `azure/blob_sink.py` → `sinks/`, `azure/auth.py` → `infrastructure/`. No provider-grouped folder.
2. **LLM under transforms.** `plugins/llm/` → `plugins/transforms/llm/`. It IS a transform.
3. **Subsystems under infrastructure.** `clients/`, `batching/`, `pooling/` become subfolders of `infrastructure/`.
4. **No re-exports.** `plugins/__init__.py` stripped to bare package marker. All imports update to canonical paths. No legacy compatibility per CLAUDE.md no-legacy-code policy.
5. **Parallel agent swarms** for import rewriting (8 agents) and verification (7 agents).

## Current State

```
plugins/
├── __init__.py        # 30+ re-exports (public API facade)
├── base.py            # BaseSource, BaseTransform, BaseSink (691 LOC)
├── config_base.py     # PluginConfig hierarchy (333 LOC)
├── protocols.py       # Protocol definitions (560 LOC)
├── hookspecs.py       # pluggy specs (74 LOC)
├── manager.py         # PluginManager (280 LOC)
├── discovery.py       # Plugin scanning (288 LOC)
├── validation.py      # Config validation (359 LOC)
├── schema_factory.py  # Runtime Pydantic schemas (202 LOC)
├── results.py         # Re-exports from contracts (29 LOC)
├── sentinels.py       # MISSING sentinel (68 LOC)
├── utils.py           # get_nested_field (56 LOC)
├── azure/             # MIXED: source + sink + auth
│   ├── auth.py
│   ├── blob_source.py
│   └── blob_sink.py
├── clients/           # Audited HTTP/LLM/replayer/verifier
├── batching/          # BatchTransformMixin, ports, reorder buffer
├── pooling/           # PooledExecutor, AIMD throttle
├── llm/               # LLM transform + providers
├── sources/           # csv, json, null sources
├── sinks/             # csv, json, database sinks
└── transforms/        # field_mapper, passthrough, web_scrape, azure/
```

## Target State

```
plugins/
├── __init__.py              # Bare package marker, NO re-exports
│
├── sources/
│   ├── __init__.py
│   ├── csv_source.py
│   ├── json_source.py
│   ├── null_source.py
│   ├── azure_blob_source.py   # FROM azure/blob_source.py
│   └── field_normalization.py
│
├── sinks/
│   ├── __init__.py
│   ├── csv_sink.py
│   ├── json_sink.py
│   ├── database_sink.py
│   └── azure_blob_sink.py     # FROM azure/blob_sink.py
│
├── transforms/
│   ├── __init__.py
│   ├── passthrough.py
│   ├── field_mapper.py
│   ├── truncate.py
│   ├── keyword_filter.py
│   ├── json_explode.py
│   ├── batch_replicate.py
│   ├── batch_stats.py
│   ├── field_collision.py
│   ├── web_scrape.py
│   ├── web_scrape_errors.py
│   ├── web_scrape_extraction.py
│   ├── web_scrape_fingerprint.py
│   ├── safety_utils.py
│   ├── azure/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── content_safety.py
│   │   ├── errors.py
│   │   └── prompt_shield.py
│   └── llm/                   # FROM plugins/llm/
│       ├── __init__.py
│       ├── base.py
│       ├── transform.py
│       ├── provider.py
│       ├── templates.py
│       ├── tracing.py
│       ├── validation.py
│       ├── langfuse.py
│       ├── azure_batch.py
│       ├── openrouter_batch.py
│       ├── multi_query.py
│       └── providers/
│           ├── __init__.py
│           ├── azure.py
│           └── openrouter.py
│
└── infrastructure/
    ├── __init__.py
    ├── base.py                # FROM plugins/base.py
    ├── config_base.py         # FROM plugins/config_base.py
    ├── protocols.py           # FROM plugins/protocols.py
    ├── hookspecs.py           # FROM plugins/hookspecs.py
    ├── manager.py             # FROM plugins/manager.py
    ├── discovery.py           # FROM plugins/discovery.py
    ├── validation.py          # FROM plugins/validation.py
    ├── schema_factory.py      # FROM plugins/schema_factory.py
    ├── results.py             # FROM plugins/results.py
    ├── sentinels.py           # FROM plugins/sentinels.py
    ├── utils.py               # FROM plugins/utils.py
    ├── azure_auth.py          # FROM azure/auth.py
    ├── clients/               # FROM plugins/clients/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── http.py
    │   ├── llm.py
    │   ├── replayer.py
    │   └── verifier.py
    ├── batching/              # FROM plugins/batching/
    │   ├── __init__.py
    │   ├── mixin.py
    │   ├── ports.py
    │   └── row_reorder_buffer.py
    └── pooling/               # FROM plugins/pooling/
        ├── __init__.py
        ├── config.py
        ├── errors.py
        ├── executor.py
        ├── reorder_buffer.py
        └── throttle.py
```

## Import Mapping Table

| Old path | New path |
|---|---|
| `elspeth.plugins.base` | `elspeth.plugins.infrastructure.base` |
| `elspeth.plugins.config_base` | `elspeth.plugins.infrastructure.config_base` |
| `elspeth.plugins.protocols` | `elspeth.plugins.infrastructure.protocols` |
| `elspeth.plugins.hookspecs` | `elspeth.plugins.infrastructure.hookspecs` |
| `elspeth.plugins.manager` | `elspeth.plugins.infrastructure.manager` |
| `elspeth.plugins.discovery` | `elspeth.plugins.infrastructure.discovery` |
| `elspeth.plugins.validation` | `elspeth.plugins.infrastructure.validation` |
| `elspeth.plugins.schema_factory` | `elspeth.plugins.infrastructure.schema_factory` |
| `elspeth.plugins.results` | `elspeth.plugins.infrastructure.results` |
| `elspeth.plugins.sentinels` | `elspeth.plugins.infrastructure.sentinels` |
| `elspeth.plugins.utils` | `elspeth.plugins.infrastructure.utils` |
| `elspeth.plugins.clients` | `elspeth.plugins.infrastructure.clients` |
| `elspeth.plugins.clients.base` | `elspeth.plugins.infrastructure.clients.base` |
| `elspeth.plugins.clients.http` | `elspeth.plugins.infrastructure.clients.http` |
| `elspeth.plugins.clients.llm` | `elspeth.plugins.infrastructure.clients.llm` |
| `elspeth.plugins.clients.replayer` | `elspeth.plugins.infrastructure.clients.replayer` |
| `elspeth.plugins.clients.verifier` | `elspeth.plugins.infrastructure.clients.verifier` |
| `elspeth.plugins.batching` | `elspeth.plugins.infrastructure.batching` |
| `elspeth.plugins.batching.mixin` | `elspeth.plugins.infrastructure.batching.mixin` |
| `elspeth.plugins.batching.ports` | `elspeth.plugins.infrastructure.batching.ports` |
| `elspeth.plugins.batching.row_reorder_buffer` | `elspeth.plugins.infrastructure.batching.row_reorder_buffer` |
| `elspeth.plugins.pooling` | `elspeth.plugins.infrastructure.pooling` |
| `elspeth.plugins.pooling.config` | `elspeth.plugins.infrastructure.pooling.config` |
| `elspeth.plugins.pooling.errors` | `elspeth.plugins.infrastructure.pooling.errors` |
| `elspeth.plugins.pooling.executor` | `elspeth.plugins.infrastructure.pooling.executor` |
| `elspeth.plugins.pooling.reorder_buffer` | `elspeth.plugins.infrastructure.pooling.reorder_buffer` |
| `elspeth.plugins.pooling.throttle` | `elspeth.plugins.infrastructure.pooling.throttle` |
| `elspeth.plugins.llm` | `elspeth.plugins.transforms.llm` |
| `elspeth.plugins.llm.base` | `elspeth.plugins.transforms.llm.base` |
| `elspeth.plugins.llm.transform` | `elspeth.plugins.transforms.llm.transform` |
| `elspeth.plugins.llm.provider` | `elspeth.plugins.transforms.llm.provider` |
| `elspeth.plugins.llm.templates` | `elspeth.plugins.transforms.llm.templates` |
| `elspeth.plugins.llm.tracing` | `elspeth.plugins.transforms.llm.tracing` |
| `elspeth.plugins.llm.validation` | `elspeth.plugins.transforms.llm.validation` |
| `elspeth.plugins.llm.langfuse` | `elspeth.plugins.transforms.llm.langfuse` |
| `elspeth.plugins.llm.azure_batch` | `elspeth.plugins.transforms.llm.azure_batch` |
| `elspeth.plugins.llm.openrouter_batch` | `elspeth.plugins.transforms.llm.openrouter_batch` |
| `elspeth.plugins.llm.multi_query` | `elspeth.plugins.transforms.llm.multi_query` |
| `elspeth.plugins.llm.providers` | `elspeth.plugins.transforms.llm.providers` |
| `elspeth.plugins.llm.providers.azure` | `elspeth.plugins.transforms.llm.providers.azure` |
| `elspeth.plugins.llm.providers.openrouter` | `elspeth.plugins.transforms.llm.providers.openrouter` |
| `elspeth.plugins.azure.auth` | `elspeth.plugins.infrastructure.azure_auth` |
| `elspeth.plugins.azure.blob_source` | `elspeth.plugins.sources.azure_blob_source` |
| `elspeth.plugins.azure.blob_sink` | `elspeth.plugins.sinks.azure_blob_sink` |
| `from elspeth.plugins import X` | Varies by X — use canonical module path |

## Special Updates

### discovery.py PLUGIN_SCAN_CONFIG

```python
# Before
PLUGIN_SCAN_CONFIG = {
    "sources": ["sources", "azure"],
    "transforms": ["transforms", "transforms/azure", "llm"],
    "sinks": ["sinks", "azure"],
}

# After (paths relative to plugins/ root)
PLUGIN_SCAN_CONFIG = {
    "sources": ["sources"],
    "transforms": ["transforms", "transforms/azure", "transforms/llm"],
    "sinks": ["sinks"],
}
```

### discovery.py EXCLUDED_FILES

May need updates if any file names changed (e.g., `auth.py` is no longer in scan paths).

### Tier Model Allowlist

`config/cicd/enforce_tier_model/plugins.yaml` — update all file path references from old to new locations.

### CLAUDE.md Source Layout

Update the `Source Layout` section to reflect the new plugins/ structure.

## Execution Phases

### Phase 1: Structural Moves (sequential, primary agent)

All `git mv` operations in dependency order. Single commit.

### Phase 2: Import Rewriting (parallel agent swarm — 8 agents)

Each agent owns a disjoint file scope:

1. `plugins/infrastructure/` internal cross-refs (~25 files)
2. `plugins/sources/` + `plugins/sinks/` (~10 files)
3. `plugins/transforms/` including llm/, azure/ (~20 files)
4. `engine/` (~15 files)
5. `core/` + `contracts/` + `cli*.py` + `testing/` + `mcp/` + `tui/` + `telemetry/` (~20 files)
6. `tests/unit/` (~60 files)
7. `tests/integration/` + `tests/e2e/` + `tests/property/` + `tests/performance/` (~40 files)
8. Config: CLAUDE.md, tier model allowlist, discovery.py scan config (~5 files)

Single commit after all agents complete.

### Phase 3: Verification (parallel verification swarm — 7 agents)

1. `ruff check src/` — lint
2. `mypy src/` — types
3. `pytest tests/unit/` — unit tests
4. `pytest tests/integration/` — integration tests
5. Stale import grep — no old paths remain
6. Tier model enforcer
7. Config contracts checker

## Risk Assessment

- **Low risk:** File moves are git-tracked, easily reversible
- **Medium risk:** Import rewriting at scale — typos could break things
- **Mitigation:** Verification swarm catches all breakage before commit
- **Rollback:** Single `git revert` of the commit undoes everything
