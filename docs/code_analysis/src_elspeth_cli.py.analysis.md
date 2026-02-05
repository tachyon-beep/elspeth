# Analysis: src/elspeth/cli.py

**Lines:** 2,417
**Role:** The CLI entry point for ELSPETH. Uses Typer for command handling. Implements `run`, `resume`, `validate`, `plugins list`, `purge`, `explain`, and `health` commands. Handles configuration loading, secret resolution, plugin instantiation, graph construction, pipeline execution, and user-facing output in both console and JSON modes.
**Key dependencies:** Imports from `elspeth.core.config` (settings loading), `elspeth.core.dag` (ExecutionGraph), `elspeth.core.security.config_secrets` (secret loading), `elspeth.core.landscape` (LandscapeDB, LandscapeRecorder), `elspeth.engine` (Orchestrator, PipelineConfig), `elspeth.cli_helpers` (plugin instantiation, database URL resolution). Imported by `cli_helpers.py` (circular: `_get_plugin_manager`). Entry point for the `elspeth` console script.
**Analysis depth:** FULL

## Summary

The CLI is functional and handles most error paths carefully, but contains several significant issues: a 312-line dead function that was marked deprecated but never removed, massive code duplication across three execution paths (approximately 600 lines of duplicated event formatter definitions), secret values carried in memory longer than necessary via resolution records, missing resource cleanup in the health command, and triple plugin instantiation in the resume path. The error handling is generally thorough, but there are inconsistencies in JSON error output (stdout vs stderr) that could affect consumers. Overall the file needs refactoring to eliminate duplication and dead code, but the core logic is sound for an RC-2 release.

## Critical Findings

### [675-985] Dead code: `_execute_pipeline` is defined but never called

**What:** The function `_execute_pipeline` (lines 675-985) is a 311-line function annotated as "deprecated in favor of `_execute_pipeline_with_instances`" (line 683). It is defined but never invoked anywhere in the codebase. The only caller is the `run()` command at line 471, which calls `_execute_pipeline_with_instances` instead.

**Why it matters:** Per CLAUDE.md's "No Legacy Code Policy", deprecated code must be deleted completely. More critically, this dead function creates a maintenance hazard: it instantiates plugins independently (double instantiation), creates its own LandscapeDB and event bus, and has its own cleanup path. If anyone were to call it by mistake, it would bypass the graph-based plugin flow entirely, creating a divergent execution path with different audit semantics. The function also duplicates all event formatter definitions (lines 803-935), making it easy for changes to `_execute_pipeline_with_instances` to drift from this dead copy.

**Evidence:**
```python
# Line 683
# NOTE: This function is deprecated in favor of _execute_pipeline_with_instances.
```
grep for `_execute_pipeline` (without trailing `_with_instances`) shows only the definition at line 675 and no call sites.

### [secret_resolutions lifetime] Secret values persist in memory via resolution records

**What:** The `_load_settings_with_secrets` function (line 257) and the `run()` command (line 388) both obtain `secret_resolutions` lists that contain `"secret_value"` keys with plaintext secret values (see `config_secrets.py` line 152). These records are passed through `_execute_pipeline_with_instances` (line 477 -> 994 -> 1257) and eventually to `orchestrator.run()`. The plaintext values persist in Python memory across the entire pipeline setup phase.

**Why it matters:** If the process crashes or a memory dump is taken during pipeline setup, plaintext secrets (API keys, connection strings) are recoverable from the `secret_resolutions` list. The values are intentionally included for HMAC fingerprinting (the orchestrator computes fingerprints at recording time), but the resolution records are never scrubbed after fingerprinting completes. In a high-stakes audit environment, this extends the window of secret exposure unnecessarily.

**Evidence:**
```python
# config_secrets.py line 152
"secret_value": secret_value,  # For fingerprinting, NOT for storage

# cli.py line 477 - passed through to orchestrator
secret_resolutions=secret_resolutions,
```

### [2112-2133] Resume command instantiates plugins 4 times

**What:** The `resume()` command calls `instantiate_plugins_from_config()` three separate times: once in `_build_validation_graph()` (line 1900), once in `_build_execution_graph()` (line 1928), and once directly at line 2117. Additionally, sinks are re-instantiated a fourth time in the loop at lines 2128-2133 for resume-mode configuration. This means source plugins, transform plugins, and sink plugins are each constructed 3-4 times.

**Why it matters:** Plugin constructors may have side effects (opening connections, allocating resources, loading model weights for ML transforms). Instantiating plugins multiple times wastes resources and could cause issues with plugins that hold exclusive locks or finite connection pools. The first two instantiations (`_build_validation_graph` and `_build_execution_graph`) create plugin instances that are immediately discarded after graph construction. The third instantiation at line 2117 creates instances that are also discarded when sinks are re-instantiated at lines 2128-2133 (overriding the `sinks` from `plugins`).

