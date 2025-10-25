# Elspeth Documentation Status Review

- Generated: 2025-10-26T03:25:15.459530
- Total Markdown files reviewed: 147
- Updated within last 30 days: 147
- Updated more than 180 days ago: 0

## Methodology

1. Enumerated all Markdown files under `docs/` and repository root.
2. Extracted first heading and first substantive line to estimate each file's stated purpose.
3. Collected filesystem metadata (`ctime` as creation, `mtime` as last modification, `atime` as last access).
4. Grouped files by documentation area to highlight coverage and staleness risk.

> **Note**: On Linux filesystems `ctime` tracks metadata changes, which may differ slightly from original creation timestamp.

### Batched Inventory (10 files per group)

```
Batch 1 (1-10):
  1. CLAUDE.md
  2. CONTRIBUTING.md
  3. docs/architecture/architecture-overview.md
  4. docs/architecture/archive/adr-002-implementation/ADR002A_CODE_REVIEW.md
  5. docs/architecture/archive/adr-002-implementation/ADR002A_EVALUATION.md
  6. docs/architecture/archive/adr-002-implementation/ADR002A_PLAN.md
  7. docs/architecture/archive/adr-002-implementation/ADR002_IMPLEMENTATION_README.md
  8. docs/architecture/archive/adr-002-implementation/CERTIFICATION_EVIDENCE.md
  9. docs/architecture/archive/adr-002-implementation/CHECKLIST.md
 10. docs/architecture/archive/adr-002-implementation/METHODOLOGY.md

Batch 2 (11-20):
 11. docs/architecture/archive/adr-002-implementation/PROGRESS.md
 12. docs/architecture/archive/adr-002-implementation/README.md
 13. docs/architecture/archive/adr-002-implementation/THREAT_MODEL.md
 14. docs/architecture/audit-logging.md
 15. docs/architecture/component-diagram.md
 16. docs/architecture/configuration-security.md
 17. docs/architecture/CORE_STRUCTURE_CURRENT.md
 18. docs/architecture/data-flow-diagrams.md
 19. docs/architecture/decisions/000-template.md
 20. docs/architecture/decisions/001-design-philosophy.md

Batch 3 (21-30):
 21. docs/architecture/decisions/002-a-trusted-container-model.md
 22. docs/architecture/decisions/002-security-architecture.md
 23. docs/architecture/decisions/003-plugin-type-registry.md
 24. docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md
 25. docs/architecture/decisions/005-security-critical-exception-policy.md
 26. docs/architecture/decisions/historical/003-remove-legacy-code.md
 27. docs/architecture/decisions/historical/004-complete-registry-migration.md
 28. docs/architecture/decisions/README.md
 29. docs/architecture/embeddings-rag-plugin-design.md
 30. docs/architecture/llm-tracing-plugin-options.md

Batch 4 (31-40):
 31. docs/architecture/middleware-lifecycle.md
 32. docs/architecture/plugin-catalogue.md
 33. docs/architecture/plugin-security-model.md
 34. docs/architecture/README.md
 35. docs/architecture/security-controls.md
 36. docs/architecture/sink-hardening-plan.md
 37. docs/architecture/threat-surfaces.md
 38. docs/archive/roadmap/data-flow-migration/data-flow-migration/SILENT_DEFAULTS_AUDIT.md
 39. docs/compliance/accreditation-run-example.md
 40. docs/compliance/adr-002-certification-evidence.md

Batch 5 (41-50):
 41. docs/compliance/AUSTRALIAN_GOVERNMENT_CONTROLS.md
 42. docs/compliance/COMPLIANCE_ROADMAP.md
 43. docs/compliance/configuration-security.md
 44. docs/compliance/CONTROL_INVENTORY.md
 45. docs/compliance/deployment-diagram.md
 46. docs/compliance/environment-hardening.md
 47. docs/compliance/incident-response.md
 48. docs/compliance/README.md
 49. docs/compliance/threat-traceability.md
 50. docs/compliance/TRACEABILITY_MATRIX.md

Batch 6 (51-60):
 51. docs/development/core-extension-design.md
 52. docs/development/dependency-analysis.md
 53. docs/development/logging-standards.md
 54. docs/development/plugin-authoring.md
 55. docs/development/plugin-hardening-principles.md
 56. docs/development/README.md
 57. docs/development/suite-lifecycle.md
 58. docs/development/testing-overview.md
 59. docs/development/upgrade-strategy.md
 60. docs/end_to_end_scenarios.md

Batch 7 (61-70):
 61. docs/examples/colour-animals.md
 62. docs/examples/MASTER_EXAMPLE.md
 63. docs/examples/README.md
 64. docs/examples/SCHEMA_VALIDATION_DEMO.md
 65. docs/examples/SECURE_AZURE_WORKFLOW_GUIDE.md
 66. docs/examples/SECURITY_MIDDLEWARE_DEMOS.md
 67. docs/external/README.md
 68. docs/guides/plugin-development-adr002a.md
 69. docs/migration/adr-002-baseplugin-completion/CHECKLIST.md
 70. docs/migration/adr-002-baseplugin-completion/PHASE_0_STATUS.md

Batch 8 (71-80):
 71. docs/migration/adr-002-baseplugin-completion/PHASE_0_TEST_SPECIFICATION.md
 72. docs/migration/adr-002-baseplugin-completion/PHASE_1.5_REGISTRY_ENFORCEMENT.md
 73. docs/migration/adr-002-baseplugin-completion/PHASE_1_IMPLEMENTATION_GUIDE.md
 74. docs/migration/adr-002-baseplugin-completion/PHASE_2_VALIDATION_CLEANUP.md
 75. docs/migration/adr-002-baseplugin-completion/PHASE_3_VERIFICATION.md
 76. docs/migration/adr-002-baseplugin-completion/README.md
 77. docs/migration/adr-003-004-classified-containers/INTEGRATED_ROADMAP.md
 78. docs/migration/adr-003-004-classified-containers/MIGRATION_COMPLEXITY_ASSESSMENT.md
 79. docs/migration/adr-003-004-classified-containers/plugin_migration_analysis.md
 80. docs/migration/adr-003-004-classified-containers/README.md

Batch 9 (81-90):
 81. docs/migration/adr-003-004-classified-containers/README_MIGRATION_ANALYSIS.md
 82. docs/migration/adr-003-004-classified-containers/RENAMING_ASSESSMENT.md
 83. docs/migration-guide.md
 84. docs/operations/artifacts.md
 85. docs/operations/branch-protection-setup.md
 86. docs/operations/dependabot.md
 87. docs/operations/dependency-governance.md
 88. docs/operations/healthcheck.md
 89. docs/operations/job-configs.md
 90. docs/operations/logging.md

Batch 10 (91-100):
 91. docs/operations/retrieval-endpoints.md
 92. docs/operations/security-patch-automation.md
 93. docs/quality/README.md
 94. docs/quality/sonar_issues_triaged.md
 95. docs/README.md
 96. docs/refactoring/completed/pr-010-runner-refactor/baseline_summary.md
 97. docs/refactoring/completed/pr-010-runner-refactor/EXECUTION_PLAN_runner_refactor.md
 98. docs/refactoring/completed/pr-010-runner-refactor/README.md
 99. docs/refactoring/completed/pr-010-runner-refactor/REFACTORING_COMPLETE_summary.md
100. docs/refactoring/completed/pr-010-runner-refactor/refactor_plan_runner_run.md

Batch 11 (101-110):
101. docs/refactoring/completed/pr-010-runner-refactor/risk_mitigation_runner_refactor.md
102. docs/refactoring/completed/pr-011-suite-runner-refactor/baseline_flow_diagram.md
103. docs/refactoring/completed/pr-011-suite-runner-refactor/CHECKPOINT_suite_runner_phase0_complete.md
104. docs/refactoring/completed/pr-011-suite-runner-refactor/EXECUTION_PLAN_suite_runner_refactor.md
105. docs/refactoring/completed/pr-011-suite-runner-refactor/PROGRESS_suite_runner_refactoring.md
106. docs/refactoring/completed/pr-011-suite-runner-refactor/README.md
107. docs/refactoring/completed/pr-011-suite-runner-refactor/REFACTORING_COMPLETE_suite_runner.md
108. docs/refactoring/completed/pr-011-suite-runner-refactor/risk_reduction_suite_runner.md
109. docs/refactoring/completed/pr-011-suite-runner-refactor/sink_resolution_documentation.md
110. docs/refactoring/METHODOLOGY.md

Batch 12 (111-120):
111. docs/refactoring/QUICK_REFERENCE.md
112. docs/refactoring/v1.1/CHECKLIST.md
113. docs/refactoring/v1.1/METHODOLOGY.md
114. docs/refactoring/v1.1/QUICK_START.md
115. docs/refactoring/v1.1/TEMPLATES.md
116. docs/release-checklist.md
117. docs/reporting-and-suite-management.md
118. docs/roadmap/FEATURE_ROADMAP.md
119. docs/roadmap/README.md
120. docs/roadmap/SILENT_DEFAULTS_REMOVAL_PLAN.md

Batch 13 (121-130):
121. docs/roadmap/work-packages/WP001-streaming-datasource-architecture.md
122. docs/roadmap/work-packages/WP002-dataframe-schema-validation.md
123. docs/roadmap/work-packages/WP002_IMPLEMENTATION_PLAN.md
124. docs/security/adr-002-a-trusted-container-model.md
125. docs/security/adr-002-classified-dataframe-hardening-delta.md
126. docs/security/adr-002-implementation-gap.md
127. docs/security/adr-002-orchestrator-security-model.md
128. docs/security/adr-002-threat-model.md
129. docs/security/archive/fuzzing_design_review_external.md
130. docs/security/archive/fuzzing_design_review.md

Batch 14 (131-140):
131. docs/security/archive/phase2_blocked_atheris/fuzzing_coverage_guided.md
132. docs/security/archive/phase2_blocked_atheris/fuzzing_coverage_guided_plan.md
133. docs/security/archive/phase2_blocked_atheris/fuzzing_coverage_guided_readiness.md
134. docs/security/archive/phase2_blocked_atheris/README.md
135. docs/security/DEPENDENCY_VULNERABILITIES.md
136. docs/security/EXTERNAL_SERVICES.md
137. docs/security/fuzzing/fuzzing_irap_risk_acceptance.md
138. docs/security/fuzzing/fuzzing.md
139. docs/security/fuzzing/fuzzing_plan.md
140. docs/security/fuzzing/IMPLEMENTATION.md

Batch 15 (141-147):
141. docs/security/fuzzing/MODERNIZATION_SUMMARY.md
142. docs/security/fuzzing/README.md
143. docs/SECURITY.md
144. docs/security/README-ADR002-IMPLEMENTATION.md
145. docs/security/SECURITY_TEST_REPORT.md
146. docs/testing/PERFORMANCE_BASELINES.md
147. README.md
```

