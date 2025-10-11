# Incident Response Flow

```penguin
diagram "Middleware Incident Response" {
  direction: down

  node detect "Violation Detected\n(e.g. prompt shield, content safety)"
  node suppress "Mode = abort / mask / log\n(src/elspeth/plugins/llms/middleware.py:110,232)"
  node log "Structured Log Event\n(channel specific)"
  node artifacts "Mark Failure in Payload\n(src/elspeth/core/experiments/runner.py:177)"
  node notify "Middleware Hooks\nretry exhausted / on_experiment_complete"
  node signed "Signed Manifest / Dry-run Payload"
  node analyst "Security Analyst Review"

  detect -> suppress "apply configured response"
  suppress -> log "warning/error with metadata"
  log -> artifacts "record failure detail"
  artifacts -> notify "middleware callbacks"
  notify -> signed "artifact metadata includes failure sample"
  log -> analyst "forward to SIEM"
  signed -> analyst "review signed bundle / dry-run output"
```

- Violations originate in middleware (prompt shield, Azure Content Safety) or in validation plugins; behaviour depends on `on_violation` or `on_error` configuration (`config/sample_suite/prompt_shield_demo/config.json:8`, `src/elspeth/plugins/llms/middleware.py:226`).
- Failures become part of the runner payload, propagated to signed manifests and repository dry-runs for later investigation (`src/elspeth/core/experiments/runner.py:162`, `src/elspeth/plugins/outputs/signed.py:59`, `src/elspeth/plugins/outputs/repository.py:57`).
