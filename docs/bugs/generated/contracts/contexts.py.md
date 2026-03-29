## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/contracts/contexts.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/contracts/contexts.py
- Line(s): 36-198
- Function/Method: SourceContext, TransformContext, SinkContext, LifecycleContext

## Evidence

`/home/john/elspeth/src/elspeth/contracts/contexts.py:36-198` defines four narrow runtime-checkable protocols that match the concrete `PluginContext` surface used by plugins.

`/home/john/elspeth/src/elspeth/contracts/plugin_context.py:79-137` contains the corresponding fields (`run_id`, `node_id`, `operation_id`, `landscape`, `telemetry_emit`, `state_id`, `token`, `batch_token_ids`, `contract`, `rate_limit_registry`, `concurrency_config`) and `/home/john/elspeth/src/elspeth/contracts/plugin_context.py:139-197` contains the corresponding methods (`get_checkpoint`, `set_checkpoint`, `clear_checkpoint`, `record_call`).

`/home/john/elspeth/tests/unit/contracts/test_context_protocols.py:20-48` explicitly checks that a real `PluginContext` satisfies all four protocols at runtime, and `/home/john/elspeth/tests/unit/contracts/test_context_protocols.py:158-208` mechanically verifies that every protocol member exists on `PluginContext` and that no public `PluginContext` members are left unaccounted for.

`/home/john/elspeth/tests/unit/plugins/test_base_signatures.py:38-95` verifies the base plugin classes use these protocol types in their signatures, so the contracts are wired into the plugin API.

Integration call sites also line up with the declared members:
- `/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py:113-129` uses `LifecycleContext.run_id`, `telemetry_emit`, `landscape`, and `rate_limit_registry`, all present in the protocol.
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:101-118` and `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:150-202` use `SinkContext.contract`, `landscape`, and `run_id`, all present in the protocol.
- `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1543-1568` constructs one `PluginContext` with the required infrastructure and passes it through plugin lifecycle hooks, which supports the intended integration model.

I also attempted to run the focused protocol/signature tests, but the environment could not provide a writable temp directory, so execution failed before tests ran:
`FileNotFoundError: No usable temporary directory found in ['/tmp', '/var/tmp', '/usr/tmp', '/home/john/elspeth']`.

## Root Cause Hypothesis

No bug identified

## Suggested Fix

No code change recommended in `/home/john/elspeth/src/elspeth/contracts/contexts.py`.

## Impact

No concrete breakage confirmed in this file. Based on the inspected code and existing tests, the protocol definitions currently align with the concrete context object and the plugin call sites that depend on them.