## High-Level Observations

- Documentation set is large (147 files) with significant focus on architecture, security, and migration playbooks.

- 147 files updated in the past 30 days, indicating active maintenance in several areas (notably security fuzzing and architecture archives).

- 0 files have not been modified in over 6 months and are candidates for archival review or refresh.

- Multiple directories contain historical or archived plans; consolidating status (active vs archived) would reduce navigation friction.

- Consider establishing an authoritative index per domain (architecture, security, operations) to prevent drift between overlapping plans and checklists.


## Detailed Inventory

### (root)

#### root

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `CLAUDE.md` | This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. | 16.5 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `CONTRIBUTING.md` | Thanks for investing time in improving Elspeth! This guide outlines the expectations for proposing changes, writing code, and keeping the documentation and artefacts in sync. | 4.1 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `README.md` | **E**xtensible **L**ayered **S**ecure **P**ipeline **E**ngine for **T**ransformation and **H**andling | 11.4 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### README.md

#### docs

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/README.md` | This directory contains all operational guides, architecture references, compliance evidence, and development documentation for the Elspeth orchestrator. Use this index to jump to the resource you need. | 5.0 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### SECURITY.md

#### docs

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/SECURITY.md` | ## Reporting a Security Vulnerability | 8.6 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### architecture

#### architecture

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/architecture/CORE_STRUCTURE_CURRENT.md` | **Last Updated:** 2025-10-17 | 7.9 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/README.md` | This directory contains the technical architecture documentation for Elspeth's core design patterns, plugin system, and data flows. | 3.4 | 2025-10-24 | 2025-10-24 | 2025-10-25 | 1 |
| `docs/architecture/architecture-overview.md` | ## Core Principles | 23.8 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/audit-logging.md` | ## Logging Sources | 12.8 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/architecture/component-diagram.md` | ```mermaid | 16.3 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/configuration-security.md` | This document summarises how ELSPETH validates configuration inputs, hydrates suites, and protects | 6.0 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/data-flow-diagrams.md` | ## Experiment Execution Flow | 17.4 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/embeddings-rag-plugin-design.md` | ## Purpose | 10.7 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/llm-tracing-plugin-options.md` | <!-- UPDATE 2025-10-12: Initial option catalogue and evaluation --> | 9.4 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/architecture/middleware-lifecycle.md` | **Status:** Implementation Reference | 19.1 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/plugin-catalogue.md` | All built-in plugins now receive a `PluginContext` instance during construction. The context carries the resolved security classification, provenance trail, and any parent metadata. Unless explicitly noted, each plugin inherits classification from configuration via this context and requires no further adjustments. | 23.3 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/plugin-security-model.md` | ## Registry Architecture | 13.4 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/architecture/security-controls.md` | ## Authentication & Authorization | 24.0 | 2025-10-24 | 2025-10-24 | 2025-10-25 | 1 |
| `docs/architecture/sink-hardening-plan.md` | Objective: Enforce write-path allowlists and symlink containment across local sinks (CSV, Excel, local_bundle, zip_bundle), and extend observability with structured PluginLogger events. | 2.5 | 2025-10-18 | 2025-10-18 | 2025-10-25 | 7 |
| `docs/architecture/threat-surfaces.md` | ## Trust Zones | 14.8 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

