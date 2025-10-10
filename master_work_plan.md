# Master Work Plan
*Status: Draft v1.1 — Phase 0.1 complete (Azure middleware safety); update after each milestone*

## Guiding Principles
- **Risk-first sequencing**: Address runtime-breaking defects and configuration hazards before expanding scope.
- **Parity then progression**: Restore critical capabilities from the legacy stack prior to new feature investments.
- **Documentation as deliverable**: Every phase culminates in updated docs/tests to keep this plan grounded in reality.

---

## Phase 0 – Immediate Risk Reduction & Triage
**Objective:** Stabilise current deployments by neutralising high-severity hazards.

### Step 0.1 – Azure Middleware Safety
- [x] Task 0.1.1: Audit default profiles for `azure_environment` middleware usage and document where it is implicitly enabled.
- [x] Task 0.1.2: Change middleware defaults to `on_error="skip"` or gate with environment detection.
- [x] Task 0.1.3: Add regression tests ensuring local execution does not raise when run context is missing.
  - *Notes:* Default profiles keep middleware opt-in (sample suite only); middleware now defaults to `on_error="skip"` with Azure-environment heuristics and README/notes updated with usage guidance in lieu of fail-fast behaviour.

### Step 0.2 – Single-Run Plugin Gap
- [x] Task 0.2.1: Reproduce missing plugin execution in single-run mode with automated tests.
- [x] Task 0.2.2: Update `ExperimentOrchestrator` to instantiate row/aggregation/baseline plugins when running standalone.
- [x] Task 0.2.3: Verify CSV output captures metric/baseline data parity with suite mode.
  - *Notes:* Added regression in `tests/test_orchestrator.py` to ensure plugin execution, wired orchestrator to instantiate row/aggregation plugins directly, and expanded single-run CLI CSV export to flatten metrics alongside response content.

### Step 0.3 – Observability of Retries
- [x] Task 0.3.1: Extend retry loop to log and expose attempt metadata in payload failures.
- [x] Task 0.3.2: Create alerting hooks (e.g., logger or middleware callback) for exhausted retries.
- [x] Task 0.3.3: Add unit coverage around retry/backoff sequencing with fault injection.
  - *Notes:* Runner now records structured retry history on success and failure, CLI surfaces retry warnings/columns, Azure middleware logs `llm_retry_exhausted`, and regression tests cover retry history propagation plus middleware callbacks.

*Exit Criteria:* Local CLI runs succeed without Azure context; single-run mode emits plugin outputs; retry diagnostics visible in logs/tests.

---

## Phase 1 – Bug Remediation & Hardening
**Objective:** Resolve non-blocking defects uncovered during risk triage and reinforce regression coverage.

### Step 1.1 – Test Suite Expansion
- [x] Task 1.1.1: Add smoke tests for `src/elspeth/cli.py` covering `--single-run`, `--disable-metrics`, and prompt-pack overrides.
- [x] Task 1.1.2: Introduce golden-data fixtures validating artifact pipeline ordering and security level propagation.
  - *Notes:* CLI suite now exercises metrics stripping, prompt-pack overrides, and failure logging; artifact pipeline test compares execution order and security snapshots against a golden fixture.

### Step 1.2 – Middleware & Controls Consistency
- [x] Task 1.2.1: Ensure cost tracker and rate limiter contexts survive concurrency boundaries (threads).
- [x] Task 1.2.2: Guard middleware lifecycle callbacks against duplicate invocations.
  - *Notes:* Added thread-safe limiter usage in parallel runner, introduced concurrency regression tests, and cached middleware instances so shared hooks fire exactly once per suite.

### Step 1.3 – Configuration UX
- [x] Task 1.3.1: Emit actionable validation errors when prompt packs/middleware names are unknown.
- [x] Task 1.3.2: Document config migration from legacy keys (mapping table in README/notes).
  - *Notes:* Validators now list available prompt packs and middleware when an unknown name is referenced; CLI error output reflects these messages. Added `notes/config-migration.md` and README guidance covering common legacy-to-modern key translations.

*Exit Criteria:* CI includes new tests; middleware and controls behave consistently across execution paths; configuration errors are self-descriptive.

---

## Phase 2 – Feature Parity Restoration
**Objective:** Close the most visible functionality gaps between legacy and refactored stacks.

### Step 2.1 – Early-Stop Heuristics
- [x] Task 2.1.1: Design plugin or middleware interface mirroring `should_stop_early` semantics.
- [x] Task 2.1.2: Implement opt-in early-stop plugin with configurable thresholds.
- [x] Task 2.1.3: Provide suite example demonstrating cost-saving behaviour.

### Step 2.2 – Advanced Analytics Outputs
- [x] Task 2.2.1: Inventory legacy `StatsAnalyzer` capabilities (effect sizes, Bayesian summaries, visualisations).
- [x] Task 2.2.2: Port critical analytics into modular plugins (e.g., effect-size recommendation, power analysis charts).
- [x] Task 2.2.3: Offer optional reporting sink (JSON/Markdown) summarising key analytics for stakeholders.

### Step 2.3 – Operational Monitors
- [x] Task 2.3.1: Recreate `HealthMonitor` functionality as middleware emitting heartbeat metrics.
- [x] Task 2.3.2: Integrate safety manager/prompt shield hooks with new middleware pipeline.

*Exit Criteria:* Early-stop, analytics, and health features available via plugins with documentation and demos.

---

## Phase 3 – Architectural Enhancements & Enablement
**Objective:** Scale the platform sustainably with documentation, tooling, and community adoption.

### Step 3.1 – Documentation & Samples
- [x] Task 3.1.1: Publish migration guide (legacy → plugin architecture) referencing prompt packs, middleware, sinks.
- [x] Task 3.1.2: Expand sample suites covering Azure, local, and hybrid execution paths.

### Step 3.2 – Developer Experience
- [x] Task 3.2.1: Provide scaffolding scripts for generating new plugins with schema stubs.
- [x] Task 3.2.2: Add linting/pre-commit hooks tuned to plugin structure.

### Step 3.3 – Observability & Governance
- [x] Task 3.3.1: Define metrics/logging standards for middleware and sinks (structured log schema).
- [x] Task 3.3.2: Establish release checklist and update this plan after each milestone.

*Exit Criteria:* Updated documentation set, improved DX tooling, and operational playbooks in place; master work plan refreshed with status notes.

---

## Maintenance of this Document
- Update task checkboxes and version header after each completed task set.
- Record deviations (scope changes, deferrals) directly under relevant tasks.
- Review plan quarterly or after major release to reprioritise phases.
