# Phase 2: Test Suite Reorganization Plan

**Objective**: Move 136 root-level test files into structured subdirectories WITHOUT merging files

**Estimated Effort**: 6-8 hours
**Prerequisites**: Phase 1 complete, stakeholder approval received
**Risk Level**: Medium (file moves can break imports, but git mv preserves history)

---

## Overview

Phase 2 executes the physical reorganization of test files from the flat root structure into the hierarchical structure designed in Phase 1. Files are moved **as-is** without consolidation (that happens in Phase 3).

### Key Principles

1. **Preserve history**: Use `git mv` exclusively (not `mv`)
2. **One concern per file**: Keep path_guard, errors, integration tests separate
3. **Verify continuously**: Run `pytest --collect-only` after each batch
4. **Commit frequently**: Batch moves by category, commit after each batch
5. **Import safety**: Update import paths immediately after moving

---

## Proposed Directory Structure

```
tests/
├── unit/                                    # Fast (<1s), isolated, no external I/O
│   ├── core/
│   │   ├── cli/                             # CLI utilities (not end-to-end)
│   │   │   ├── test_artifact_publish.py
│   │   │   └── test_job_config_parsing.py
│   │   ├── pipeline/
│   │   │   ├── test_artifact_pipeline.py
│   │   │   └── test_sink_chaining.py
│   │   ├── registries/
│   │   │   ├── test_base_registry.py
│   │   │   ├── test_plugin_helpers.py
│   │   │   └── test_context_utils.py
│   │   ├── security/
│   │   │   ├── test_signing_symmetric.py
│   │   │   ├── test_signing_asymmetric.py
│   │   │   ├── test_level_enforcement.py
│   │   │   └── test_path_guard_utils.py
│   │   └── validation/
│   │       ├── test_config_validation.py
│   │       ├── test_schema_validation.py
│   │       └── test_suite_validation.py
│   ├── plugins/
│   │   ├── nodes/
│   │   │   ├── sources/
│   │   │   │   ├── csv/
│   │   │   │   │   ├── test_load.py
│   │   │   │   │   └── test_security.py
│   │   │   │   └── blob/
│   │   │   │       ├── test_load.py
│   │   │   │       └── test_errors.py
│   │   │   ├── sinks/
│   │   │   │   ├── csv/
│   │   │   │   │   ├── test_write.py
│   │   │   │   │   ├── test_path_guard.py
│   │   │   │   │   └── test_errors.py
│   │   │   │   ├── excel/
│   │   │   │   │   ├── test_write.py
│   │   │   │   │   ├── test_path_guard.py
│   │   │   │   │   └── test_sanitization.py
│   │   │   │   ├── blob/
│   │   │   │   │   ├── test_write.py
│   │   │   │   │   └── test_errors.py
│   │   │   │   ├── signed/
│   │   │   │   │   ├── test_artifact_generation.py
│   │   │   │   │   └── test_signing.py
│   │   │   │   ├── bundles/
│   │   │   │   │   ├── test_local_bundle.py
│   │   │   │   │   ├── test_zip_bundle.py
│   │   │   │   │   └── test_reproducibility.py
│   │   │   │   ├── repository/
│   │   │   │   │   └── test_repository_sinks.py
│   │   │   │   ├── visual/
│   │   │   │   │   ├── test_base_visual.py
│   │   │   │   │   ├── test_visual_report.py
│   │   │   │   │   └── test_enhanced_visual.py
│   │   │   │   ├── analytics/
│   │   │   │   │   ├── test_analytics_report.py
│   │   │   │   │   └── test_errors.py
│   │   │   │   ├── embeddings/
│   │   │   │   │   └── test_embeddings_store.py
│   │   │   │   └── utilities/
│   │   │   │       ├── test_file_copy.py
│   │   │   │       └── test_sanitize_utils.py
│   │   │   └── transforms/
│   │   │       └── llm/
│   │   │           ├── test_azure_openai.py
│   │   │           ├── test_http_openai.py
│   │   │           ├── test_mock_llm.py
│   │   │           └── test_static_plugin.py
│   │   └── experiments/
│   │       ├── aggregators/
│   │       │   ├── test_cost_summary.py
│   │       │   ├── test_score_stats.py
│   │       │   └── test_metrics_plugins.py
│   │       ├── validators/
│   │       │   └── test_validation_plugins.py
│   │       ├── baselines/
│   │       │   ├── test_score_significance.py
│   │       │   ├── test_score_delta.py
│   │       │   └── test_assumptions_coverage.py
│   │       └── lifecycle/
│   │           ├── test_early_stop.py
│   │           └── test_prompt_variants.py
│   ├── utils/
│   │   ├── test_env_helpers.py
│   │   ├── test_sanitize_utils.py
│   │   └── test_scaffold.py
│   └── README.md                            # Unit test organization guide
├── integration/                             # Multi-component, may have I/O
│   ├── cli/
│   │   ├── test_suite_execution.py          # Was: test_cli_end_to_end.py
│   │   ├── test_dry_run.py
│   │   ├── test_strict_exit.py
│   │   ├── test_validate_schemas.py
│   │   ├── test_artifact_publish.py
│   │   ├── test_bundle_failure.py
│   │   └── test_yaml_json_edges.py
│   ├── suite_runner/
│   │   ├── test_characterization.py
│   │   ├── test_integration.py
│   │   ├── test_edge_cases.py
│   │   ├── test_baseline_flow.py
│   │   ├── test_middleware_hooks.py
│   │   └── test_sink_resolution.py
│   ├── orchestrator/
│   │   ├── test_orchestrator.py
│   │   ├── test_experiment_runner.py
│   │   └── test_scenarios.py
│   ├── middleware/
│   │   ├── test_llm_middleware.py           # Full middleware chains
│   │   └── test_security_filters.py
│   ├── retrieval/
│   │   ├── test_embedding_service.py
│   │   ├── test_providers.py
│   │   ├── test_utility.py
│   │   └── test_rag_integration.py
│   ├── signed/
│   │   ├── test_signed_artifacts.py
│   │   └── test_keyvault_signing.py
│   └── README.md
├── compliance/                              # ADR enforcement tests
│   ├── adr002/                              # Multi-Level Security
│   │   ├── test_baseplugin_compliance.py
│   │   ├── test_invariants.py
│   │   ├── test_error_handling.py
│   │   ├── test_properties.py
│   │   ├── test_validation.py
│   │   ├── test_middleware_integration.py
│   │   └── test_suite_integration.py
│   ├── adr002a/                             # Trusted Container Model
│   │   ├── test_invariants.py
│   │   └── test_performance.py
│   ├── adr004/                              # BasePlugin compliance
│   │   └── (tests may be consolidated with adr002)
│   ├── adr005/                              # Frozen plugins
│   │   └── test_baseplugin_frozen.py
│   ├── security/                            # Security controls compliance
│   │   ├── test_controls_registry.py
│   │   ├── test_controls_coverage.py
│   │   ├── test_secure_mode.py
│   │   └── test_approved_endpoints.py
│   └── README.md
├── performance/                             # Slow tests (>1s), benchmarks
│   ├── baselines/
│   │   └── test_performance_baseline.py
│   └── README.md
├── fixtures/                                # Shared fixtures & test data
│   ├── conftest.py                          # Global fixtures
│   ├── adr002_test_helpers.py               # ADR-002 specific helpers
│   ├── test_data/
│   │   └── (security test data, sample configs)
│   └── README.md
└── README.md                                # Top-level test organization guide
```