#### architecture/archive/adr-002-implementation

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/architecture/archive/adr-002-implementation/ADR002A_CODE_REVIEW.md` | **Reviewer**: Security Code Review | 22.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/ADR002A_EVALUATION.md` | **Date**: 2025-10-25 | 18.7 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/ADR002A_PLAN.md` | **Status**: Planning | 17.7 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/ADR002_IMPLEMENTATION_README.md` | **Status**: ADR-002 Phase 2 Complete ✅ \| ADR-002-A Phase 4 Complete ✅ | 6.2 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/CERTIFICATION_EVIDENCE.md` | **Implementation Status**: ✅ COMPLETE | 29.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/CHECKLIST.md` | **Quick reference checklist - expand details in METHODOLOGY.md** | 7.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/METHODOLOGY.md` | **Adapted from:** `docs/refactoring/METHODOLOGY.md` (PR #10, PR #11 - 100% success rate) | 21.7 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/PROGRESS.md` | **Branch**: `feature/adr-002-security-enforcement` | 24.3 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/README.md` | **Status**: Implementation Complete (2025-10-25) | 6.1 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/archive/adr-002-implementation/THREAT_MODEL.md` | **Date**: 2025-10-25 (Updated) | 23.5 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### architecture/decisions

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/architecture/decisions/000-template.md` | ## Status | 1.9 | 2025-10-24 | 2025-10-24 | 2025-10-25 | 1 |
| `docs/architecture/decisions/001-design-philosophy.md` | ## Status | 5.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/decisions/002-a-trusted-container-model.md` | ## Status | 9.2 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/decisions/002-security-architecture.md` | ## Status | 5.8 | 2025-10-24 | 2025-10-24 | 2025-10-25 | 1 |
| `docs/architecture/decisions/003-plugin-type-registry.md` | **Status**: ACCEPTED | 17.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md` | **Status**: PROPOSED | 42.1 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/decisions/005-security-critical-exception-policy.md` | ## Status | 37.2 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/architecture/decisions/README.md` | This directory contains Architecture Decision Records documenting significant architectural and design decisions for Elspeth. | 5.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### architecture/decisions/historical

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/architecture/decisions/historical/003-remove-legacy-code.md` | ## Status | 0.5 | 2025-10-24 | 2025-10-24 | 2025-10-25 | 1 |
| `docs/architecture/decisions/historical/004-complete-registry-migration.md` | ## Status | 0.6 | 2025-10-24 | 2025-10-24 | 2025-10-25 | 1 |

### archive

#### archive/roadmap/data-flow-migration/data-flow-migration

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/archive/roadmap/data-flow-migration/data-flow-migration/SILENT_DEFAULTS_AUDIT.md` | This document records critical defaults and their rationale to avoid silent or surprising behavior. | 1.0 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### compliance

