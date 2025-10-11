# Release Checklist

Use this list before shipping a new release. Treat it as a living document;
update as processes evolve.

## Pre-Release Validation
1. **Environment** – create/activate `.venv`, run `pip install -e .[dev]`.
2. **Formatting & linting** – `pre-commit run --all-files` (or `make lint`).
3. **Unit tests** – `python -m pytest` (ensure coverage for new code).
4. **Sample suite** – run `python -m elspeth.cli --settings config/sample_suite/settings.yaml --suite-root config/sample_suite --head 0 --live-outputs` and inspect outputs under `outputs/sample_suite/`.
5. **Analytics report** – confirm `analytics_report` sink generated JSON/Markdown for at least one experiment.
6. **Safety middleware** – spot-check warning logs for `prompt_shield` / `azure_content_safety` to ensure observability standards are met.
7. **Dependency audit** – capture `pip list --format=json` (or `pip-audit`) results and attach to release notes for accreditation evidence; verify optional extras (azure, stats, sinks) remain on patched versions.
8. **Concurrency & retry sanity** – run at least one suite with `concurrency.enabled` and `retry.max_attempts>1`, confirming retry summaries and early-stop metadata appear in outputs (`outputs/*/analytics_report.json`).
9. **Signed artifact verification** – when signed sink is enabled, execute verification helper (`python -m elspeth.tools.verify_signature <bundle>`) or manual HMAC check to ensure keys rotate correctly.
10. **Visual analytics check** – when `analytics_visual` sink is configured, open the generated PNG/HTML reports, verify embedded metadata (retry/cost summaries) and confirm files reside in a hardened location.

## Documentation
7. Update `README.md`, `AGENTS.md`, and relevant docs (migration guide, logging standards) when behaviour changes.
8. Increment plan status in `master_work_plan.md` (mark completed tasks, add notes for deferrals).
9. Run `docs/reporting-and-suite-management.md` commands to ensure CLI help text remains accurate; update screenshots or artefact lists if analytics pipeline changed.

## Packaging & Changelog
9. Update `pyproject.toml` version if publishing.
10. Draft release notes summarising major features, bug fixes, and upgrade steps.
11. Reference dependency audit, telemetry updates, and any new optional extras in the changelog to aid security reviewers.

## Post-Release
11. Tag the release and push (after manual verification).
12. Archive generated outputs/logs if needed; reset `outputs/` locally.
13. Review telemetry dashboards/alerts to confirm healthy runtime behaviour.
14. Submit analytics/signed artefact samples to accreditation archive and rotate secrets used during validation.

## Update History
- 2025-10-12 – Added dependency audit, concurrency/retry validation, visual analytics verification, and signed artifact verification steps to align with accreditation checkpoints.
