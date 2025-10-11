# Plugin Security Model

## Registry Architecture
- **Central factories** – Datasource, LLM, and sink registries wrap constructors with JSON-schema validation, rejecting unknown plugin names or malformed options before instantiation (`src/elspeth/core/registry.py:91`, `src/elspeth/core/registry.py:208`).[^plugin-central-2025-10-12]
- **Experiment plugins** – Row, aggregation, baseline, validation, and early-stop plugins register via dedicated registries that normalise definitions and check option schemas (`src/elspeth/core/experiments/plugin_registry.py:93`, `src/elspeth/core/experiments/plugin_registry.py:227`).[^plugin-experiment-2025-10-12]
- **Control plane plugins** – Rate limiter and cost tracker factories follow the same pattern, providing a consistent extension point for throttle/cost logic while retaining validation hooks (`src/elspeth/core/controls/registry.py:36`, `src/elspeth/core/controls/registry.py:102`).[^plugin-control-2025-10-12]
<!-- Update 2025-10-12: Registry creation paths also stamp `_elspeth_security_level` on plugins, ensuring artifact pipeline enforcement downstream (`src/elspeth/core/experiments/plugin_registry.py:122`, `src/elspeth/core/registry.py:120`). -->

### Update 2025-10-12: Registry Enforcement
- Registries attach `_elspeth_security_level` attributes and validate schemas before plugin instantiation, aligning with artifact clearance checks.

### Update 2025-10-12: Validation Plugins
- Validation plugins (regex/JSON/LLM guard) must declare schemas and security levels, ensuring untrusted responses are filtered consistently (`src/elspeth/plugins/experiments/validation.py:20`, `src/elspeth/core/experiments/plugin_registry.py:227`).

### Update 2025-10-12: Control Registry
- Rate limiter and cost tracker registries validate options and security levels before binding to the runner (`src/elspeth/core/controls/registry.py:36`, `src/elspeth/core/controls/registry.py:102`).

## Isolation & Error Handling
- **Try/except guards** – Early-stop plugins are wrapped so unexpected exceptions log and continue rather than crashing the run, isolating custom logic from the core orchestrator (`src/elspeth/core/experiments/runner.py:260`).[^plugin-try-2025-10-12]
- **Middleware order** – LLM middleware definitions are validated, cached, and shared across experiments to avoid duplicate instantiation and to enforce consistent sequencing (`src/elspeth/core/llm/registry.py:46`, `src/elspeth/core/experiments/suite_runner.py:158`).[^plugin-middleware-2025-10-12]
- **Retry metadata** – Exceptions from LLM clients are annotated with retry history, enabling middleware hooks (e.g., telemetry) to observe failures without mutating the runner (`src/elspeth/core/experiments/runner.py:565`, `src/elspeth/core/experiments/runner.py:575`).[^plugin-retry-meta-2025-10-12]

### Update 2025-10-12: Early-Stop Lifecycle
- Early-stop plugins expose `reset` and `check` hooks and are normalised prior to execution, preventing configuration drift (`src/elspeth/plugins/experiments/early_stop.py:17`, `src/elspeth/core/experiments/runner.py:223`).

## Artifact Governance
- **Produced/consumed declarations** – Sinks advertise the artifacts they produce and consume, allowing the pipeline to topologically sort execution and prevent improper dependencies (`src/elspeth/core/artifact_pipeline.py:153`, `src/elspeth/core/artifact_pipeline.py:201`).[^plugin-produced-2025-10-12]
- **Security classification** – Each binding inherits a security level; the pipeline denies access when a consumer lacks sufficient clearance, preventing cross-domain lateral movement (`src/elspeth/core/artifact_pipeline.py:192`).[^plugin-security-2025-10-12]
- **Sanitisation metadata** – Sinks may augment produced artifacts with sanitisation details or manifest digests, enabling downstream plugins to reason about provenance (`src/elspeth/plugins/outputs/csv_file.py:106`, `src/elspeth/plugins/outputs/excel.py:187`).[^plugin-sanitisation-2025-10-12]

### Update 2025-10-12: Artifact Tokens
- Sink descriptors map produced artifacts to types and aliases, enabling secure dependency resolution across the pipeline (`src/elspeth/core/interfaces.py:83`, `src/elspeth/core/artifact_pipeline.py:167`).