#### compliance

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/compliance/AUSTRALIAN_GOVERNMENT_CONTROLS.md` | ## Overview | 8.9 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/compliance/COMPLIANCE_ROADMAP.md` | This roadmap expands on the compliance uplift required for Elspeth, mapping documentation, tooling, and governance workstreams to accreditation expectations (e.g., ISM, Essential Eight, IRAP). It complements `../roadmap/FEATURE_ROADMAP.md` by focusing on evidence, policy, and assurance deliverables. | 6.1 | 2025-10-15 | 2025-10-15 | 2025-10-25 | 10 |
| `docs/compliance/CONTROL_INVENTORY.md` | \| Control ID \| Description \| Implementation \| Test Coverage \| Doc Reference \| | 4.2 | 2025-10-18 | 2025-10-18 | 2025-10-25 | 7 |
| `docs/compliance/README.md` | This directory contains all compliance, security audit, and governance documentation for Elspeth. | 1.9 | 2025-10-15 | 2025-10-15 | 2025-10-25 | 10 |
| `docs/compliance/TRACEABILITY_MATRIX.md` | \| Component \| File Path \| Documentation Reference \| Last Verified \| | 2.3 | 2025-10-18 | 2025-10-18 | 2025-10-25 | 7 |
| `docs/compliance/accreditation-run-example.md` | ## Objective | 3.7 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/compliance/adr-002-certification-evidence.md` | **Implementation Status**: ✅ COMPLETE | 29.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/compliance/configuration-security.md` | ## Configuration Entry Points | 11.9 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/compliance/deployment-diagram.md` | ```penguin | 1.9 | 2025-10-18 | 2025-10-18 | 2025-10-25 | 7 |
| `docs/compliance/environment-hardening.md` | ## Secrets & Credentials | 4.3 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/compliance/incident-response.md` | ```penguin | 1.4 | 2025-10-15 | 2025-10-15 | 2025-10-25 | 10 |
| `docs/compliance/threat-traceability.md` | ```penguin | 1.8 | 2025-10-18 | 2025-10-18 | 2025-10-25 | 7 |

### development

#### development

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/development/README.md` | This directory contains developer-focused guides for contributing to Elspeth. | 1.4 | 2025-10-15 | 2025-10-15 | 2025-10-25 | 10 |
| `docs/development/core-extension-design.md` | This note sketches early implementation steps for broadening the orchestrator beyond LLM-centric workflows while preserving the security, auditability, and reliability guarantees described in the plugin catalogue. | 7.2 | 2025-10-15 | 2025-10-15 | 2025-10-25 | 10 |
| `docs/development/dependency-analysis.md` | ## Core Runtime Dependencies | 9.5 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/development/logging-standards.md` | This document defines the minimum logging expectations for middleware and | 6.1 | 2025-10-18 | 2025-10-18 | 2025-10-25 | 7 |
| `docs/development/plugin-authoring.md` | Audience: Plugin authors and integrators building datasources, experiment plugins, sinks, or middleware for Elspeth. | 14.2 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/development/plugin-hardening-principles.md` | This note captures the long-term plugin architecture reforms originally outlined in the external `PLUGIN_REFORM.md`. It complements the feature roadmap by describing how we intend to make plugins safer, more discoverable, and easier to audit. | 4.7 | 2025-10-15 | 2025-10-15 | 2025-10-25 | 10 |
| `docs/development/suite-lifecycle.md` | ```penguin | 1.7 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/development/testing-overview.md` | \| Area \| Key Tests \| Focus \| | 3.2 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/development/upgrade-strategy.md` | ## Dependency Inventory | 2.4 | 2025-10-15 | 2025-10-15 | 2025-10-25 | 10 |