**Evidence:**
```python
# Line 1900 - 1st instantiation (validation graph)
plugins = instantiate_plugins_from_config(settings_config)

# Line 1928 - 2nd instantiation (execution graph)
plugins = instantiate_plugins_from_config(settings_config)

# Line 2117 - 3rd instantiation (for execution)
plugins = instantiate_plugins_from_config(settings_config)

# Lines 2128-2133 - 4th instantiation of sinks only
sink = sink_cls(sink_options)
```

## Warnings

### [573-601] Explain command: JSON errors go to stdout, non-JSON errors to stderr

**What:** In the `explain` command, when `json_output=True`, error messages are written to stdout via `typer.echo(json_module.dumps({"error": message}))` without `err=True`. When `json_output=False`, the same errors go to stderr with `err=True`. This is visible at lines 576, 587, 599, 611, 619, 637, 644.

**Why it matters:** This creates an inconsistency: a JSON consumer piping stdout may receive error messages mixed with valid output data. If the `explain` command is used in a pipeline like `elspeth explain --json ... | jq .`, an error response still produces valid JSON to stdout, which is actually reasonable. However, the inconsistency with the `run` command (which sends JSON errors to stderr at line 493 with `err=True`) means consumers cannot rely on a consistent pattern across commands. The `run` command's JSON error handler uses `err=True` (line 493), while `explain` does not.

**Evidence:**
```python
# explain command - JSON errors to stdout (no err=True)
typer.echo(json_module.dumps({"error": message}))  # line 576

# run command - JSON errors to stderr (err=True)
typer.echo(json.dumps({...}), err=True)  # line 493
```

### [454-457] Dry-run and non-execute paths in JSON mode exit with code 1 without explanation

**What:** When `output_format == "json"` and either `dry_run` or `not execute`, the command silently exits with code 1 (line 457) without emitting any JSON output explaining why.

**Why it matters:** A JSON consumer calling `elspeth run --format json -s pipeline.yaml` (without `--execute`) receives exit code 1 and no output at all. The consumer cannot distinguish between "you forgot --execute" and "your config is invalid." In console mode, a helpful message is printed (lines 448-452). JSON mode should emit an equivalent structured message.

**Evidence:**
```python
else:
    # JSON mode: early exits without console output
    if dry_run or not execute:
        raise typer.Exit(1)  # Silent failure
```

### [2304-2310] Health command: SQLAlchemy engine never disposed

**What:** The `health` command creates a SQLAlchemy `Engine` object at line 2304 to test database connectivity. While the `Connection` is properly closed via the `with` statement, the `Engine` object itself is never disposed. The engine holds a connection pool that persists.

**Why it matters:** For a health check command that runs and exits, this is a minor issue because the process terminates and the OS reclaims resources. However, if `health` were ever called programmatically (e.g., in tests or as a library function), the leaked engine pool could accumulate. More importantly, this pattern differs from the rest of the codebase which carefully manages `LandscapeDB` lifecycle with `try/finally/close()`.

**Evidence:**
```python
engine = create_engine(db_url)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
# engine.dispose() never called
```

### [48-65] Module-level singleton `_plugin_manager_cache` has no thread safety

**What:** The `_get_plugin_manager()` function uses a module-level global `_plugin_manager_cache` with a classic check-then-act pattern: check if None, create instance, assign to global. This is not thread-safe.

**Why it matters:** If ELSPETH CLI is ever invoked from multiple threads (e.g., in a test runner using parallel execution, or if the CLI were embedded in a web server), two threads could race and both create separate `PluginManager` instances. The second assignment would overwrite the first, and the first thread might use a manager that is never the canonical singleton. For a CLI that always runs single-threaded, this is low risk but worth noting.

**Evidence:**
```python
_plugin_manager_cache: PluginManager | None = None

def _get_plugin_manager() -> PluginManager:
    global _plugin_manager_cache
    if _plugin_manager_cache is None:  # TOCTOU race
        manager = PluginManager()
        manager.register_builtin_plugins()
        _plugin_manager_cache = manager
    return _plugin_manager_cache
```

### [225-226] `_ensure_output_directories` uses `hasattr` and `.get()` on sink config

**What:** Line 225 uses `hasattr(sink_config, "options")` and line 226 uses `sink_config.options.get("path")`. Per CLAUDE.md's prohibition on defensive programming patterns, `hasattr` should not be used to guard against missing attributes on system-owned objects. The `sink_config` is a Pydantic model (`SinkSettings`) which always has an `options` field.

**Why it matters:** Using `hasattr` masks potential bugs. If `SinkSettings` were refactored and `options` were renamed, this code would silently skip directory creation instead of crashing, leading to a runtime error later when the sink tries to write. The `.get("path")` on the options dict is more defensible since options are user-provided config (Tier 3), but `hasattr` on the Pydantic model is a defensive pattern the codebase prohibits.

