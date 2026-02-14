## Summary

`enable_content_recording` is accepted/logged in Azure tracing config but never applied in Azure Monitor setup (dead config field).

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1: dead config field affects observability UX, not data integrity)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure.py`
- Line(s): 320-322, 752-767
- Function/Method: `_setup_azure_ai_tracing`, `_configure_azure_monitor`

## Evidence

The code logs `enable_content_recording` as part of active tracing config:

```python
logger.info(
    "Azure AI tracing initialized",
    ...,
    content_recording=tracing_config.enable_content_recording ...
)
```

But `_configure_azure_monitor()` only passes `connection_string` and `enable_live_metrics`:

```python
configure_azure_monitor(
    connection_string=config.connection_string,
    enable_live_metrics=config.enable_live_metrics,
)
```

`enable_content_recording` is never consumed.

Related config definition also advertises this field as meaningful (`src/elspeth/plugins/llm/tracing.py:77`).

## Root Cause Hypothesis

Config field was introduced and surfaced in logs, but mapping into runtime SDK configuration was never implemented (settings-to-runtime orphaning).

## Suggested Fix

Implement explicit mapping for `enable_content_recording` in `_configure_azure_monitor()` (using the Azure Monitor/OpenTelemetry-supported parameter path). If the SDK does not support it, reject this option during validation and remove it from success logs to avoid false signaling.

## Impact

- User-configured tracing behavior is not honored.
- Operators may believe prompt/response content capture policy is enforced when it is not.
- Creates a config contract violation and observability/audit expectation drift.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/azure.py.md`
- Finding index in source report: 2
- Beads: pending