### end_to_end_scenarios.md

#### docs

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/end_to_end_scenarios.md` | This document records the high-value integration scenarios covered by the non-Azure tests. Each scenario exercises a representative pipeline across prompts, datasources, plugins, and sinks so future contributors can reuse or extend the patterns. | 3.1 | 2025-10-12 | 2025-10-12 | 2025-10-25 | 13 |

### examples

#### examples

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/examples/MASTER_EXAMPLE.md` | This walkthrough bundles the features most teams care about into a single, reproducible | 6.9 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/examples/README.md` | This directory contains practical examples and walkthroughs for common Elspeth workflows. | 1.5 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/examples/SCHEMA_VALIDATION_DEMO.md` | ## Status: Production Ready ✅ | 14.3 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/examples/SECURE_AZURE_WORKFLOW_GUIDE.md` | Updated October 2025 — this walkthrough shows how to run a fully secured Elspeth suite | 9.3 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/examples/SECURITY_MIDDLEWARE_DEMOS.md` | These companion demos walk through the two defensive middleware plugins shipped with | 6.0 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/examples/colour-animals.md` | This example drives a locally hosted OpenAI-compatible model (running on `http://192.168.1.240:5000`) to suggest an animal for each colour in a 100-row CSV. | 5.8 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### external

#### external

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/external/README.md` | This folder previously contained external PDFs used during early design and audits. | 0.5 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### guides

#### guides

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/guides/plugin-development-adr002a.md` | **Target Audience**: Plugin developers implementing datasources, transforms, and sinks | 13.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