## Extensibility Controls
- **Side-effect imports** – Default plugin packages register themselves on import, but alternative registries can be loaded explicitly to constrain available plugins in hardened deployments (`src/elspeth/plugins/experiments/__init__.py:5`, `src/elspeth/plugins/llms/__init__.py:1`).[^plugin-side-effect-2025-10-12]
- **Custom plugin onboarding** – Helper scripts scaffold new plugin skeletons while registries enforce schema validation, reducing the risk of insecure copy/paste code (`scripts/plugin_scaffold.py:19`).[^plugin-onboarding-2025-10-12]
- **Future hardening** – Consider introducing signed plugin manifests or runtime capability lists (e.g., network, filesystem) to limit the blast radius of third-party plugins.[^plugin-future-2025-10-12]

### Update 2025-10-12: Plugin Lifecycle
- Harden deployments by sealing plugin registries and auditing prompt packs for unexpected plugin references before accreditation runs.

## Added 2025-10-12 – Lifecycle Hooks & Shared Middleware
- **Middleware lifecycle** – Shared middleware instances receive suite lifecycle callbacks (`on_suite_loaded`, `on_experiment_start`, `on_experiment_complete`, `on_retry_exhausted`), centralising telemetry while avoiding per-run duplication (`src/elspeth/core/experiments/suite_runner.py:177`, `src/elspeth/plugins/llms/middleware_azure.py:180`).[^plugin-middleware-lifecycle-2025-10-12]
- **Plugin normalisation** – Early-stop, baseline, and concurrency-aware plugins are normalised through helper functions such as `normalize_early_stop_definitions`, guaranteeing consistent option shapes regardless of legacy shorthand (`src/elspeth/core/experiments/plugin_registry.py:282`, `src/elspeth/config.py:66`).[^plugin-normalisation-2025-10-12]
- **Artifact-aware sinks** – The registry records sink artifact descriptors and binds security levels, enabling downstream pipeline enforcement without granting sinks arbitrary filesystem access (`src/elspeth/core/registry.py:120`, `src/elspeth/core/artifact_pipeline.py:153`).[^plugin-artifact-aware-2025-10-12]

## Update History
- 2025-10-12 – Documented middleware lifecycle hooks, plugin normalisation safeguards, and artifact-aware sink enforcement within the security model.
- 2025-10-12 – Update 2025-10-12: Added registry/control registry notes, validation plugin coverage, and plugin lifecycle guidance with cross-references.

[^plugin-central-2025-10-12]: Update 2025-10-12: Registry architecture connects to docs/architecture/architecture-overview.md Component Layers.
[^plugin-experiment-2025-10-12]: Update 2025-10-12: Experiment plugin lifecycle visualised in docs/architecture/component-diagram.md (Update 2025-10-12: Plugin Registry).
[^plugin-control-2025-10-12]: Update 2025-10-12: Control registry enforcement referenced in docs/architecture/security-controls.md (Update 2025-10-12: Rate Limiting & Cost Controls).
[^plugin-try-2025-10-12]: Update 2025-10-12: Early-stop isolation linked to docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Early-Stop Lifecycle).
[^plugin-middleware-2025-10-12]: Update 2025-10-12: Middleware ordering shared with docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards).
[^plugin-retry-meta-2025-10-12]: Update 2025-10-12: Retry metadata feeds docs/architecture/audit-logging.md.
[^plugin-produced-2025-10-12]: Update 2025-10-12: Produced/consumed descriptors appear in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Tokens).
[^plugin-security-2025-10-12]: Update 2025-10-12: Security classification ties to docs/architecture/security-controls.md (Update 2025-10-12: Artifact Clearance).
[^plugin-sanitisation-2025-10-12]: Update 2025-10-12: Sanitisation provenance links to docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation).
[^plugin-side-effect-2025-10-12]: Update 2025-10-12: Side-effect imports cautioned in docs/architecture/threat-surfaces.md (Update 2025-10-12: Plugin Catalogue).
[^plugin-onboarding-2025-10-12]: Update 2025-10-12: Plugin onboarding script referenced in docs/architecture/threat-surfaces.md (Update 2025-10-12: Plugin Catalogue).
[^plugin-future-2025-10-12]: Update 2025-10-12: Future hardening recommendations align with docs/architecture/security-controls.md.
[^plugin-middleware-lifecycle-2025-10-12]: Update 2025-10-12: Middleware lifecycle callbacks documented in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Baseline Evaluation).
[^plugin-normalisation-2025-10-12]: Update 2025-10-12: Normalisation helpers cross-referenced in docs/architecture/configuration-security.md (Update 2025-10-12: Suite Defaults).
[^plugin-artifact-aware-2025-10-12]: Update 2025-10-12: Artifact-aware sink enforcement linked to docs/architecture/security-controls.md (Update 2025-10-12: Artifact Tokens).