---

## File Mapping Strategy

### Mapping Rules

1. **Unit tests** → `tests/unit/`
   - Test single component in isolation
   - No external I/O (filesystem, network, database)
   - Fast (<1s per test)
   - Example: `test_csv_sink_writes()` → `unit/plugins/nodes/sinks/csv/test_write.py`

2. **Integration tests** → `tests/integration/`
   - Test multiple components together
   - May have I/O, external dependencies
   - Example: `test_cli_end_to_end()` → `integration/cli/test_suite_execution.py`

3. **Compliance tests** → `tests/compliance/`
   - Enforce ADR requirements
   - Security invariants
   - Example: `test_adr002_baseplugin_compliance.py` → `compliance/adr002/test_baseplugin_compliance.py`

4. **Performance tests** → `tests/performance/`
   - Slow tests (>1s)
   - Benchmarks, stress tests
   - Example: `test_performance_baseline.py` → `performance/baselines/test_performance_baseline.py`

### Decision Tree

```
Is the test enforcing an ADR requirement?
  YES → tests/compliance/adrXXX/
  NO  → Continue

Does the test take >1 second?
  YES → tests/performance/
  NO  → Continue

Does the test involve >1 component OR external I/O?
  YES → tests/integration/
  NO  → tests/unit/ (mirror source structure)
```

