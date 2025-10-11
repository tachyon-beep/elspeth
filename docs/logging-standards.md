# Structured Logging Guidelines

This document defines the minimum logging expectations for middleware and
result sinks so that operations teams have consistent telemetry.

## Middleware

- **Channels** – Each middleware should emit logs under a dedicated logger
  (e.g. `elspeth.health`, `elspeth.prompt_shield`, `elspeth.azure_content_safety`).
- **Heartbeat entries** (`health_monitor`):
  ```json
  {
    "requests": 42,
    "failures": 1,
    "failure_rate": 0.0238,
    "latency_count": 42,
    "latency_avg": 0.82,
    "latency_min": 0.13,
    "latency_max": 1.12
  }
  ```
  Emit at INFO level; include counts even when zero.
- **Safety violations** (`prompt_shield`, `azure_content_safety`):
  - Log at WARNING with the blocked term/category and action taken
    (abort/mask/log).
  - When masking, ensure the outgoing prompt no longer contains the term.
- **Retry exhaustion** (`azure_environment`): continue logging the sequence ID
  and metadata as structured dicts so Azure tables remain compatible.
<!-- UPDATE 2025-10-12: Include `attempts`, `max_attempts`, and serialized `history` when available so Azure ML dashboards can pivot on root causes (`src/elspeth/plugins/llms/middleware_azure.py:233`). -->
- **Suite lifecycle** (`azure_environment`):
  - `on_suite_loaded` should log experiment metadata and preflight findings once per run.
  - `on_experiment_complete` entries must include `rows`, `failures`, `cost_*` metrics, and serialized aggregates/baseline comparisons when present (`src/elspeth/plugins/llms/middleware_azure.py:208`).

## Sinks

- **Success** – Log the resolved path or destination (`outputs/...`, blob URL,
  repo path) at INFO once write completes.
- **Skip / dry run** – When `on_error=skip` or `--live-outputs` disabled,
  include the reason in the log message.
- **Failures** – Log at WARNING or ERROR with at least `path`, `exception`
  and `on_error` policy.
<!-- UPDATE 2025-10-12: Analytics sinks should log the list of files emitted along with the security level inherited from metadata to support artifact provenance tracking (`src/elspeth/plugins/outputs/analytics_report.py:69`). -->
<!-- UPDATE 2025-10-12: Visual analytics sink should log generated formats (PNG/HTML) and note when chart generation is skipped due to missing plot backends (`src/elspeth/plugins/outputs/visual_report.py:66`). -->

## Testing Expectations

- Unit tests should capture representative logs via `caplog` when the behaviour
  is core to operations (e.g. health heartbeat, safety violations).
- When emitting structured data, tests should assert key presence (e.g.
  `'failures': 1` in the heartbeat) to catch regressions.
- Avoid over-constraining format (timestamp, ordering) so logging can evolve.

## References
- `tests/test_llm_middleware.py` demonstrates log validation for heartbeats and
  safety middleware.
- `tests/test_outputs_*` should assert sink logging behaviour where relevant.
- `tests/test_reporting.py` verifies analytics/report exports log created artefacts and metadata hand-offs.

## Update History
- 2025-10-12 – Clarified retry exhaustion payload fields, suite lifecycle telemetry, and analytics sink logging expectations for accreditation traceability.
