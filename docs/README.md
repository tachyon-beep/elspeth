# Elspeth Documentation Index

This directory captures the operational guides, architecture references, and compliance evidence that back the Elspeth orchestrator. Use this index to jump to the resource you need.

## Operations & How-To

- [`reporting-and-suite-management.md`](reporting-and-suite-management.md) – Running suites, generating artefacts, and managing reports.
- [`end_to_end_scenarios.md`](end_to_end_scenarios.md) – Guided walkthroughs that stitch configuration, orchestration, and analytics together.
- [`examples_colour_animals.md`](examples_colour_animals.md) – A lightweight sample scenario useful for workshops and quick smoke tests.
- [`logging-standards.md`](logging-standards.md) – Expectations for structured logging, audit trails, and telemetry integration.
- [`migration-guide.md`](migration-guide.md) – Steps for upgrading Elspeth deployments between releases.
- [`release-checklist.md`](release-checklist.md) – Tasks required before tagging a release, from artefact regeneration to documentation updates.

## Architecture & Security

Architecture references now live under [`docs/architecture/`](architecture/). Start with [`architecture/README.md`](architecture/README.md) for a curated overview, then dive deeper into data flows, plugin registries, and security controls as needed.

Security-focused documents include:

- [`architecture/security-controls.md`](architecture/security-controls.md) – Control inventory mapped to platform capabilities.
- [`architecture/threat-surfaces.md`](architecture/threat-surfaces.md) – Identified attack surfaces and mitigation notes.
- [`architecture/threat-traceability.md`](architecture/threat-traceability.md) – Links from threats to implemented controls.
- [`architecture/incident-response.md`](architecture/incident-response.md) – Response plan and runbook expectations.
- [`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md) – Requirement-to-test traceability for accreditation.

## Compliance & Accreditation Artefacts

- [`architecture/CONTROL_INVENTORY.md`](architecture/CONTROL_INVENTORY.md) – Control IDs, owners, and verification activities.
- [`architecture/accreditation-run-example.md`](architecture/accreditation-run-example.md) – End-to-end example aligned with accreditation evidence requirements.
- [`architecture/environment-hardening.md`](architecture/environment-hardening.md) – Baseline hardening guidance for deployment environments.

## Testing & Quality

- [`architecture/testing-overview.md`](architecture/testing-overview.md) – Test strategy, coverage targets, and tooling.
- [`architecture/dependency-analysis.md`](architecture/dependency-analysis.md) – Supply-chain overview and monitoring approach.
- [`architecture/upgrade-strategy.md`](architecture/upgrade-strategy.md) – Versioning, backward compatibility, and deprecation policy.

## Need Something Else?

Additional notes, decisions, and design explorations live under `docs/notes/`. See `AGENTS.md` at the repository root for details on automation agents involved in documentation upkeep.

If you notice gaps or outdated sections, open an issue or submit a pull request—community improvements to the docs are always welcome.