---

## Execution Protocol

### Step 2.1: Preparation (1 hour)

#### Create Directory Structure

```bash
# Create all subdirectories
mkdir -p tests/unit/core/{cli,pipeline,registries,security,validation}
mkdir -p tests/unit/plugins/nodes/sources/{csv,blob}
mkdir -p tests/unit/plugins/nodes/sinks/{csv,excel,blob,signed,bundles,repository,visual,analytics,embeddings,utilities}
mkdir -p tests/unit/plugins/nodes/transforms/llm
mkdir -p tests/unit/plugins/experiments/{aggregators,validators,baselines,lifecycle}
mkdir -p tests/unit/utils

mkdir -p tests/integration/{cli,suite_runner,orchestrator,middleware,retrieval,signed}
mkdir -p tests/compliance/{adr002,adr002a,adr004,adr005,security}
mkdir -p tests/performance/baselines
mkdir -p tests/fixtures/test_data
```

#### Extract Global Fixtures

```bash
# Move shared fixtures to fixtures/conftest.py
# Review tests/conftest.py for fixtures used by >5 files
# Extract to tests/fixtures/conftest.py
```

#### Backup Current State

```bash
# Create branch for safety
git checkout -b test-reorganization-phase2
git commit -m "Checkpoint: Before test reorganization Phase 2" --allow-empty
```

---

### Step 2.2: Automated Migration (3 hours)

#### Batch 1: Compliance Tests (30 minutes)

**Rationale**: Least risky, isolated from other tests

**Commands**:
```bash
# ADR-002 compliance
git mv tests/test_adr002_baseplugin_compliance.py tests/compliance/adr002/test_baseplugin_compliance.py
git mv tests/test_adr002_invariants.py tests/compliance/adr002/test_invariants.py
git mv tests/test_adr002_error_handling.py tests/compliance/adr002/test_error_handling.py
git mv tests/test_adr002_properties.py tests/compliance/adr002/test_properties.py
git mv tests/test_adr002_validation.py tests/compliance/adr002/test_validation.py
git mv tests/test_adr002_middleware_integration.py tests/compliance/adr002/test_middleware_integration.py
git mv tests/test_adr002_suite_integration.py tests/compliance/adr002/test_suite_integration.py

# ADR-002-A compliance
git mv tests/test_adr002a_invariants.py tests/compliance/adr002a/test_invariants.py
git mv tests/test_adr002a_performance.py tests/compliance/adr002a/test_performance.py

# ADR-005 compliance
git mv tests/test_baseplugin_frozen.py tests/compliance/adr005/test_baseplugin_frozen.py

# Security controls
git mv tests/test_controls.py tests/compliance/security/test_controls.py
git mv tests/test_controls_registry.py tests/compliance/security/test_controls_registry.py
git mv tests/test_controls_registry_coverage.py tests/compliance/security/test_controls_coverage.py
git mv tests/test_secure_mode_validations.py tests/compliance/security/test_secure_mode.py
git mv tests/test_security_approved_endpoints.py tests/compliance/security/test_approved_endpoints.py

# Verify
pytest tests/compliance/ --collect-only -q

# Commit
git add -A
git commit -m "test: Move compliance tests to tests/compliance/ (Phase 2.1)"
```

