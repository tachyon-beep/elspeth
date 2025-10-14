# Configuration & Secrets Management

## Configuration Entry Points
- **Profile settings** – Primary runtime definitions live in `settings.yaml`, declaring datasource/LLM/sink plugins, prompt packs, and suite defaults (`config/settings.yaml:3`, `config/settings.yaml:76`).[^config-profile-2025-10-12]
- **Prompt packs** – Reusable prompt bundles include row/aggregate plugins and middleware defaults, enabling centralised policy updates across suites (`config/settings.yaml:4`, `src/elspeth/config.py:78`).[^config-prompt-pack-2025-10-12]
- **Suite overrides** – Individual experiments provide JSON configs with per-experiment sinks, middleware, rate limiters, and early-stop definitions (`config/sample_suite/slow_rate_limit_demo/config.json:13`, `src/elspeth/core/experiments/config.py:82`).[^config-suite-overrides-2025-10-12]
<!-- Update 2025-10-12: Profiles also expose `concurrency`, `early_stop`, and `checkpoint` sections that are normalised via `normalize_early_stop_definitions` to align with plugin schemas (`src/elspeth/config.py:66`, `src/elspeth/core/experiments/plugin_registry.py:298`). -->

### Update 2025-10-12: Loader Safeguards
- `load_settings` merges prompt packs, early-stop definitions, and concurrency defaults while preserving security levels (`src/elspeth/config.py:52`, `src/elspeth/config.py:146`).[^config-loader-safeguards-2025-10-12]
- Early-stop configuration passed as shorthand objects or legacy keys is normalised into canonical plugin definitions, preventing ambiguous threshold semantics (`src/elspeth/config.py:68`, `src/elspeth/core/experiments/plugin_registry.py:298`).[^config-early-stop-normalised-2025-10-12]

## Secret Resolution
- **Environment variables** – LLM clients, repository sinks, and signing bundles resolve credentials via `_env` keys or well-known variables, keeping secrets out of config artefacts (`src/elspeth/plugins/llms/azure_openai.py:66`, `src/elspeth/plugins/outputs/repository.py:149`, `src/elspeth/plugins/outputs/signed.py:107`).[^config-env-2025-10-12]
- **Azure identity** – Blob datasources fall back to `DefaultAzureCredential` when SAS tokens are absent, supporting managed identity deployments without patching configuration (`src/elspeth/datasources/blob_store.py:125`, `src/elspeth/datasources/blob_store.py:157`).[^config-azure-2025-10-12]
- **Sample artefacts** – Repository includes illustrative SAS tokens; accreditation deployments must replace these with tenant-specific secure stores and treat checked-in values as non-production (`config/blob_store.yaml:4`).[^config-sample-2025-10-12]

### Update 2025-10-12: Secret Management
- Prefer workload identities for infrastructure-deployed runs; local development should inject `.env` files ignored by version control.

## Validation & Fail-fast Behaviour
- **Schema enforcement** – Loader passes raw configuration through schema validators before instantiating plugins, catching typoed plugin names or missing options early (`src/elspeth/core/validation.py:271`, `src/elspeth/core/registry.py:98`, `src/elspeth/core/controls/registry.py:36`).[^config-schema-2025-10-12]
- **Early-stop normalisation** – User-friendly structures are converted into canonical plugin definitions, reducing ambiguity around threshold plugins (`src/elspeth/core/experiments/plugin_registry.py:298`, `src/elspeth/config.py:69`).[^config-early-stop-2025-10-12]
- **Suite audits** – `validate_suite` collects experiment metadata, checks for duplicate names/baselines, and surfaces aggregate risk estimations before orchestration begins (`src/elspeth/core/validation.py:407`, `src/elspeth/core/experiments/suite_runner.py:74`).[^config-suite-audits-2025-10-12]

### Update 2025-10-12: Suite Defaults
- Suite defaults merge prompt packs, middleware, and sink definitions with per-experiment overrides, ensuring accreditation profiles stay consistent (`src/elspeth/core/experiments/suite_runner.py:55`, `src/elspeth/core/experiments/suite_runner.py:118`).