### migration

#### migration/adr-002-baseplugin-completion

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/migration/adr-002-baseplugin-completion/CHECKLIST.md` | **Quick Reference**: Use this checklist to track progress through all 3 phases | 10.4 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-002-baseplugin-completion/PHASE_0_STATUS.md` | **Date**: 2025-10-25 | 28.4 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-002-baseplugin-completion/PHASE_0_TEST_SPECIFICATION.md` | **Objective**: Build comprehensive test coverage proving ADR-002 validation currently short-circuits | 21.5 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-002-baseplugin-completion/PHASE_1.5_REGISTRY_ENFORCEMENT.md` | **Objective**: Add registration-time checks to reject plugins without BasePlugin methods | 7.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-002-baseplugin-completion/PHASE_1_IMPLEMENTATION_GUIDE.md` | **Objective**: Ensure all 26 plugin classes inherit from BasePlugin ABC and pass security level to the base constructor | 9.8 | 2025-10-26 | 2025-10-26 | 2025-10-26 | 0 |
| `docs/migration/adr-002-baseplugin-completion/PHASE_2_VALIDATION_CLEANUP.md` | **Objective**: Remove defensive `hasattr` checks from validation code | 12.1 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-002-baseplugin-completion/PHASE_3_VERIFICATION.md` | **Objective**: Prove ADR-002 validation now works end-to-end | 9.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-002-baseplugin-completion/README.md` | **Project Type**: Critical Security Implementation Gap | 20.7 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### migration/adr-003-004-classified-containers

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/migration/adr-003-004-classified-containers/INTEGRATED_ROADMAP.md` | **Total Duration**: 35-47 hours (5-6 days) | 17.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-003-004-classified-containers/MIGRATION_COMPLEXITY_ASSESSMENT.md` | **Date**: 2025-10-25 | 20.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-003-004-classified-containers/README.md` | **Migration Type**: Terminology + Architecture Enhancement - Secure Container Adoption | 44.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-003-004-classified-containers/README_MIGRATION_ANALYSIS.md` | ## Overview | 8.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-003-004-classified-containers/RENAMING_ASSESSMENT.md` | **Migration Type**: Terminology Standardization - Universal Applicability | 25.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/migration/adr-003-004-classified-containers/plugin_migration_analysis.md` | ## Executive Summary | 35.7 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

### migration-guide.md

#### docs

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/migration-guide.md` | This guide helps teams upgrade from the legacy `old/` implementation to the modern plugin-driven ELSPETH. | 10.4 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### operations

#### operations

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/operations/artifacts.md` | This guide describes how Elspeth writes persistent job artifacts for audits and reproducibility. | 3.6 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/operations/branch-protection-setup.md` | **Purpose:** Configure GitHub branch protection rules to enable automated security patches while requiring manual review for regular updates. | 10.9 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/operations/dependabot.md` | **Status:** ✅ Active with Auto-Merge for Security Patches | 13.9 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/operations/dependency-governance.md` | This note captures the workflow for maintaining deterministic Python | 2.1 | 2025-10-18 | 2025-10-18 | 2025-10-25 | 7 |
| `docs/operations/healthcheck.md` | Health Check Server | 1.5 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/operations/job-configs.md` | Elspeth can run simple ad‑hoc jobs that assemble a datasource, optional LLM transform (with prompts and middlewares), and one or more sinks, without a full suite configuration. | 3.0 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/operations/logging.md` | Elspeth plugins emit structured JSON Lines under `logs/` for each run (one file per run): | 0.8 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/operations/retrieval-endpoints.md` | ## Overview | 4.2 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/operations/security-patch-automation.md` | **Status:** ✅ Active | 14.3 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### quality

#### quality

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/quality/README.md` | This directory contains code quality analysis reports and triage documentation. | 1.7 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/quality/sonar_issues_triaged.md` | **Generated:** 2025-10-23 | 15.4 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

### refactoring