#### Batch 2: Sink Tests (45 minutes)

**Rationale**: High-volume category, clear mapping

**Commands**:
```bash
# CSV sinks
git mv tests/test_outputs_csv.py tests/unit/plugins/nodes/sinks/csv/test_write.py
git mv tests/test_csv_sink_path_guard.py tests/unit/plugins/nodes/sinks/csv/test_path_guard.py

# Excel sinks
git mv tests/test_outputs_excel.py tests/unit/plugins/nodes/sinks/excel/test_write.py
git mv tests/test_excel_sink_path_guard.py tests/unit/plugins/nodes/sinks/excel/test_path_guard.py
git mv tests/test_excel_sink_additional.py tests/unit/plugins/nodes/sinks/excel/test_sanitization.py

# Blob sinks
git mv tests/test_outputs_blob.py tests/unit/plugins/nodes/sinks/blob/test_write.py
git mv tests/test_blob_sink_errors.py tests/unit/plugins/nodes/sinks/blob/test_errors.py
git mv tests/test_blob_store.py tests/unit/plugins/nodes/sinks/blob/test_blob_store.py

# Signed artifacts
git mv tests/test_outputs_signed.py tests/unit/plugins/nodes/sinks/signed/test_artifact_generation.py
git mv tests/test_signed_sink.py tests/unit/plugins/nodes/sinks/signed/test_signing.py
git mv tests/test_signed_artifact_sink_coverage.py tests/unit/plugins/nodes/sinks/signed/test_coverage.py

# Bundles
git mv tests/test_outputs_local_bundle.py tests/unit/plugins/nodes/sinks/bundles/test_local_bundle.py
git mv tests/test_local_bundle_sink_errors.py tests/unit/plugins/nodes/sinks/bundles/test_local_bundle_errors.py
git mv tests/test_local_bundle_sink_path_guard.py tests/unit/plugins/nodes/sinks/bundles/test_local_bundle_path_guard.py
git mv tests/test_outputs_zip.py tests/unit/plugins/nodes/sinks/bundles/test_zip_bundle.py
git mv tests/test_zip_sink_name_sanitization.py tests/unit/plugins/nodes/sinks/bundles/test_zip_sanitization.py
git mv tests/test_zip_sink_path_guard.py tests/unit/plugins/nodes/sinks/bundles/test_zip_path_guard.py
git mv tests/test_reproducibility_bundle_sink.py tests/unit/plugins/nodes/sinks/bundles/test_reproducibility.py

# Repository
git mv tests/test_outputs_repo.py tests/unit/plugins/nodes/sinks/repository/test_repository_sinks.py
git mv tests/test_repository_sinks.py tests/unit/plugins/nodes/sinks/repository/test_repository_helpers.py

# Visual
git mv tests/test_visual_report_success.py tests/unit/plugins/nodes/sinks/visual/test_visual_report.py
git mv tests/test_visual_sink_errors.py tests/unit/plugins/nodes/sinks/visual/test_errors.py
git mv tests/test_outputs_visual.py tests/unit/plugins/nodes/sinks/visual/test_base_visual.py
git mv tests/test_enhanced_visual_sink.py tests/unit/plugins/nodes/sinks/visual/test_enhanced_visual.py
git mv tests/test_outputs_enhanced_visual.py tests/unit/plugins/nodes/sinks/visual/test_enhanced_visual_outputs.py

# Analytics
git mv tests/test_outputs_analytics_report.py tests/unit/plugins/nodes/sinks/analytics/test_analytics_report.py
git mv tests/test_analytics_report_errors.py tests/unit/plugins/nodes/sinks/analytics/test_errors.py

# Embeddings
git mv tests/test_outputs_embeddings_store.py tests/unit/plugins/nodes/sinks/embeddings/test_embeddings_store.py
git mv tests/test_embeddings_store_sink.py tests/unit/plugins/nodes/sinks/embeddings/test_embeddings_store_helpers.py

# Utilities
git mv tests/test_file_copy_sink_path_guard.py tests/unit/plugins/nodes/sinks/utilities/test_file_copy.py
git mv tests/test_sanitize_utils.py tests/unit/plugins/nodes/sinks/utilities/test_sanitize_utils.py

# Verify
pytest tests/unit/plugins/nodes/sinks/ --collect-only -q

# Commit
git add -A
git commit -m "test: Move sink tests to tests/unit/plugins/nodes/sinks/ (Phase 2.2)"
```

