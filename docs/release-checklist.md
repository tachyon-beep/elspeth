# Release Checklist

Use this list before shipping a new release. Treat it as a living document;
update as processes evolve.

## Pre-Release Validation
1. **Environment** – create/activate `.venv`, run `pip install -e .[dev]`.
1. **Formatting & linting** – `pre-commit run --all-files` (or `make lint`).
1. **Unit tests** – `python -m pytest` (ensure coverage for new code).
1. **Sample suite** – run `python -m elspeth.cli --settings config/sample_suite/settings.yaml --suite-root config/sample_suite --head 0 --live-outputs` and inspect outputs under `outputs/sample_suite/`.
1. **Analytics report** – confirm `analytics_report` sink generated JSON/Markdown for at least one experiment.
1. **Safety middleware** – spot-check warning logs for `prompt_shield` / `azure_content_safety` to ensure observability standards are met.
1. **Dependency audit** – capture `pip list --format=json` (or `pip-audit`) results and attach to release notes for accreditation evidence; verify optional extras (azure, stats, sinks) remain on patched versions.[^release-deps-2025-10-12]
1. **Concurrency & retry sanity** – run at least one suite with `concurrency.enabled` and `retry.max_attempts>1`, confirming retry summaries and early-stop metadata appear in outputs (`outputs/*/analytics_report.json`).[^release-concurrency-2025-10-12]
1. **Signed artifact verification** – when signed sink is enabled, execute verification helper (`python -m elspeth.tools.verify_signature <bundle>`) or manual HMAC check to ensure keys rotate correctly.[^release-signed-2025-10-12]
1. **Visual analytics check** – when `analytics_visual` sink is configured, open the generated PNG/HTML reports, verify embedded metadata (retry/cost summaries) and confirm files reside in a hardened location.[^release-visual-2025-10-12]
1. **Suite report parity** – run CLI with `--reports-dir` and confirm all consolidated artefacts exist (validation, comparative, recommendations, analytics, visual, Excel); ensure logs list each produced path for audit traceability (`src/elspeth/tools/reporting.py:33`).[^release-suite-report-2025-10-12]
1. **Blob/repository dry-run** – if publishing to external sinks, rerun with `--live-outputs` disabled to confirm dry-run manifests/logs capture target paths without mutating external systems (`src/elspeth/cli.py:344`).[^release-dry-run-2025-10-12]

## Documentation
1. Update `README.md`, `AGENTS.md`, and relevant docs (migration guide, logging standards) when behaviour changes.
1. Increment plan status in `master_work_plan.md` (mark completed tasks, add notes for deferrals).
1. Run `docs/reporting-and-suite-management.md` commands to ensure CLI help text remains accurate; update screenshots or artefact lists if analytics pipeline changed.

## Packaging & Changelog
1. Update `pyproject.toml` version if publishing.
1. Draft release notes summarising major features, bug fixes, and upgrade steps.
1. Reference dependency audit, telemetry updates, and any new optional extras in the changelog to aid security reviewers.

## Post-Release
1. Tag the release and push (after manual verification).
1. Archive generated outputs/logs if needed; reset `outputs/` locally.
1. Review telemetry dashboards/alerts to confirm healthy runtime behaviour.
1. Submit analytics/signed artefact samples to accreditation archive and rotate secrets used during validation.

## Update History
- 2025-10-12 – Update 2025-10-12: Added suite reporting verification and dry-run sink validation steps aligned with new reporting and telemetry flows.
- 2025-10-12 – Added dependency audit, concurrency/retry validation, visual analytics verification, and signed artifact verification steps to align with accreditation checkpoints.
- 2025-10-12 – Update 2025-10-12: Added references to dependency analysis, data-flow concurrency checks, and security controls for signing/visual analytics.

[^release-deps-2025-10-12]: Update 2025-10-12: Dependency audit requirements map to docs/architecture/dependency-analysis.md.
[^release-concurrency-2025-10-12]: Update 2025-10-12: Concurrency validation aligns with docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Parallel Execution Gate).
[^release-signed-2025-10-12]: Update 2025-10-12: Signed artifact verification ties to docs/architecture/security-controls.md (Update 2025-10-12: Artifact Signing).
[^release-visual-2025-10-12]: Update 2025-10-12: Visual analytics checks reference docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation) and docs/reporting-and-suite-management.md (Update 2025-10-12: Visual Analytics Sink).
[^release-suite-report-2025-10-12]: Update 2025-10-12: Suite report parity checkpoints described in docs/reporting-and-suite-management.md (Artefact overview).
[^release-dry-run-2025-10-12]: Update 2025-10-12: Dry-run verification linked to docs/architecture/threat-surfaces.md (Update 2025-10-12: Repository Interfaces) and docs/logging-standards.md (Suite report exports).