#### refactoring

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/refactoring/METHODOLOGY.md` | **Version:** 1.0 | 69.5 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/QUICK_REFERENCE.md` | **Use this checklist during refactoring to ensure nothing is missed.** | 6.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### refactoring/completed/pr-010-runner-refactor

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/refactoring/completed/pr-010-runner-refactor/EXECUTION_PLAN_runner_refactor.md` | **Target:** `src/elspeth/core/experiments/runner.py:75-245` | 75.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-010-runner-refactor/README.md` | **Date**: 2025-10-24 | 2.2 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-010-runner-refactor/REFACTORING_COMPLETE_summary.md` | **Date:** 2025-10-24 | 10.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-010-runner-refactor/baseline_summary.md` | **Date:** 2025-10-23 | 5.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-010-runner-refactor/refactor_plan_runner_run.md` | **Target:** `src/elspeth/core/experiments/runner.py:75-245` | 21.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-010-runner-refactor/risk_mitigation_runner_refactor.md` | **Target:** `src/elspeth/core/experiments/runner.py:75` | 17.2 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### refactoring/completed/pr-011-suite-runner-refactor

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/refactoring/completed/pr-011-suite-runner-refactor/CHECKPOINT_suite_runner_phase0_complete.md` | **Date:** 2025-10-24 | 14.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-011-suite-runner-refactor/EXECUTION_PLAN_suite_runner_refactor.md` | **Target:** `src/elspeth/core/experiments/suite_runner.py::run()` | 24.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-011-suite-runner-refactor/PROGRESS_suite_runner_refactoring.md` | **Date:** 2025-10-24 | 18.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-011-suite-runner-refactor/README.md` | **Date**: 2025-10-24 | 3.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-011-suite-runner-refactor/REFACTORING_COMPLETE_suite_runner.md` | **Date:** 2025-10-24 | 27.1 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-011-suite-runner-refactor/baseline_flow_diagram.md` | **Purpose:** Document the exact baseline tracking and comparison timing logic in `suite_runner.py::run()` to prevent regressions during refactoring. | 16.2 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-011-suite-runner-refactor/risk_reduction_suite_runner.md` | **Target:** `suite_runner.py::run()` (complexity 69) | 21.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/completed/pr-011-suite-runner-refactor/sink_resolution_documentation.md` | **File:** `src/elspeth/core/experiments/suite_runner.py` | 14.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### refactoring/v1.1

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/refactoring/v1.1/CHECKLIST.md` | **Version:** 1.1 | 11.1 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/v1.1/METHODOLOGY.md` | **Version:** 1.1 | 91.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/v1.1/QUICK_START.md` | **Version:** 1.1 | 7.9 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/refactoring/v1.1/TEMPLATES.md` | **Version:** 1.1 | 32.4 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

### release-checklist.md

#### docs

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/release-checklist.md` | Use this list before shipping a new release. Treat it as a living document; | 6.8 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### reporting-and-suite-management.md

#### docs

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/reporting-and-suite-management.md` | This guide walks through the new CLI flows for maintaining legacy-style suites, generating | 10.1 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### roadmap

#### roadmap

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/roadmap/FEATURE_ROADMAP.md` | This roadmap outlines the planned expansion of Elspeth’s capabilities so stakeholders can track feature coverage, vendor alignment, and upcoming workstreams. It complements the compliance roadmap by focusing on functional growth across datasources, LLM clients, middleware, metrics, sinks, and observability. | 8.6 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/roadmap/README.md` | This directory tracks planned features, work packages, and completed initiatives. | 1.5 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/roadmap/SILENT_DEFAULTS_REMOVAL_PLAN.md` | **Purpose**: Remove all critical silent defaults to enforce explicit configuration for security-sensitive parameters. | 12.9 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |

#### roadmap/work-packages

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/roadmap/work-packages/WP001-streaming-datasource-architecture.md` | **Status**: Planning | 77.3 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/roadmap/work-packages/WP002-dataframe-schema-validation.md` | **Status**: Implemented with Pydantic v2 | 34.8 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/roadmap/work-packages/WP002_IMPLEMENTATION_PLAN.md` | **Target**: Demo-ready in 1-2 days | 38.4 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

### security