#### Batch 3: Source/LLM Tests (30 minutes)

```bash
# Sources
git mv tests/test_datasource_csv.py tests/unit/plugins/nodes/sources/csv/test_load.py
git mv tests/test_datasource_blob_plugin.py tests/unit/plugins/nodes/sources/blob/test_load.py

# LLM transforms
git mv tests/test_llm_azure.py tests/unit/plugins/nodes/transforms/llm/test_azure_openai.py
git mv tests/test_llm_http_openai.py tests/unit/plugins/nodes/transforms/llm/test_http_openai.py
git mv tests/test_llm_http_openai_rejects.py tests/unit/plugins/nodes/transforms/llm/test_http_openai_rejects.py
git mv tests/test_llm_mock.py tests/unit/plugins/nodes/transforms/llm/test_mock_llm.py
git mv tests/test_llm_static_plugin.py tests/unit/plugins/nodes/transforms/llm/test_static_plugin.py

# Verify
pytest tests/unit/plugins/nodes/sources/ tests/unit/plugins/nodes/transforms/ --collect-only -q

# Commit
git add -A
git commit -m "test: Move source/transform tests to tests/unit/plugins/nodes/ (Phase 2.3)"
```

#### Batch 4: Experiment Plugins (30 minutes)

```bash
# Aggregators
git mv tests/test_aggregators_cost_summary.py tests/unit/plugins/experiments/aggregators/test_cost_summary.py
git mv tests/test_aggregators_score_stats.py tests/unit/plugins/experiments/aggregators/test_score_stats.py
git mv tests/test_experiment_metrics_plugins.py tests/unit/plugins/experiments/aggregators/test_metrics_plugins.py
git mv tests/test_experiment_metrics_priority2.py tests/unit/plugins/experiments/aggregators/test_metrics_priority2.py

# Validators
git mv tests/test_validation_plugins.py tests/unit/plugins/experiments/validators/test_validation_plugins.py

# Baselines
git mv tests/test_baseline_score_significance.py tests/unit/plugins/experiments/baselines/test_score_significance.py
git mv tests/test_baseline_score_delta_coverage.py tests/unit/plugins/experiments/baselines/test_score_delta.py
git mv tests/test_baseline_score_assumptions_coverage.py tests/unit/plugins/experiments/baselines/test_assumptions_coverage.py

# Lifecycle
git mv tests/test_early_stop_coverage.py tests/unit/plugins/experiments/lifecycle/test_early_stop.py
git mv tests/test_prompt_variants_plugin.py tests/unit/plugins/experiments/lifecycle/test_prompt_variants.py

# Verify
pytest tests/unit/plugins/experiments/ --collect-only -q

# Commit
git add -A
git commit -m "test: Move experiment plugin tests to tests/unit/plugins/experiments/ (Phase 2.4)"
```

#### Batch 5: Core Framework (30 minutes)

