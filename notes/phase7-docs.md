# Phase 7 – Tooling & Documentation Recon

## Current State
- No top-level README describing the new architecture, CLI workflow, or plugin configuration.
- Notes folder contains detailed design docs (`plugin-architecture.md`, phase-specific memos) but nothing consumable for onboarding.
- `AGENTS.md` targets internal agents; lacks user-facing instructions.
- Sample suite absent; existing configs only demonstrate whimsical prompt pack.
- Bootstrap steps (venv activation, installing extras, running CLI) rely on tribal knowledge; `.venv` exists but no script/Makefile.

## Requirements
1. **Sample Suite**
   - Demonstrate datasource → prompt packs → metrics → sinks flow with CSV outputs.
   - Include multiple experiments (baseline + variants) exercising prompt defaults, criteria, plugins, and sinks.
   - Provide a README snippet explaining how to run it via CLI.
2. **Bootstrap Tooling**
   - Script/Makefile target to create/refresh `.venv`, install project (editable) plus dev deps, and run smoke tests.
   - Include `.env.example` guidance (already present) and mention required secrets (Azure blob SAS, OpenAI key, signing key).
3. **Documentation**
   - New top-level `README.md` summarising architecture, setup, running experiments, configuring plugins, and extending sinks/metrics.
   - Update notes/AGENTS to reference new bootstrap scripts and sample suite.
   - Document prompt templating capabilities introduced in Phase 5/6.
4. **Verification Guidance**
   - Outline regression approach (e.g., sample suite output diff, prompt rendering checks) for future releases.

## Risks / Considerations
- Ensure bootstrap script respects existing `.venv` without clobbering user customisations; default to idempotent install.
- Sample suite should avoid hitting live Azure/OpenAI by default – use mock datasource or provide placeholder config referencing CSV.
- Document environment variable expectations clearly to avoid accidental secret leakage in git.

## Implementation Summary
- Sample suite created under `config/sample_suite/` (local CSV datasource, mock LLM, metrics and sink plugins) with accompanying README.
- Bootstrap tooling provided via `scripts/bootstrap.sh` and `Makefile` targets (`bootstrap`, `sample-suite`, `test`).
- New `README.md` documents architecture, setup, templating, and plugin usage; `AGENTS.md` updated for internal onboarding.
- Regression guidance captured via sample suite run (`make sample-suite`) and full pytest run.
- Safety/audit behaviour restored via LLM middleware (audit logger, prompt shield) and concurrency-aware execution paired with adaptive rate limiting.

## Open Threads
- Azure ML telemetry/logging from the legacy suite has not yet been reintroduced.
- DevOps/Excel/zip archiving flows remain to be ported.
- Advanced statistical analysis (Bayesian/effect size) still pending.
- Schema/preflight validation and helper CLI hooks to be carried over.
