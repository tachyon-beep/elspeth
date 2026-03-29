## Summary

Hard-coded `elspeth.__version__` is stale (`0.3.3` vs packaged `0.4.1`), causing ELSPETH to report and audit the wrong engine version.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/__init__.py
- Line(s): 8
- Function/Method: Unknown

## Evidence

`/home/john/elspeth/src/elspeth/__init__.py:8` hard-codes the package version:

```python
__version__ = "0.3.3"
```

But `/home/john/elspeth/pyproject.toml:1-3` declares a different released package version:

```toml
[project]
name = "elspeth"
version = "0.4.1"
```

That stale module constant is not isolated. Repo consumers import it directly:

- `/home/john/elspeth/src/elspeth/cli.py:21,55-59` prints `elspeth version {__version__}` for `--version`
- `/home/john/elspeth/src/elspeth/cli.py:2032-2036,2157-2166` reports `__version__` in health-check output and JSON
- `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:42,1293-1301` uses it as `ENGINE_VERSION`, then records `plugin_version = f"engine:{ENGINE_VERSION}"` for structural nodes
- `/home/john/elspeth/src/elspeth/telemetry/exporters/otlp.py:21,456-459` uses it as the OpenTelemetry instrumentation scope version

What the code does:
- Reports engine/package version from a manually maintained string in `__init__.py`

What it should do:
- Report the actual installed/project version consistently everywhere, or at minimum keep the single exported constant aligned with packaging metadata

Because the stale value feeds CLI output, telemetry metadata, and audit node registration, a `0.4.1` build can identify itself as `0.3.3`.

## Root Cause Hypothesis

The package keeps version data in two independent places: `pyproject.toml` and `src/elspeth/__init__.py`. Nothing in the repo appears to enforce synchronization, so the manual constant drifted during a release bump.

## Suggested Fix

Make `src/elspeth/__init__.py` derive `__version__` from installed package metadata instead of duplicating the value manually, for example via `importlib.metadata.version("elspeth")` with a narrowly scoped fallback only for non-installed development contexts.

If ELSPETH wants a static source-of-truth instead, then the primary fix is still in this file: update `__version__` to match `pyproject.toml` and add a test that asserts the two stay equal.

## Impact

Users and operators get incorrect version information from `elspeth --version` and health endpoints. More importantly for ELSPETH’s auditability goals, structural nodes recorded by the orchestrator can carry the wrong `engine:<version>` metadata, and OTLP spans can advertise the wrong instrumentation version. That weakens the project’s “traceable to code version” guarantee during incident analysis and formal audit.