```bash
# CLI utilities
git mv tests/test_cli_job_config.py tests/unit/core/cli/test_job_config_parsing.py

# Pipeline
git mv tests/test_artifact_pipeline.py tests/unit/core/pipeline/test_artifact_pipeline.py
git mv tests/test_sink_chaining.py tests/unit/core/pipeline/test_sink_chaining.py

# Registries
git mv tests/test_registry_base.py tests/unit/core/registries/test_base_registry.py
git mv tests/test_registry_plugin_helpers.py tests/unit/core/registries/test_plugin_helpers.py
git mv tests/test_registry_context_utils.py tests/unit/core/registries/test_context_utils.py
git mv tests/test_registry.py tests/unit/core/registries/test_registry_general.py
git mv tests/test_registry_schemas.py tests/unit/core/registries/test_schemas.py
git mv tests/test_plugin_registry_validators.py tests/unit/core/registries/test_validators.py
git mv tests/test_registries_datasource_coverage.py tests/unit/core/registries/test_datasource_coverage.py
git mv tests/test_experiment_plugin_registry_coverage.py tests/unit/core/registries/test_experiment_coverage.py
git mv tests/test_utilities_plugin_registry.py tests/unit/core/registries/test_utilities_registry.py
git mv tests/test_rate_limiter_registry.py tests/unit/core/registries/test_rate_limiter.py
git mv tests/test_registry_artifacts.py tests/unit/core/registries/test_artifacts.py

# Security
git mv tests/test_security_signing.py tests/unit/core/security/test_signing_symmetric.py
git mv tests/test_security_signing_asymmetric.py tests/unit/core/security/test_signing_asymmetric.py
git mv tests/test_security_level_enforcement.py tests/unit/core/security/test_level_enforcement.py
git mv tests/test_security_enforcement_defaults.py tests/unit/core/security/test_enforcement_defaults.py
git mv tests/test_path_guard.py tests/unit/core/security/test_path_guard_utils.py

# Validation
git mv tests/test_config_validation.py tests/unit/core/validation/test_config_validation.py
git mv tests/test_schema_validation.py tests/unit/core/validation/test_schema_validation.py
git mv tests/test_validation_core.py tests/unit/core/validation/test_core.py
git mv tests/test_validation_suite_coverage.py tests/unit/core/validation/test_suite_coverage.py
git mv tests/test_validation_rules_simple.py tests/unit/core/validation/test_rules_simple.py

# Verify
pytest tests/unit/core/ --collect-only -q

# Commit
git add -A
git commit -m "test: Move core framework tests to tests/unit/core/ (Phase 2.5)"
```

#### Batch 6: Integration Tests (45 minutes)

