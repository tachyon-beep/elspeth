# Traceability Matrix

| Component | File Path | Documentation Reference | Last Verified |
|-----------|-----------|-------------------------|---------------|
| ExperimentOrchestrator | `src/elspeth/core/orchestrator.py:22-144` | docs/architecture/architecture-overview.md (Component Layers) | 2025-10-12 |
| ExperimentRunner | `src/elspeth/core/experiments/runner.py:52-709` | docs/architecture/data-flow-diagrams.md (Runner Pipeline) | 2025-10-12 |
| ArtifactPipeline | `src/elspeth/core/pipeline/artifact_pipeline.py:147-219` | docs/architecture/component-diagram.md (Artifact Pipeline) | 2025-10-12 |
| SuiteReportGenerator | `src/elspeth/tools/reporting.py:18-199` | docs/reporting-and-suite-management.md (Section 2) | 2025-10-12 |
| Configuration Loader | `src/elspeth/config.py:52-210` | docs/architecture/configuration-security.md (Validation Pipeline) | 2025-10-12 |
| AzureEnvironmentMiddleware | `src/elspeth/plugins/nodes/transforms/llm/middleware_azure.py:180-259` | docs/architecture/audit-logging.md (Azure Telemetry) | 2025-10-12 |
| PromptShieldMiddleware | `src/elspeth/plugins/nodes/transforms/llm/middleware.py:157-186` | docs/architecture/security-controls.md (Middleware Safeguards) | 2025-10-12 |
| AdaptiveRateLimiter | `src/elspeth/core/controls/rate_limit.py:104-150` | docs/architecture/security-controls.md (Rate Limiting & Cost Controls) | 2025-10-12 |
| FixedPriceCostTracker | `src/elspeth/core/controls/cost_tracker.py:36-96` | docs/architecture/audit-logging.md (Cost Reporting) | 2025-10-12 |
| AnalyticsReportSink | `src/elspeth/plugins/nodes/sinks/analytics_report.py:16-133` | docs/architecture/architecture-overview.md (Added 2025-10-12 – Early Stop and Baseline Analytics) | 2025-10-12 |
| VisualAnalyticsSink | `src/elspeth/plugins/nodes/sinks/visual_report.py:17-199` | docs/architecture/architecture-overview.md (Added 2025-10-12 – Early Stop and Baseline Analytics) | 2025-10-12 |
| SignedArtifactSink | `src/elspeth/plugins/nodes/sinks/signed.py:1-132` | docs/architecture/security-controls.md (Artifact Signing) | 2025-10-12 |
| EarlyStopPlugins | `src/elspeth/plugins/experiments/early_stop.py:7-118` | docs/architecture/plugin-security-model.md (Early-Stop Lifecycle) | 2025-10-12 |
| BlobDatasource/Sink | `src/elspeth/plugins/nodes/sources/blob.py`, `src/elspeth/plugins/nodes/sinks/blob.py` | docs/architecture/threat-surfaces.md (Storage Interfaces) | 2025-10-12 |

# Update History
- 2025-10-12 – Initial matrix created to map core components to updated documentation set.