## Runtime Configuration Controls
- **Dry-run toggles** – Repository sinks respect `dry_run`, allowing accreditation teams to inspect payloads without mutating upstream repositories (`config/settings.yaml:64`, `src/elspeth/plugins/outputs/repository.py:70`).[^config-dry-run-2025-10-12]
- **On-error policies** – Datasources and sinks accept `"abort"` or `"skip"` to tailor resilience vs. strictness; combine with telemetry to ensure skipped components are investigated (`src/elspeth/plugins/datasources/csv_local.py:30`, `src/elspeth/plugins/outputs/blob.py:64`, `src/elspeth/plugins/outputs/excel.py:52`).[^config-on-error-2025-10-12]
- **Security levels** – Datasources, sinks, and suite defaults can specify classifications that propagate through the artifact pipeline, enabling downstream segregation of outputs (`src/elspeth/plugins/datasources/csv_blob.py:25`, `src/elspeth/core/experiments/suite_runner.py:116`, `src/elspeth/core/artifact_pipeline.py:192`).[^config-security-levels-2025-10-12]
<!-- Update 2025-10-12: `concurrency.enabled`, `max_workers`, and `utilization_pause` settings guard thread pools, while `checkpoint.path`/`field` control resumable runs; ensure these paths point to hardened storage (`src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/experiments/runner.py:280`). -->
- **Concurrency & checkpointing** – `concurrency` blocks configure thread pools and rate-limiter backoff, while `checkpoint` paths direct resumable execution to hardened storage locations (`src/elspeth/config.py:97`, `src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/experiments/runner.py:280`).[^config-concurrency-2025-10-12]
- **Suite defaults harmonisation** – Suite defaults merge prompt packs (including middleware/rate limiters) before experiments override them, ensuring accreditation-approved stacks remain in effect (`src/elspeth/core/experiments/suite_runner.py:55`, `src/elspeth/core/experiments/suite_runner.py:118`).[^config-suite-defaults-2025-10-12]

### Update 2025-10-12: Prompt Pack Governance
- Prompt packs should exclude development middleware and enforce accreditation-required stacks (prompt shield + content safety) by default.

## Recommendations
- Store operational secrets (API keys, SAS tokens, signing keys) in managed secret stores and inject them at runtime through environment variables or workload identities.[^config-rec-secrets-2025-10-12]
- Maintain a signed baseline of accreditation-approved configuration bundles; use the signed artifact sink to capture canonical run manifests (`src/elspeth/plugins/outputs/signed.py:48`).[^config-rec-signing-2025-10-12]
- Extend validation to enforce minimum middleware stacks (e.g., prompt shield + content safety) for high-assurance suites to avoid configuration drift.[^config-rec-middleware-2025-10-12]

## Added 2025-10-12 – Suite Management & Export Pathing
- **Suite exports** – CLI flags `--export-suite-config`, `--create-experiment-template`, and `--reports-dir` reuse hydrated settings to write artefacts under operator-defined paths; treat exported JSON/YAML and analytics reports as configuration evidence requiring signing or checksum capture (`src/elspeth/cli.py:161`, `src/elspeth/cli.py:201`, `src/elspeth/tools/reporting.py:33`).[^config-suite-exports-2025-10-12]
- **Prompt pack inheritance** – Prompt packs can override concurrency, middleware, sinks, and early-stop defaults; ensure packs shipped for production omit development-only plugins (`src/elspeth/config.py:92`, `src/elspeth/core/experiments/suite_runner.py:55`).[^config-prompt-inheritance-2025-10-12]
- **Plugin whitelisting** – Registries validate plugin names against in-memory maps. Harden builds by avoiding dynamic imports at runtime and auditing prompt packs/suite defaults for unexpected plugin references (`src/elspeth/core/registry.py:69`, `src/elspeth/core/experiments/plugin_registry.py:52`).[^config-plugin-whitelist-2025-10-12]