```bash
# CLI integration
git mv tests/test_cli_end_to_end.py tests/integration/cli/test_suite_execution.py
git mv tests/test_cli_integration.py tests/integration/cli/test_integration.py
git mv tests/test_cli.py tests/integration/cli/test_cli_general.py
git mv tests/test_cli_dry_run.py tests/integration/cli/test_dry_run.py
git mv tests/test_cli_strict_exit.py tests/integration/cli/test_strict_exit.py
git mv tests/test_cli_suite.py tests/integration/cli/test_suite.py
git mv tests/test_cli_validate_schemas.py tests/integration/cli/test_validate_schemas.py
git mv tests/test_cli_artifact_publish.py tests/integration/cli/test_artifact_publish.py
git mv tests/test_cli_artifact_publish_edges.py tests/integration/cli/test_artifact_publish_edges.py
git mv tests/test_cli_bundle_failure.py tests/integration/cli/test_bundle_failure.py
git mv tests/test_cli_yaml_json_edges.py tests/integration/cli/test_yaml_json_edges.py

# Suite runner
git mv tests/test_suite_runner_characterization.py tests/integration/suite_runner/test_characterization.py
git mv tests/test_suite_runner_integration.py tests/integration/suite_runner/test_integration.py
git mv tests/test_suite_runner_edge_cases.py tests/integration/suite_runner/test_edge_cases.py
git mv tests/test_suite_runner_baseline_flow.py tests/integration/suite_runner/test_baseline_flow.py
git mv tests/test_suite_runner_middleware_hooks.py tests/integration/suite_runner/test_middleware_hooks.py
git mv tests/test_suite_runner_sink_resolution.py tests/integration/suite_runner/test_sink_resolution.py
git mv tests/test_runner_characterization.py tests/integration/suite_runner/test_runner_characterization.py
git mv tests/test_runner_safety.py tests/integration/suite_runner/test_runner_safety.py
git mv tests/test_suite_reporter.py tests/integration/suite_runner/test_suite_reporter.py

# Orchestrator
git mv tests/test_orchestrator.py tests/integration/orchestrator/test_orchestrator.py
git mv tests/test_experiment_runner_integration.py tests/integration/orchestrator/test_experiment_runner.py
git mv tests/test_scenarios.py tests/integration/orchestrator/test_scenarios.py

# Middleware
git mv tests/test_llm_middleware.py tests/integration/middleware/test_llm_middleware.py
git mv tests/test_middleware_security_filters.py tests/integration/middleware/test_security_filters.py

# Retrieval
git mv tests/test_retrieval_embedding.py tests/integration/retrieval/test_embedding_service.py
git mv tests/test_retrieval_providers.py tests/integration/retrieval/test_providers.py
git mv tests/test_retrieval_service.py tests/integration/retrieval/test_service.py
git mv tests/test_retrieval_utility.py tests/integration/retrieval/test_utility.py
git mv tests/test_integration_embeddings_rag.py tests/integration/retrieval/test_rag_integration.py

# Signed artifacts
git mv tests/test_artifacts.py tests/integration/signed/test_signed_artifacts.py
git mv tests/test_keyvault_signing_mock.py tests/integration/signed/test_keyvault_signing.py

# Visual suite integration
git mv tests/test_integration_visual_suite.py tests/integration/visual/test_visual_suite_integration.py

# Verify
pytest tests/integration/ --collect-only -q

# Commit
git add -A
git commit -m "test: Move integration tests to tests/integration/ (Phase 2.6)"
```

#### Batch 7: Remaining Tests (30 minutes)

```bash
# Performance
git mv tests/test_performance_baseline.py tests/performance/baselines/test_performance_baseline.py

# Utils
git mv tests/test_env_helpers.py tests/unit/utils/test_env_helpers.py
git mv tests/test_scaffold.py tests/unit/utils/test_scaffold.py

# Config (could be unit or integration - use judgment)
git mv tests/test_config.py tests/unit/core/config/test_config.py
git mv tests/test_config_merge.py tests/unit/core/config/test_config_merge.py
git mv tests/test_config_suite.py tests/unit/core/config/test_config_suite.py

# Prompts
git mv tests/test_prompts.py tests/unit/core/prompts/test_prompts.py
git mv tests/test_prompts_loader.py tests/unit/core/prompts/test_loader.py

# Other
git mv tests/test_processing.py tests/unit/core/pipeline/test_processing.py
git mv tests/test_experiments.py tests/unit/plugins/experiments/test_experiments_general.py
git mv tests/test_healthcheck.py tests/unit/core/healthcheck/test_healthcheck.py
git mv tests/test_metrics_structure.py tests/unit/plugins/experiments/test_metrics_structure.py
git mv tests/test_sink_observability.py tests/unit/core/pipeline/test_sink_observability.py
git mv tests/test_suite_tools.py tests/unit/core/suite/test_suite_tools.py

# Verify
pytest tests/ --collect-only -q

# Commit
git add -A
git commit -m "test: Move remaining tests to structured directories (Phase 2.7)"
```

---

### Step 2.3: Import Path Updates (1 hour)

