## Summary

Plugin cleanup is skipped when plugin startup succeeded but pre-loop setup fails (notably `_build_processor`), violating the lifecycle contract and leaking resources.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py`
- Line(s): 1211-1234, 1286, 1816-1817, 2140-2164, 2182, 2301-2302
- Function/Method: `Orchestrator._execute_run`, `Orchestrator._process_resumed_rows`

## Evidence

In `_execute_run()`, plugin `on_start()` and `_build_processor()` run before the `try/finally` that performs cleanup:

```python
1216 config.source.on_start(ctx)
1217 for transform in config.transforms: transform.on_start(ctx)
1220 for sink in config.sinks.values(): sink.on_start(ctx)

1222 processor, ... = self._build_processor(...)

1286 try:
...
1816 finally:
1817     self._cleanup_plugins(config, ctx, include_source=True)
```

Same pattern in resume path:

```python
2146 for transform in config.transforms: transform.on_start(ctx)
2149 for sink in config.sinks.values(): sink.on_start(ctx)

2151 processor, ... = self._build_processor(...)

2182 try:
...
2301 finally:
2302     self._cleanup_plugins(config, ctx, include_source=False)
```

`_build_processor()` can raise after successful starts (for example missing coalesce settings: `core.py:562-566`), so started plugins are not cleaned up.

Lifecycle contract says cleanup is guaranteed if `on_start()` succeeded (example: `src/elspeth/plugins/base.py:205-210`).

## Root Cause Hypothesis

The cleanup `finally` blocks begin too late (after startup and processor construction), so exceptions in setup stages bypass cleanup.

## Suggested Fix

Restructure both methods so cleanup scope starts immediately after startup success. One safe pattern:

1. Call `on_start()` sequence.
2. Set a `startup_succeeded` flag after all `on_start()` calls succeed.
3. Enter `try/finally` that includes `_build_processor()` and execution body.
4. In `finally`, call `_cleanup_plugins(...)` only when `startup_succeeded` is `True`.

This preserves current behavior for `on_start()` failures while fixing leaks after successful startup.

## Impact

- Resource leaks (clients, pools, tracing handles, file/db/network resources).
- Lifecycle contract violation for plugins.
- Higher risk of stuck threads/connection exhaustion in long-lived processes.