## Update History
- 2025-10-12 – Update 2025-10-12: Documented loader normalisation, concurrency/checkpoint controls, suite default harmonisation, and evidence export flows for accreditation-ready profiles.
- 2025-10-12 – Captured concurrency/checkpoint configuration impacts, suite export considerations, and plugin inheritance safeguards.
- 2025-10-12 – Update 2025-10-12: Added loader/secret governance notes, suite default annotations, and cross-references for prompt packs and exports.

[^config-profile-2025-10-12]: Update 2025-10-12: Profiles correspond to docs/architecture/architecture-overview.md Component Layers.
[^config-prompt-pack-2025-10-12]: Update 2025-10-12: Prompt pack behaviour tied to docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Defaults).
[^config-suite-overrides-2025-10-12]: Update 2025-10-12: Suite overrides mapped in docs/architecture/plugin-security-model.md.
[^config-env-2025-10-12]: Update 2025-10-12: Secret handling linked to docs/architecture/threat-surfaces.md (Update 2025-10-12: Storage Interfaces).
[^config-azure-2025-10-12]: Update 2025-10-12: Managed identity details referenced in docs/architecture/security-controls.md (Update 2025-10-12: Managed Identity).
[^config-sample-2025-10-12]: Update 2025-10-12: Sample artefact warnings reflected in docs/architecture/threat-surfaces.md (Update 2025-10-12: Secret Management).
[^config-schema-2025-10-12]: Update 2025-10-12: Schema enforcement discussed in docs/architecture/security-controls.md (Update 2025-10-12: Loader Safeguards).
[^config-early-stop-2025-10-12]: Update 2025-10-12: Early-stop normalisation ties to docs/architecture/plugin-security-model.md (Update 2025-10-12: Early-Stop Lifecycle).
[^config-suite-audits-2025-10-12]: Update 2025-10-12: Suite audits cross-referenced in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Lifecycle).
[^config-dry-run-2025-10-12]: Update 2025-10-12: Dry-run safeguards linked to docs/architecture/threat-surfaces.md (Update 2025-10-12: Repository Interfaces).
[^config-on-error-2025-10-12]: Update 2025-10-12: on_error implications covered in docs/architecture/migration-guide.md (Update 2025-10-12: on_error Behaviour).
[^config-security-levels-2025-10-12]: Update 2025-10-12: Security propagation detailed in docs/architecture/security-controls.md (Update 2025-10-12: Artifact Clearance).
[^config-rec-secrets-2025-10-12]: Update 2025-10-12: Secret storage recommendations align with docs/architecture/threat-surfaces.md.
[^config-rec-signing-2025-10-12]: Update 2025-10-12: Signed baseline guidance tied to docs/architecture/security-controls.md (Update 2025-10-12: Artifact Signing).
[^config-rec-middleware-2025-10-12]: Update 2025-10-12: Minimum middleware stack enforcement recommended in docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards).
[^config-suite-exports-2025-10-12]: Update 2025-10-12: Export paths compared in docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Export Tooling).
[^config-prompt-inheritance-2025-10-12]: Update 2025-10-12: Prompt pack inheritance diagrammed in docs/architecture/component-diagram.md (Update 2025-10-12: Configuration Loader).
[^config-plugin-whitelist-2025-10-12]: Update 2025-10-12: Plugin whitelisting guidance overlaps with docs/architecture/plugin-security-model.md (Update 2025-10-12: Registry Enforcement).
[^config-loader-safeguards-2025-10-12]: Update 2025-10-12: Loader safeguards corroborated by docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Lifecycle).
[^config-early-stop-normalised-2025-10-12]: Update 2025-10-12: Early-stop normalisation detailed in docs/architecture/plugin-security-model.md (Update 2025-10-12: Early-Stop Lifecycle).
[^config-concurrency-2025-10-12]: Update 2025-10-12: Concurrency and checkpoint guidance visualised in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Parallel Execution Gate / Checkpoint Loop).
[^config-suite-defaults-2025-10-12]: Update 2025-10-12: Suite defaults harmonisation aligned with docs/architecture/component-diagram.md (Update 2025-10-12: Suite reporting outputs).