**Evidence:**
```python
if hasattr(sink_config, "options") and isinstance(sink_config.options, dict):
    sink_path = sink_config.options.get("path")
```

### [807-935, 1091-1219, 1780-1830] Massive duplication of event formatter definitions

**What:** The same set of event formatters (`_format_phase_started`, `_format_phase_completed`, `_format_phase_error`, `_format_run_summary`, `_format_progress`) is defined three times:
1. In `_execute_pipeline` (dead code) - lines 807-935
2. In `_execute_pipeline_with_instances` - lines 1091-1219
3. In `_execute_resume_with_instances` - lines 1780-1830

Both console and JSON variants are duplicated across (1) and (2). The resume path (3) only has console formatters.

**Why it matters:** Any change to formatting (e.g., adding a new field to RunSummary, fixing a display bug) must be applied in 3 places. The resume path already lacks JSON output support, which may be intentional but is undocumented. This level of duplication is fragile and invites divergence.

**Evidence:** The console `_format_run_summary` definition appears identically at lines 897-920, 1181-1204, and 1792-1815. The only difference in the resume variant is "Resume" vs "Run" in the output string (line 1808 vs 913/1197).

## Observations

### [306-317] `_extract_secrets_config` duplicates logic in `_load_settings_with_secrets`

**What:** The function `_extract_secrets_config` (lines 306-317) performs the same operation as lines 292-293 inside `_load_settings_with_secrets`. The `run()` command calls `_extract_secrets_config` directly (line 377) instead of using `_load_settings_with_secrets`, while `validate()` and `resume()` use `_load_settings_with_secrets`. This creates two code paths for the same three-phase loading pattern.

**Why it matters:** The `run()` command manually reimplements the three-phase loading (lines 364-395) that `_load_settings_with_secrets` encapsulates. If the loading sequence changes, both paths must be updated. The docstring on `_load_settings_with_secrets` (line 266) says it "encapsulates the secret-loading flow used by run, resume, and validate" but `run()` does not actually use it.

### [975-979, 1260-1264] Return values of execution functions are never used

**What:** Both `_execute_pipeline` and `_execute_pipeline_with_instances` return `ExecutionResult` dicts (lines 975-979 and 1260-1264), but the caller in `run()` at line 471 discards the return value. The function signature declares `-> ExecutionResult` but no caller uses the result.

**Why it matters:** The return type annotation creates a false contract. Callers might assume the function's return value matters, but it does not. The real outcome is communicated via event bus subscribers (console/JSON formatters). The returned dict is vestigial.

### [1584-1659] Purge command: settings.yaml loading failure is swallowed when `--database` is provided

**What:** When the purge command has `--database` explicitly set and `settings.yaml` loading fails, the error is downgraded to a warning (e.g., line 1593, 1608, 1614). While `db_url` is correctly set from the CLI arg, the `payload_path` and `retention_days` may fall through to defaults rather than config values if settings loading failed but the user expected config values to be used.

**Why it matters:** A user providing `--database` may expect their `settings.yaml` retention policy to still apply. If settings loading fails silently (warning only), the purge uses the 90-day default, which could delete data the user intended to keep or retain data they expected purged.

### [2298-2310] Health command uses `DATABASE_URL` env var, not landscape settings

**What:** The health command checks database connectivity using the `DATABASE_URL` environment variable (line 2299), not from `settings.yaml` or `--database` CLI option. This is a different database resolution path than all other commands.

**Why it matters:** In a deployment where `settings.yaml` specifies the landscape database URL but `DATABASE_URL` is not set, the health check will report "database: skip" even though the database is fully configured. The health check may report false positives (skip) or false negatives (checking a different database than the pipeline uses).

### [2155-2164] Resume command accesses sink options with string key `"restore_source_headers"`

**What:** Line 2157 checks `"restore_source_headers" in sink_options` using a string key lookup on the options dict. This is fragile if the option name changes.

**Why it matters:** This is a magic string coupling. If `restore_source_headers` is renamed in the sink plugin's option schema, this code path silently stops providing field resolution data, causing resume operations to potentially produce mismatched headers without error.

## Verdict

**Status:** NEEDS_REFACTOR
**Recommended action:** (1) Delete the dead `_execute_pipeline` function (lines 675-985) immediately -- it violates the No Legacy Code Policy. (2) Extract event formatter definitions into a shared factory or registry to eliminate ~400 lines of duplication. (3) Refactor the `run()` command to use `_load_settings_with_secrets` like `validate()` and `resume()` do, eliminating the duplicated three-phase loading. (4) Reduce plugin instantiation in the resume path from 4x to 1x by reusing instances across validation/execution graphs. (5) Consider scrubbing `secret_value` from resolution records after fingerprinting to reduce the secret exposure window. (6) Add `engine.dispose()` to the health command's database check.
**Confidence:** HIGH -- Full file read with complete dependency analysis. All findings verified against the actual code and cross-referenced with imported modules.
