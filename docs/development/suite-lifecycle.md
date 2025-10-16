# Suite Lifecycle State Machine

```penguin
diagram "Experiment Suite Lifecycle" {
  direction: right

  state "Load Settings" as load {
    entry "validate profile\n(src/elspeth/core/validation/validators.py:271)"
  }
  state "Load Suite" as suite {
    entry "ExperimentSuite.load\n(src/elspeth/core/experiments/config.py:118)"
  }
  state "Preflight" as preflight {
    entry "validate_suite\n(src/elspeth/core/validation/validators.py:407)"
  }
  state "Experiment Loop" as loop
  state "Baseline Compare" as compare
  state "Suite Complete" as complete {
    entry "middleware.on_suite_complete\n(src/elspeth/plugins/llms/middleware_azure.py:250)"
  }
  state "Artifacts Finalised" as artifacts {
    entry "ArtifactPipeline.execute\n(src/elspeth/core/pipeline/artifact_pipeline.py:201)"
  }

  [*] --> load
  load --> suite
  suite --> preflight
  preflight --> loop : suite_valid
  preflight --> [*] : errors_found

  loop --> compare : each experiment payload
  compare --> loop : more variants
  loop --> artifacts : sinks executed
  artifacts --> complete
  complete --> [*]
}
```

- **Load** – settings and plugins are validated before any experiments run (`src/elspeth/core/validation/validators.py:271`).
- **Preflight** – suite-level checks ensure baselines, prompts, and sinks are consistent (`src/elspeth/core/validation/validators.py:471`).
- **Loop** – each experiment is executed, middleware notified, and artifacts produced; baseline comparisons are attached when available (`src/elspeth/core/experiments/suite_runner.py:166`, `src/elspeth/core/experiments/suite_runner.py:208`).
