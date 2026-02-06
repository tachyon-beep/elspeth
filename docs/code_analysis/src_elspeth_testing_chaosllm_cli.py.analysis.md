# Analysis: src/elspeth/testing/chaosllm/cli.py

**Lines:** 565
**Role:** CLI interface for the ChaosLLM server. Uses Typer to define commands: `serve` (start server), `presets` (list available presets), `show-config` (display effective configuration). Also defines the `chaosllm-mcp` CLI entry point for the metrics analysis MCP server.
**Key dependencies:** Imports `typer`, `load_config`/`list_presets`/`DEFAULT_MEMORY_DB` from `config.py`. Imported by `src/elspeth/cli.py` (mounts `app` and `mcp_app` as sub-commands). Lazily imports `uvicorn`, `yaml`, and `elspeth.testing.chaosllm.server`.
**Analysis depth:** FULL

## Summary

This file is a straightforward Typer CLI with reasonable error handling. The primary concern is the variable shadowing of `app` on line 375 which reassigns the module-level Typer app variable to a Starlette app instance. There is also a missing validation for `connection_failed_pct` and `connection_stall_pct` CLI overrides (these config fields have no CLI flags), and the MCP server entry point references a module that may not exist. Overall the file is sound. Confidence is HIGH.

## Critical Findings

### [375] Variable shadowing: module-level `app` reassigned to Starlette instance

**What:** Line 375 assigns `app = create_app(config)`, which shadows the module-level `app = typer.Typer(...)` defined on line 39. Inside the `serve` function body, `app` is a local variable so this does not actually corrupt the module-level Typer app. However, the naming collision is confusing and could mislead a developer into thinking the Typer app is being replaced. If this function were ever refactored to not be a function (e.g., extracted to module level), it would overwrite the Typer app.

**Why it matters:** While currently harmless due to Python scoping rules (the assignment creates a local variable), this is a maintenance hazard. The `serve` function already has access to the module-level `app` (the Typer instance) for potential sub-command registration. The same-name reassignment could cause confusion during debugging or refactoring.

**Evidence:**
```python
# Line 39: Module-level Typer app
app = typer.Typer(
    name="chaosllm",
    ...
)

# Line 375: Local variable shadows module-level name
app = create_app(config)  # This is now a Starlette app

# Line 377-383: Uses the Starlette app (correct, but confusing)
uvicorn.run(
    app,  # Starlette app, not Typer app
    ...
)
```

This should be renamed to something like `starlette_app` or `asgi_app` for clarity.

## Warnings

### [259-312] CLI overrides miss several ErrorInjectionConfig fields

**What:** The `serve` command exposes CLI flags for `rate_limit_pct`, `capacity_529_pct`, `service_unavailable_pct`, `internal_error_pct`, and `timeout_pct`. However, `ErrorInjectionConfig` also defines `bad_gateway_pct`, `gateway_timeout_pct`, `forbidden_pct`, `not_found_pct`, `connection_failed_pct`, `connection_stall_pct`, `connection_reset_pct`, `slow_response_pct`, and all the malformed response percentages (`invalid_json_pct`, `truncated_pct`, `empty_body_pct`, `missing_fields_pct`, `wrong_content_type_pct`). None of these have CLI override flags.

**Why it matters:** Users who want to override these values from the command line must resort to creating a YAML config file. This is inconsistent -- some error injection rates are overridable via CLI, others are not. While not a bug, it creates a surprising asymmetry that could frustrate users expecting full CLI coverage.

**Evidence:** Compare the CLI flags (lines 120-171) with `ErrorInjectionConfig` fields (config.py lines 193-335). The CLI exposes 5 of the 18 error percentage fields.

### [540-551] MCP server import uses type: ignore for potentially missing module

**What:** The MCP server entry point imports `elspeth.testing.chaosllm_mcp.server` with a `# type: ignore[import-not-found]` annotation and a `# type: ignore[attr-defined]` on the `.serve()` call. The comment says "The chaosllm_mcp module is implemented in a separate task."