#### security

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/security/DEPENDENCY_VULNERABILITIES.md` | This document tracks known vulnerabilities in Elspeth's dependencies and their remediation status. | 3.9 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |
| `docs/security/EXTERNAL_SERVICES.md` | **Document Version:** 1.0 | 20.9 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/security/README-ADR002-IMPLEMENTATION.md` | **Status**: ✅ Phase 0-4 Complete \| ✅ ADR-002-A Complete | 11.1 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/SECURITY_TEST_REPORT.md` | **Date:** October 15, 2025 | 12.3 | 2025-10-17 | 2025-10-17 | 2025-10-25 | 8 |
| `docs/security/adr-002-a-trusted-container-model.md` | **Status**: Proposed | 14.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/adr-002-classified-dataframe-hardening-delta.md` | **Status**: Proposed Security Enhancement | 20.5 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/adr-002-implementation-gap.md` | **Document Status**: Implementation Specification | 27.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/adr-002-orchestrator-security-model.md` | **Document Purpose**: Clarifies the correct "minimum clearance envelope" model for ADR-002 implementation | 42.7 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/adr-002-threat-model.md` | **Date**: 2025-10-25 (Updated) | 23.5 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### security/archive

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/security/archive/fuzzing_design_review.md` | Reviewer: Internal self‑review of the canonical strategy in `docs/security/fuzzing/fuzzing.md`. | 7.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/archive/fuzzing_design_review_external.md` | Excellent feedback from your other agent! Let me break down what's **gold**, what's **good with caveats**, and what to **avoid or defer**. I'll then give you an integrated recommendation list. | 17.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### security/archive/phase2_blocked_atheris

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/security/archive/phase2_blocked_atheris/README.md` | **Status**: 🔴 **BLOCKED** - Awaiting Atheris Python 3.12 support | 5.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/archive/phase2_blocked_atheris/fuzzing_coverage_guided.md` | **Status**: 🔶 **BLOCKED** - Awaiting Atheris Python 3.12 support | 20.8 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/archive/phase2_blocked_atheris/fuzzing_coverage_guided_plan.md` | **Status**: 🔶 **BLOCKED** - Awaiting Atheris Python 3.12 support | 12.3 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/archive/phase2_blocked_atheris/fuzzing_coverage_guided_readiness.md` | **Purpose**: Track prerequisites for Phase 2 (Atheris coverage-guided fuzzing) implementation | 14.4 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

#### security/fuzzing

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/security/fuzzing/IMPLEMENTATION.md` | **Purpose**: Tactical step-by-step guide to implement property-based fuzzing with Hypothesis | 17.1 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/fuzzing/MODERNIZATION_SUMMARY.md` | **Date**: 2025-10-25 | 12.6 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/fuzzing/README.md` | **Security testing for Elspeth using property-based fuzzing (Hypothesis)** | 8.4 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/fuzzing/fuzzing.md` | **Phase 1 (Active)**: [Strategy](./fuzzing.md) • [Roadmap](./fuzzing_plan.md) • [Risk Review](../archive/fuzzing_design_review.md) • [IRAP Risk Acceptance](./fuzzing_irap_risk_acceptance.md) | 34.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/fuzzing/fuzzing_irap_risk_acceptance.md` | **Document Type**: Risk-Based Security Decision with Remediation Plan | 22.0 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |
| `docs/security/fuzzing/fuzzing_plan.md` | This document provides a concise, execution-focused roadmap for **Phase 1** fuzzing (Hypothesis property-based testing). For strategy, targets, oracles, and detailed procedures, see the canonical guide: [fuzzing.md](./fuzzing.md) | 9.5 | 2025-10-25 | 2025-10-25 | 2025-10-25 | 0 |

### testing

#### testing

| File | Purpose (excerpt) | Size (KB) | Created (ctime) | Updated (mtime) | Last Read (atime) | Freshness (days)|
|---|---|---|---|---|---|---|
| `docs/testing/PERFORMANCE_BASELINES.md` | This document defines expected performance baselines for Elspeth's performance regression tests. | 5.7 | 2025-10-23 | 2025-10-23 | 2025-10-26 | 2 |

## Recommendations

- **Create ownership map**: assign a responsible team contact per top-level directory (architecture, security, operations, compliance, migration) to drive periodic reviews.

- **Flag stale documents (>180 days)**: schedule quarterly audits for entries listed with freshness > 180 to confirm continued accuracy or move to `archive/`.

- **Simplify archives**: For directories containing executed plans (e.g. `docs/architecture/archive`, `docs/refactoring/completed`), consider rolling up into summary reports and linking from active playbooks.

- **Add changelog metadata**: Introduce front-matter or standardized headers capturing document owner, status (draft/active/archived), and next review date.

- **Automate indexing**: Generate documentation sitemap or dashboard from this inventory to keep README indices accurate.

- **Normalize security guidance**: There are multiple overlapping risk assessments (e.g., fuzzing) last touched recently; ensure canonical document is clearly indicated in index files to avoid duplication as updates continue.
