# Component Traceability Matrix

| Component | File Path | Documentation Reference | Last Verified |
|-----------|-----------|------------------------|---------------|
| Orchestrator | `src/elspeth/core/orchestrator.py` | `docs/architecture/architecture-overview.md` §Component Layers | 2025-10-12 |
| Experiment Runner | `src/elspeth/core/experiments/runner.py` | `docs/architecture/architecture-overview.md` (Added 2025-10-12), `docs/architecture/data-flow-diagrams.md` | 2025-10-12 |
| Suite Runner | `src/elspeth/core/experiments/suite_runner.py` | `docs/architecture/architecture-overview.md` (Suite governance), `docs/architecture/audit-logging.md` | 2025-10-12 |
| Artifact Pipeline | `src/elspeth/core/artifact_pipeline.py` | `docs/architecture/architecture-overview.md` (Artifact Pipeline), `docs/architecture/security-controls.md` | 2025-10-12 |
| Analytics Report Sink | `src/elspeth/plugins/outputs/analytics_report.py` | `docs/architecture/architecture-overview.md` (Added 2025-10-12), `docs/architecture/audit-logging.md` | 2025-10-12 |
| Visual Analytics Sink | `src/elspeth/plugins/outputs/visual_report.py` | `docs/architecture/architecture-overview.md` (Added 2025-10-12), `docs/reporting-and-suite-management.md` | 2025-10-12 |
| Azure Environment Middleware | `src/elspeth/plugins/llms/middleware_azure.py` | `docs/architecture/audit-logging.md`, `docs/architecture/security-controls.md` | 2025-10-12 |
| Static Test LLM | `src/elspeth/plugins/llms/static.py` | `README.md` (§Plugins), `docs/migration-guide.md` (Testing/fixtures) | 2025-10-12 |
| Prompt Shield Middleware | `src/elspeth/plugins/llms/middleware.py` | `docs/architecture/security-controls.md` §Middleware Security Features | 2025-10-12 |
| Adaptive Rate Limiter | `src/elspeth/core/controls/rate_limit.py` | `docs/architecture/security-controls.md` §Rate Limiting & Cost Controls | 2025-10-12 |
| Early Stop Plugin | `src/elspeth/plugins/experiments/early_stop.py` | `docs/architecture/architecture-overview.md` (Added 2025-10-12), `docs/architecture/security-controls.md` | 2025-10-12 |
| Validation Engine | `src/elspeth/core/validation.py`, `src/elspeth/core/config_schema.py` | `docs/architecture/configuration-security.md`, `notes/schema-validation-plan.md` | 2025-10-12 |
| CLI Orchestration | `src/elspeth/cli.py` | `docs/reporting-and-suite-management.md`, `README.md` Quick Start | 2025-10-12 |
| Suite Reporting Generator | `src/elspeth/tools/reporting.py` | `docs/reporting-and-suite-management.md`, `docs/architecture/architecture-overview.md` (Analytics) | 2025-10-12 |
