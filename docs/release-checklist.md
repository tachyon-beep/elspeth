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

## Documentation
7. Update `README.md`, `AGENTS.md`, and relevant docs (migration guide, logging standards) when behaviour changes.
8. Increment plan status in `master_work_plan.md` (mark completed tasks, add notes for deferrals).

## Packaging & Changelog
9. Update `pyproject.toml` version if publishing.
10. Draft release notes summarising major features, bug fixes, and upgrade steps.

## Post-Release
11. Tag the release and push (after manual verification).
12. Archive generated outputs/logs if needed; reset `outputs/` locally.
13. Review telemetry dashboards/alerts to confirm healthy runtime behaviour.
