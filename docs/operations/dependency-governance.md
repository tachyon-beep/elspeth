# Dependency Governance

This note captures the workflow for maintaining deterministic Python
dependencies and generating compliance artefacts.

## Locked Requirements

- Runtime and developer dependencies are pinned in `requirements.lock` and
  `requirements-dev.lock`, generated with
  ```bash
  pip-compile --resolver=backtracking --generate-hashes pyproject.toml
  pip-compile --resolver=backtracking --generate-hashes --extra dev pyproject.toml
  ```
- `scripts/bootstrap.sh` uses `python -m piptools sync` to install the dev lockfile,
  ensuring local virtualenvs match the pinned set exactly.
- When dependencies change, regenerate both lockfiles and rerun
  `make sbom` + `make audit` before committing.
- Optional extras receive their own locks:
  * `requirements-azure.lock` captures runtime deps + Azure ML extras.
  * `requirements-dev-azure.lock` combines dev tooling with Azure ML extras.
  Use `python -m piptools sync` (or `pip install --require-hashes`) against the
  appropriate lockfile before installing the editable package.

## CI Automation

- `.github/workflows/ci.yml` installs dependencies with `python -m piptools sync
  requirements-dev.lock`, runs `make lint`, `pytest` (coverage enabled),
  `make sbom`, and `pip-audit -r requirements.lock`.
- Generated artefacts (`coverage.xml`, `sbom.json`, `pip-audit.json`) are
  uploaded via `actions/upload-artifact` for every run.
- A `gitleaks` secret scan job runs before lint/tests to fail fast on
  credential leaks.

## Verification Commands

- `make audit` runs `pip-audit` against `requirements.lock` with hash
  enforcement and should be run in CI.
- `make sbom` produces `sbom.json` (CycloneDX 1.6, JSON) from the runtime
  lockfile. Re-run whenever dependencies change, and attach to governance
  packets.

## Release Checklist Additions

1. Regenerate lockfiles via `pip-compile`.
2. Run `make audit` and capture the “No known vulnerabilities” output.
3. Run `make sbom` and archive the resulting `sbom.json`.
4. Submit both artefacts with the release evidence bundle.

Future work: wire `make audit` and `make sbom` into CI, and store
artefacts alongside test reports for every mainline build.