**Why it matters:** This is effectively dead code if the module does not exist at runtime. The `ImportError` catch handles this gracefully, but the `type: ignore` directives suppress static analysis that would otherwise flag this. If the module exists but has a different API (e.g., `serve` is renamed to `run`), the `attr-defined` ignore would suppress the type error. This code should either be completed or removed per the no-legacy-code policy.

**Evidence:**
```python
# Lines 540-551
try:
    import elspeth.testing.chaosllm_mcp.server as mcp_server  # type: ignore[import-not-found]
    mcp_server.serve(database)  # type: ignore[attr-defined]
except ImportError as e:
    typer.secho(
        f"Error: MCP server not available. ...\n{e}",
        ...
    )
    raise typer.Exit(1) from e
```

However, checking the codebase, `elspeth.testing.chaosllm_mcp.server` does exist (see `tests/testing/chaosllm_mcp/test_server.py` imports). The `type: ignore` annotations may be stale and should be verified.

### [86-90] Host flag uses `-h` short option, conflicting with help convention

**What:** The `--host` option uses `-h` as its short form. In many CLI tools, `-h` is conventionally reserved for `--help`. While Typer handles `--help` separately and this does not cause a technical conflict, it violates user expectations and could confuse operators familiar with Unix conventions.

**Why it matters:** An operator typing `chaosllm serve -h` expecting help output would instead get an error about missing required arguments or would set the host to the next positional argument.

**Evidence:**
```python
# Lines 86-90
host: Annotated[
    str,
    typer.Option(
        "--host",
        "-h",  # Conventionally reserved for --help
        help="Host address to bind to.",
    ),
] = "127.0.0.1",
```

Note: Typer may prevent this conflict automatically. This should be tested.

### [456-466] Silent YAML fallback to JSON on ImportError

**What:** The `show-config` command attempts to import `yaml` for YAML output, but falls back to JSON if `yaml` is not available. Since `yaml` is imported at the top of `config.py` (which is already imported), this `ImportError` should never trigger -- if `yaml` were truly missing, `config.py` would have already failed. This makes the fallback dead code.

**Why it matters:** Dead code that silently changes output format is misleading. If a user requests `--format=yaml` and gets JSON instead, that is a silent contract violation. Since `yaml` is a hard dependency of the config module, this fallback is unreachable.

**Evidence:**
```python
# config.py line 12 (already imported, would fail before CLI runs):
import yaml

# cli.py lines 460-466:
try:
    import yaml
    typer.echo(yaml.dump(config_dict, ...))
except ImportError:
    # Fall back to JSON if yaml not available
    typer.echo(json.dumps(config_dict, indent=2))
```

## Observations

### [321-326] Broad exception handler for config loading

**What:** Lines 324-326 catch `Exception` broadly when loading config. This is acceptable for a CLI entry point where any config error should result in a user-friendly message rather than a traceback. The error message includes the exception details.

### [377-383] uvicorn.run called with app instance, not string

**What:** `uvicorn.run(app, ...)` is called with an app instance rather than an import string. This means the `workers` parameter will not work as expected on non-Unix platforms, because uvicorn needs an import string to fork workers. On Linux (the target platform per env info), this works but only for `workers=1`. For `workers > 1`, uvicorn requires the app to be specified as an import string (e.g., `"module:app"`).

**Why it matters:** The `--workers` flag defaults to 1 in the CLI but 4 in `ServerConfig`. If a user loads a config with `workers: 4` (all presets set this), uvicorn will log a warning or fail to spawn workers correctly when passed an app instance instead of an import string. This is a subtle runtime issue that would only manifest when `workers > 1`.

### [554-561] Entry points are clean and simple

**What:** The `main()` and `mcp_main_entry()` functions are straightforward wrappers that Typer expects for console script entry points. No issues.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Rename the local `app` variable on line 375 to avoid shadowing. Verify whether `uvicorn.run()` works correctly with `workers > 1` when passed an app instance (vs. import string). Consider either completing the missing CLI flags for error injection or documenting the intentional subset. Remove stale `type: ignore` annotations on the MCP import if the module now exists.
**Confidence:** HIGH -- The issues are clearly identifiable from code inspection and Typer/uvicorn documentation.
