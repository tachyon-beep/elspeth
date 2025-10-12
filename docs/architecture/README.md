# Architecture Guide

Elspeth’s architecture documentation is split into focused topics so you can move from high-level diagrams to implementation details quickly. Start here and jump to the documents that match your role or question.

## 1. Orientation

- [`architecture-overview.md`](architecture-overview.md) – Core principles, component layering, and security posture highlights.
- [`component-diagram.md`](component-diagram.md) – Logical component breakdown and responsibilities.
- [`data-flow-diagrams.md`](data-flow-diagrams.md) – Detailed data paths from ingestion to sink emission.
- [`suite-lifecycle.md`](suite-lifecycle.md) – How suite execution stages interact with plugins, middleware, and artefact pipelines.

## 2. Configuration & Extensibility

- [`configuration-merge.md`](configuration-merge.md) – How profiles, prompt packs, and suite defaults merge.
- [`plugin-catalogue.md`](plugin-catalogue.md) – Current datasource, LLM, middleware, metric, baseline, and sink options.
- [`plugin-security-model.md`](plugin-security-model.md) – How security levels, registries, and controls interact when instantiating plugins.
- [`configuration-security.md`](configuration-security.md) – Validation rules and guardrails for runtime configuration.

## 3. Security & Compliance

- [`security-controls.md`](security-controls.md) – Control objectives mapped to Elspeth features.
- [`threat-surfaces.md`](threat-surfaces.md) & [`threat-traceability.md`](threat-traceability.md) – Threat modelling artefacts and mitigations.
- [`audit-logging.md`](audit-logging.md) – Expectations for audit events across datasources, LLM clients, and sinks.
- [`environment-hardening.md`](environment-hardening.md) – Deployment and runtime hardening guidance.
- [`incident-response.md`](incident-response.md) – Roles, runbooks, and notification paths for incidents.

## 4. Operations & Maintenance

- [`dependency-analysis.md`](dependency-analysis.md) – Third-party dependencies, supply-chain controls, and monitoring strategy.
- [`upgrade-strategy.md`](upgrade-strategy.md) – Versioning guarantees, migration paths, and deprecation process.
- [`testing-overview.md`](testing-overview.md) – Test coverage strategy, tooling, and quality gates.
- [`accreditation-run-example.md`](accreditation-run-example.md) – Example end-to-end run aligned with accreditation evidence.

## 5. Controls Inventory

- [`CONTROL_INVENTORY.md`](CONTROL_INVENTORY.md) – Comprehensive list of controls, owners, and verification hints.

---

Looking for business-level guidance or release process notes? Head back to [`docs/README.md`](../README.md) for the broader documentation index.
