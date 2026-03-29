## Summary

`PluginContext` hands plugins a live, only shallow-frozen view of the run config, so a plugin can mutate nested config during execution and make runtime behavior diverge from the `settings_json`/`config_hash` snapshot already recorded for the run.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/plugin_context.py
- Line(s): 79-80
- Function/Method: `PluginContext` dataclass initialization contract

## Evidence

`PluginContext` stores `config` as a plain `Mapping[str, Any]` field and does not freeze or copy it anywhere in the file:

```python
79     run_id: str
80     config: Mapping[str, Any]
```

The orchestrator passes the resolved pipeline config directly into both the audit snapshot and the plugin context:

- [`src/elspeth/engine/orchestrator/core.py:1009`](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1009) records the run with `config=config.config`
- [`src/elspeth/engine/orchestrator/core.py:1543`](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1543) creates `PluginContext(..., config=config.config, ...)`

The run snapshot is hashed and serialized immediately at run start:

- [`src/elspeth/core/landscape/run_lifecycle_repository.py:86`](/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L86) to [`src/elspeth/core/landscape/run_lifecycle_repository.py:88`](/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L88)

```python
86     run_id = run_id or generate_id()
87     settings_json = canonical_json(config)
88     config_hash = stable_hash(config)
```

But `PipelineConfig` only shallow-wraps `config` with `MappingProxyType`:

- [`src/elspeth/engine/orchestrator/types.py:97`](/home/john/elspeth/src/elspeth/engine/orchestrator/types.py#L97)

```python
97     object.__setattr__(self, "config", MappingProxyType(dict(self.config)))
```

That blocks top-level assignment, but nested dict/list values remain mutable. So a plugin receiving `ctx.config` can still do something like mutate `ctx.config["service"]["timeout"]`, changing live behavior after the audit system already committed the original config snapshot.

This violates the auditability requirement in `CLAUDE.md`: every decision must be traceable to recorded configuration, and our-data invariants must not drift silently after capture.

## Root Cause Hypothesis

`PluginContext` treats the run config as a read-only `Mapping`, but the value is only shallowly frozen before being injected. Because `PluginContext` is the boundary where plugins get long-lived access to that object, the missing deep-freeze/copy there leaves nested config structures mutable for the rest of the run.

## Suggested Fix

Deep-freeze `config` when constructing `PluginContext`, so plugins receive an immutable snapshot instead of a live nested object graph.

Example shape:

```python
from elspeth.contracts.freeze import deep_freeze

@dataclass
class PluginContext:
    run_id: str
    config: Mapping[str, Any]

    def __post_init__(self) -> None:
        self.config = deep_freeze(self.config)
```

If `PluginContext` must stay mutable for executor-owned fields, freeze only `config`, not the whole dataclass.

## Impact

A plugin can mutate nested config after `begin_run()` has already recorded `settings_json` and `config_hash`, so later node behavior may no longer match the audit snapshot for the run. That is an audit-traceability defect: an investigator can be shown a configuration record that is no longer the one actually driving execution.
---
## Summary

`record_validation_error()` logs a preview of malformed external row data during the non-canonical fallback path, duplicating row-level pipeline data into logs outside the Landscape audit trail.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/contracts/plugin_context.py
- Line(s): 421-431
- Function/Method: `record_validation_error`

## Evidence

When stable hashing fails on malformed external data, `record_validation_error()` logs the row contents:

```python
421             try:
422                 row_id = stable_hash(row)[:16]
423             except (ValueError, TypeError) as e:
424                 # Non-canonical data (NaN, Infinity, or other non-serializable types)
425                 # Hash the repr() instead - not canonical, but preserves audit trail
426                 row_preview = repr(row)[:200] + "..." if len(repr(row)) > 200 else repr(row)
427                 logger.warning(
428                     "Row data not canonically serializable, using repr() hash: %s | Row preview: %s",
429                     str(e),
430                     row_preview,
431                 )
```

That path is real and tested for NaN/Infinity rows:

- [`tests/unit/core/landscape/test_validation_error_noncanonical.py:149`](/home/john/elspeth/tests/unit/core/landscape/test_validation_error_noncanonical.py#L149) to [`tests/unit/core/landscape/test_validation_error_noncanonical.py:184`](/home/john/elspeth/tests/unit/core/landscape/test_validation_error_noncanonical.py#L184)

The same method then records the full validation error to Landscape:

- [`/home/john/elspeth/src/elspeth/contracts/plugin_context.py:452`](/home/john/elspeth/src/elspeth/contracts/plugin_context.py#L452) to [`/home/john/elspeth/src/elspeth/contracts/plugin_context.py:460`](/home/john/elspeth/src/elspeth/contracts/plugin_context.py#L460)

So the logger is emitting row-level data that already belongs in the audit trail. `CLAUDE.md` and the logging policy explicitly forbid using logs for pipeline activity or row-level decisions.

## Root Cause Hypothesis

The fallback path was implemented to preserve observability around non-canonical rows, but it used the logger as a secondary record channel instead of treating Landscape as the sole record for row data. That conflates operational logging with audited data capture.

## Suggested Fix

Remove row contents from the log entirely. If an operational breadcrumb is still needed, log only non-probative metadata such as `run_id`, `node_id`, and exception type, or skip logging completely because the validation error is already persisted.

Safer shape:

```python
except (ValueError, TypeError) as e:
    row_id = repr_hash(row)[:16]
```

Or, at most:

```python
logger.warning(
    "validation_row_noncanonical_hash_fallback",
    extra={"run_id": self.run_id, "node_id": self.node_id, "error_type": type(e).__name__},
)
```

## Impact

Malformed source rows can leak contents into logs, bypassing the Landscape’s retention and attribution model. This creates an observability side channel for row data and weakens the project’s “Landscape is the legal record” rule.
