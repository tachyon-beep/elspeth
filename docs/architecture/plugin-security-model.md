# Plugin Security Model

## Registry Architecture
- **Central factories** – Datasource, LLM, and sink registries wrap constructors with JSON-schema validation, rejecting unknown plugin names or malformed options before instantiation (`src/elspeth/core/registry.py:91`, `src/elspeth/core/registry.py:208`).
- **Experiment plugins** – Row, aggregation, baseline, validation, and early-stop plugins register via dedicated registries that normalise definitions and check option schemas (`src/elspeth/core/experiments/plugin_registry.py:93`, `src/elspeth/core/experiments/plugin_registry.py:227`).
- **Control plane plugins** – Rate limiter and cost tracker factories follow the same pattern, providing a consistent extension point for throttle/cost logic while retaining validation hooks (`src/elspeth/core/controls/registry.py:36`, `src/elspeth/core/controls/registry.py:102`).

## Isolation & Error Handling
- **Try/except guards** – Early-stop plugins are wrapped so unexpected exceptions log and continue rather than crashing the run, isolating custom logic from the core orchestrator (`src/elspeth/core/experiments/runner.py:260`).
- **Middleware order** – LLM middleware definitions are validated, cached, and shared across experiments to avoid duplicate instantiation and to enforce consistent sequencing (`src/elspeth/core/llm/registry.py:46`, `src/elspeth/core/experiments/suite_runner.py:158`).
- **Retry metadata** – Exceptions from LLM clients are annotated with retry history, enabling middleware hooks (e.g., telemetry) to observe failures without mutating the runner (`src/elspeth/core/experiments/runner.py:565`, `src/elspeth/core/experiments/runner.py:575`).

## Artifact Governance
- **Produced/consumed declarations** – Sinks advertise the artifacts they produce and consume, allowing the pipeline to topologically sort execution and prevent improper dependencies (`src/elspeth/core/artifact_pipeline.py:153`, `src/elspeth/core/artifact_pipeline.py:201`).
- **Security classification** – Each binding inherits a security level; the pipeline denies access when a consumer lacks sufficient clearance, preventing cross-domain lateral movement (`src/elspeth/core/artifact_pipeline.py:192`).
- **Sanitisation metadata** – Sinks may augment produced artifacts with sanitisation details or manifest digests, enabling downstream plugins to reason about provenance (`src/elspeth/plugins/outputs/csv_file.py:106`, `src/elspeth/plugins/outputs/excel.py:187`).

## Extensibility Controls
- **Side-effect imports** – Default plugin packages register themselves on import, but alternative registries can be loaded explicitly to constrain available plugins in hardened deployments (`src/elspeth/plugins/experiments/__init__.py:5`, `src/elspeth/plugins/llms/__init__.py:1`).
- **Custom plugin onboarding** – Helper scripts scaffold new plugin skeletons while registries enforce schema validation, reducing the risk of insecure copy/paste code (`scripts/plugin_scaffold.py:19`).
- **Future hardening** – Consider introducing signed plugin manifests or runtime capability lists (e.g., network, filesystem) to limit the blast radius of third-party plugins.