**Script**: `scripts/migrate_tests.py update-imports`

**Strategy**:
1. Scan all moved test files for relative imports
2. Convert to absolute imports: `from elspeth.core...`
3. Update fixture imports from `conftest`

**Example**:
```python
# Before (relative import)
from ..plugins.sinks.csv_file import CsvResultSink

# After (absolute import)
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink
```

**Execution**:
```bash
# Automated import rewrite
python scripts/migrate_tests.py update-imports --test-dir tests/

# Verify no import errors
pytest --collect-only -q

# Commit
git add -A
git commit -m "test: Update import paths after reorganization (Phase 2.8)"
```

---

### Step 2.4: Verification (1 hour)

#### Checklist

- [ ] All 136 root files moved (verify `ls tests/test_*.py | wc -l` = 0)
- [ ] All tests collect successfully: `pytest --collect-only -q`
- [ ] No import errors
- [ ] Full test suite runs: `pytest -v`
- [ ] Coverage unchanged: `pytest --cov --cov-report=term-missing`
- [ ] Git history preserved: `git log --follow tests/unit/core/cli/test_job_config_parsing.py`

#### Commands

```bash
# Verify root is empty
test $(find tests -maxdepth 1 -name "test_*.py" | wc -l) -eq 0 && echo "✅ Root clean"

# Collect tests
pytest --collect-only -q | tail -1
# Expected: "X tests collected" (should match pre-migration count)

# Run full suite
pytest -v --tb=short

# Check coverage
pytest --cov=elspeth --cov-report=term-missing | grep "TOTAL"
# Compare to baseline from Phase 1

# Verify git history
git log --follow --oneline tests/unit/core/cli/test_job_config_parsing.py | head -5
# Should show history from test_cli_job_config.py
```

---

### Step 2.5: Documentation (30 minutes)

#### Create README.md Files

**`tests/README.md`** - Top-level guide
**`tests/unit/README.md`** - Unit test organization
**`tests/integration/README.md`** - Integration test guide
**`tests/compliance/README.md`** - ADR compliance guide
**`tests/performance/README.md`** - Performance test guide
**`tests/fixtures/README.md`** - Fixture documentation

**Template**:
```markdown
# [Directory Name] Tests

## Purpose

[What types of tests go here]

## Organization

[Subdirectory structure]

## Adding New Tests

[Guidelines for adding tests to this directory]

## Running Tests

```bash
# Run all tests in this directory
pytest tests/[directory]/

# Run specific subdirectory
pytest tests/[directory]/[subdirectory]/
```

## Common Fixtures

[List of fixtures commonly used in this directory]
```

---

## Phase 2 Deliverables

- [ ] All 136 root test files moved to structured subdirectories
- [ ] Import paths updated
- [ ] All tests passing
- [ ] Git history preserved
- [ ] Coverage maintained (±2%)
- [ ] README.md files created
- [ ] `REORGANIZATION_SUMMARY.md` generated

---

## Rollback Strategy

**If Phase 2 fails**:
```bash
# Revert to pre-reorganization state
git reset --hard origin/main
git branch -D test-reorganization-phase2

# OR revert specific batch
git revert <commit-sha>
```

---

## Success Criteria

✅ **0 test files in tests/ root**
✅ **All tests collect successfully**
✅ **All tests passing**
✅ **Imports correct**
✅ **Coverage maintained**
✅ **Git history preserved**
✅ **Documentation complete**

---

## Next Steps

Once Phase 2 complete:
1. Generate `REORGANIZATION_SUMMARY.md` (test count per directory, mapping table)
2. Update `README.md` status tracker
3. Proceed to Phase 3: `02-DEDUPLICATION_STRATEGY.md`

---

**Phase 2 Time Estimate**: 6-8 hours
**Risk Level**: Medium (mitigated by frequent commits, git mv)
**Dependencies**: Phase 1 complete
