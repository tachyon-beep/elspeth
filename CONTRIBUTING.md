# Contributing to Elspeth

Thanks for investing time in improving Elspeth! This guide outlines the expectations for proposing changes, writing code, and keeping the documentation and artefacts in sync.

## Before You Start

- **Discuss large changes first.** Open an issue or join an existing discussion when planning new plugins, orchestration features, or configuration formats.
- **Check the docs.** Confirm whether a similar capability already exists in `docs/architecture/plugin-catalogue.md` or other references before starting fresh.
- **Security-first mindset.** Features touching datasources, LLM middleware, or sinks must maintain or improve the existing security posture (sanitisation, signing, audit logging).

## Development Workflow

1. **Bootstrap the environment**

   ```bash
   make bootstrap            # or scripts/bootstrap.sh
   source .venv/bin/activate
   pip install -e .[dev]
   ```

2. **Create a feature branch**

   ```bash
   git checkout -b <topic>/<short-description>
   ```

3. **Follow coding standards**

   - Python 3.12, `typing` annotations, 4-space indentation.
   - Run `make lint` (ruff checks/format + pytype) before pushing.
   - Keep functions focused; factor helpers when cognitive complexity warns.
   - Commit messages use imperative style (`Add`, `Fix`, `Refine`).

4. **Run tests**

   ```bash
   python -m pytest -m "not slow"
   python -m pytest --maxfail=1 --disable-warnings  # optional gate
   ```

   Touching analytics, reporting, or suite flows? Regenerate artefacts:

   ```bash
   python -m elspeth.cli \
     --settings config/sample_suite/settings.yaml \
     --suite-root config/sample_suite \
     --reports-dir outputs/sample_suite_reports \
     --head 0
   ```

   Include any relevant artefact checksums or notes when they change.

5. **Update documentation**

   - Add or adjust entries in `docs/` or `docs/architecture/` to reflect new behaviour.
   - Note concurrency, retry, or analytics changes in the architecture docs and release checklist.
   - Keep README snippets in sync with new CLI flags or workflow changes.

6. **Open a pull request**

   - Describe the change, security considerations, and verification commands (`pytest`, `make sample-suite`, CLI runs, etc.).
   - Link related issues or roadmap items.
   - Attach screenshots or artefact diffs when outputs change.

## Reporting Issues

When filing a bug or feature request, include:

- Reproduction steps (configuration snippets, CLI commands, suite files).
- Expected vs. actual results and any artefact paths.
- Environment details (OS, Python version, optional dependency extras).
- Relevant logs (`logs/`, CLI output, or telemetry excerpts).

## Code of Conduct

Elspeth follows the [Contributor Covenant](https://www.contributor-covenant.org/) (v2.1). Please act with respect and empathy. Report unacceptable behaviour through the maintainers or the incident response channels outlined in `docs/architecture/incident-response.md`.

## Thank You

Security-focused orchestration relies on community scrutiny. Whether you are polishing docs, enhancing tests, or building new sinks, we appreciate your help in making Elspeth safer and more capable.
