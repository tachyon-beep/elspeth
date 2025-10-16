# Traceability Matrix

| Component | File Path | Documentation Reference | Last Verified |
|-----------|-----------|------------------------|---------------|
| Orchestrator Core | src/elspeth/core/orchestrator.py | docs/architecture/architecture-overview.md (Update 2025-10-12: Orchestrator Core), docs/architecture/component-diagram.md (Update 2025-10-12: Orchestrator Core) | 2025-10-12 |
| Experiment Runner | src/elspeth/core/experiments/runner.py | docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Runner Pipeline), docs/migration-guide.md (Added 2025-10-12 – Concurrency & Early-stop Parity Checklist) | 2025-10-12 |
| Artifact Pipeline | src/elspeth/core/pipeline/artifact_pipeline.py | docs/architecture/security-controls.md (Update 2025-10-12: Artifact Clearance), docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Pipeline) | 2025-10-12 |
| Analytics Report Sink | src/elspeth/plugins/outputs/analytics_report.py | docs/architecture/architecture-overview.md (Update 2025-10-12: Early Stop and Baseline Analytics), docs/reporting-and-suite-management.md (Section 2) | 2025-10-12 |
| Visual Analytics Sink | src/elspeth/plugins/outputs/visual_report.py | docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation), docs/examples/colour-animals.md | 2025-10-12 |
| Azure Environment Middleware | src/elspeth/plugins/llms/middleware_azure.py | docs/architecture/audit-logging.md (Update 2025-10-12: Azure Telemetry), docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards) | 2025-10-12 |
| Configuration Loader | src/elspeth/config.py | docs/architecture/configuration-security.md (Update 2025-10-12: Loader Safeguards), docs/architecture/architecture-overview.md (Configuration Loader bullet) | 2025-10-12 |
| Plugin Registry | src/elspeth/core/experiments/plugin_registry.py | docs/architecture/plugin-security-model.md (Update 2025-10-12: Registry Enforcement), docs/architecture/component-diagram.md (Plugin registries section) | 2025-10-12 |
| Dependency Extras | pyproject.toml (optional-dependencies) | docs/architecture/dependency-analysis.md (Optional Extras), README.md (Optional extras list) | 2025-10-12 |
| Release Process | N/A (process) | docs/release-checklist.md, docs/DOCUMENTATION_AUDIT_2025-10-12.md | 2025-10-12 |
