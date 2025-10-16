# Security Control Inventory

| Control ID | Description | Implementation | Test Coverage | Doc Reference |
|------------|-------------|----------------|---------------|---------------|
| SEC-001 | Spreadsheet formula sanitisation prevents CSV/Excel injection | `src/elspeth/plugins/nodes/sinks/_sanitize.py:7-92`, `csv_file.py:18-123`, `excel.py:33-182` | `tests/test_outputs_csv.py`, `tests/test_outputs_excel.py` | docs/architecture/security-controls.md (Output Sanitisation) |
| SEC-002 | Prompt shield blocks/ masks banned phrases before LLM invocation | `src/elspeth/plugins/nodes/transforms/llm/middleware.py:157-186` | `tests/test_llm_middleware.py` | docs/architecture/security-controls.md (Middleware Safeguards) |
| SEC-003 | Azure Content Safety screening enforces severity thresholds | `src/elspeth/plugins/nodes/transforms/llm/middleware.py:257-320` | `tests/test_llm_middleware.py` | docs/architecture/security-controls.md (Middleware Safeguards) |
| SEC-004 | Retry exhaustion logging emits attempt history for SOC alerting | `src/elspeth/core/experiments/runner.py:657-678`, `middleware_azure.py:233-259` | `tests/test_llm_middleware.py`, `tests/test_outputs_analytics_report.py` | docs/architecture/audit-logging.md (Retry Exhaustion Events) |
| SEC-005 | Artifact clearance prevents sinks from consuming higher classified data | `src/elspeth/core/pipeline/artifact_pipeline.py:150-205` | `tests/test_security_level_enforcement.py`, `tests/test_sink_chaining.py` | docs/architecture/security-controls.md (Artifact Clearance) |
| SEC-006 | Signed bundles embed digests, signatures, and run metadata | `src/elspeth/plugins/nodes/sinks/signed.py:32-121`, `src/elspeth/core/security/signing.py:17-64` | `tests/test_security_signing.py` | docs/architecture/security-controls.md (Artifact Signing) |
| SEC-007 | Suite validation enforces experiment/sink presence before execution | `src/elspeth/core/validation/validators.py:430-512`, `src/elspeth/core/experiments/suite_runner.py:295-382` | `tests/test_suite_runner_integration.py`, `tests/test_config_suite.py` | docs/architecture/configuration-security.md (Suite Export & Governance) |
| SEC-008 | Adaptive rate limiter guards request/token quotas and exposes utilisation | `src/elspeth/core/controls/rate_limit.py:104-150` | `tests/test_controls.py`, `tests/test_controls_registry.py` | docs/architecture/security-controls.md (Rate Limiting & Cost Controls) |
| SEC-009 | Cost tracker records token usage and aggregates totals for audit sinks | `src/elspeth/core/controls/cost_tracker.py:36-96`, `src/elspeth/core/experiments/runner.py:198-214` | `tests/test_controls.py`, `tests/test_outputs_analytics_report.py` | docs/architecture/audit-logging.md (Cost Reporting) |
| SEC-010 | Early-stop plugins halt execution when metrics exceed thresholds | `src/elspeth/plugins/experiments/early_stop.py:17-112`, `src/elspeth/core/experiments/runner.py:218-257` | `tests/test_experiment_metrics_plugins.py`, `tests/test_experiment_runner_integration.py` | docs/architecture/plugin-security-model.md (Early-Stop Lifecycle) |

## Update History

- 2025-10-12 – Initial control inventory derived from current security controls, telemetry hooks, and accreditation requirements.

