# Structured Logging Guidelines

This document defines the minimum logging expectations for middleware and
result sinks so that operations teams have consistent telemetry.

## Middleware

- **Channels** – Each middleware should emit logs under a dedicated logger
  (e.g. `dmp.health`, `dmp.prompt_shield`, `dmp.azure_content_safety`).
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

## Sinks

- **Success** – Log the resolved path or destination (`outputs/...`, blob URL,
  repo path) at INFO once write completes.
- **Skip / dry run** – When `on_error=skip` or `--live-outputs` disabled,
  include the reason in the log message.
- **Failures** – Log at WARNING or ERROR with at least `path`, `exception`
  and `on_error` policy.

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
