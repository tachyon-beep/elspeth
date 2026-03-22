# Bug Report: errorworks multi-worker presets crash on startup

**Package:** errorworks 0.1.1
**Affects:** `chaosllm serve`, `chaosweb serve` (likely `chaosengine serve` too)
**Severity:** Medium — all presets with `workers > 1` fail immediately

## Summary

Any preset that sets `workers: N` where N > 1 causes uvicorn to exit with code 1 on startup. This affects the `realistic` preset (workers: 4) and likely others.

## Reproduction

```bash
# Fails — realistic preset has workers: 4
chaosllm serve --preset=realistic
# Output:
#   WARNING: You must pass the application as an import string to enable 'reload' or 'workers'.
#   [Exit 1]

# Workaround — explicitly override to 1 worker
chaosllm serve --preset=realistic --workers=1
# Works fine
```

## Root Cause

Uvicorn requires the application to be passed as a **Python import string** (e.g., `"errorworks.llm.server:app"`) when using `workers > 1`. This is because uvicorn needs to fork the process and reimport the app in each child worker.

The CLI is currently passing the app as a **Python object** directly to `uvicorn.run()`, which only supports single-worker mode. When a preset specifies `workers: 4`, uvicorn detects the incompatibility and refuses to start.

## Suggested Fix

In the `serve` command implementation, detect when `workers > 1` and switch to passing the app as an import string:

```python
if workers > 1:
    uvicorn.run("errorworks.llm.server:app", host=host, port=port, workers=workers)
else:
    uvicorn.run(app, host=host, port=port)
```

Or always use the import string form regardless of worker count.

## Affected Presets

| Preset | workers | Status |
|--------|---------|--------|
| realistic | 4 | **Broken** |
| silent | ? | Check |
| gentle | ? | Check |
| chaos | ? | Check |
| stress_aimd | ? | Check |
| stress_extreme | ? | Check |

## Workaround

Pass `--workers=1` explicitly to override any preset's worker count.

## Additional Note

The same bug likely affects `chaosweb serve` — confirmed identical failure with `chaosweb serve --preset=realistic` (exits with the same uvicorn warning). However, in one test the multi-worker attempt appeared to leave a zombie single-worker process bound to the port, suggesting the main process may start before the fork check fails.
