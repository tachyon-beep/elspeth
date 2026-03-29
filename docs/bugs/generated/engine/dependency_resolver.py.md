## Summary

`resolve_dependencies()` downgrades an interrupted dependency run into a generic `DependencyFailedError`, discarding the dependency run's real `run_id` and resumable semantics.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/dependency_resolver.py
- Line(s): 114-132
- Function/Method: `resolve_dependencies`

## Evidence

`resolve_dependencies()` only special-cases `KeyboardInterrupt`, then wraps every other exception in `DependencyFailedError` with a synthetic `run_id="pre-run"`:

```python
try:
    run_result = runner(dep_path)
except KeyboardInterrupt:
    raise
...
except Exception as exc:
    raise DependencyFailedError(
        dependency_name=dep.name,
        run_id="pre-run",
        reason=f"Dependency pipeline failed before generating a run ID: {type(exc).__name__}: {exc}",
    ) from exc
```

Source: `/home/john/elspeth/src/elspeth/engine/dependency_resolver.py:114-132`

But the injected runner is `bootstrap_and_run()`:

- `/home/john/elspeth/src/elspeth/engine/bootstrap.py:72-76`
- `/home/john/elspeth/src/elspeth/cli_helpers.py:209-310`

That runner ultimately calls the orchestrator, which raises `GracefulShutdownError` with the real dependency `run_id` when a run is interrupted:

- `/home/john/elspeth/src/elspeth/contracts/errors.py:664-694`
- `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1226-1228`

Top-level CLI execution has a dedicated handler for `GracefulShutdownError` that preserves interrupt semantics and prints the resume command:

- `/home/john/elspeth/src/elspeth/cli.py:517-534`

In contrast, when the same interruption happens inside a dependency, `dependency_resolver.py` converts it into a normal pre-flight failure with `run_id="pre-run"`. That means the real dependency run already exists in Landscape, but the caller is told it never got a run ID.

There is no resolver test covering `GracefulShutdownError`; existing tests only verify passthrough for `KeyboardInterrupt`, `FrameworkBugError`, `AuditIntegrityError`, and a few programming errors:

- `/home/john/elspeth/tests/unit/engine/test_dependency_resolver.py:208-288`

## Root Cause Hypothesis

The resolver assumes any non-`KeyboardInterrupt` exception from `runner()` happened before the dependency run was created. That assumption is false for orchestrator-driven interruptions: the dependency run has already been opened, marked `INTERRUPTED`, and assigned a real `run_id` before `GracefulShutdownError` is raised.

## Suggested Fix

Preserve interruption semantics from the runner instead of wrapping them as ordinary dependency failures. At minimum, add an explicit `except GracefulShutdownError: raise` branch ahead of the generic `except Exception`.

If the design requires wrapping, the wrapper must carry the real dependency `run_id` rather than hard-coding `"pre-run"`.

## Impact

A dependency pipeline interrupted during preflight becomes operationally untraceable from the parent run entrypoint:

- The user loses the real dependency `run_id`.
- The CLI cannot offer `elspeth resume <run_id> --execute`.
- A resumable interrupted dependency is misreported as a generic failure.
- Audit navigation is degraded because the error message claims no run ID was generated when Landscape already recorded one.
---
## Summary

`_load_depends_on()` assumes `yaml.safe_load()` returns a mapping and crashes with `AttributeError` on malformed top-level YAML, bypassing the intended Tier 3 validation path.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/engine/dependency_resolver.py
- Line(s): 28-35
- Function/Method: `_load_depends_on`

## Evidence

The function reads raw YAML and immediately calls `.get()` on the parsed object:

```python
with settings_path.open() as f:
    data = yaml.safe_load(f) or {}
deps: list[dict[str, str]] = data.get("depends_on", [])
```

Source: `/home/john/elspeth/src/elspeth/engine/dependency_resolver.py:28-33`

If the dependency settings file is valid YAML but not a mapping, for example:

```yaml
- just
- a
- list
```

then `yaml.safe_load()` returns a `list`, and `data.get(...)` raises `AttributeError` before any explicit validation runs.

That matters because dependency cycle detection intentionally reads raw dependency YAML before full config loading:

- `/home/john/elspeth/src/elspeth/engine/bootstrap.py:64-76`

And the CLI treats `ValueError` as an expected pre-flight validation failure, but unexpected exceptions become fatal internal errors:

- `/home/john/elspeth/src/elspeth/cli.py:486-503`

So a malformed dependency file top level is surfaced as a fatal bug-shaped crash instead of a normal operator-facing config error.

The current tests cover bad `depends_on` shapes inside a mapping, but not a non-mapping top-level document:

- `/home/john/elspeth/tests/unit/engine/test_dependency_resolver.py:19-53`

## Root Cause Hypothesis

The function validates the `depends_on` field shape but never validates the shape of the YAML document itself. The early `.get()` call effectively reintroduces the forbidden defensive-pattern problem in reverse: instead of failing with a meaningful boundary error, it fails with an incidental Python attribute error.

## Suggested Fix

Validate the top-level YAML object before accessing fields:

```python
data = yaml.safe_load(f)
if data is None:
    data = {}
if not isinstance(data, dict):
    raise ValueError(f"{settings_path} must contain a YAML mapping at the top level, got {type(data).__name__}")
```

Then continue validating `depends_on` as it does now.

## Impact

Malformed dependency settings files are misclassified as internal failures instead of operator config errors:

- Preflight aborts with an `AttributeError` path.
- The CLI fatal-error handler is triggered instead of the normal "Pre-flight check failed" path.
- Operators get a less actionable message.
- Tier 3 boundary validation is incomplete for the very raw YAML path this function exists to protect.
