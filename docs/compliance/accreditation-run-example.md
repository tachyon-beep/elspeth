# Example Accreditation Run Artefact

## Objective

Produce a traceable evidence bundle containing signed results, manifests, and dry-run repository payloads using the built-in `archival` prompt pack (`config/settings.yaml:34-75`) and sample suite configuration (`config/sample_suite/settings.yaml:1`).

## Prerequisites

- Environment variables set for secrets:
  - `ELSPETH_SIGNING_KEY` – signing secret for `signed_artifact` sink (`src/elspeth/plugins/outputs/signed.py:107`, validated by `tests/test_outputs_signed.py:40`).
  - Optional: `GITHUB_TOKEN` / `AZDO_TOKEN` if converting dry-run sinks to live commits (`src/elspeth/plugins/outputs/repository.py:149`).
- Dataset available locally (mock CSV) as configured in sample suite (`config/sample_suite/settings.yaml:4`).
- Virtual environment bootstrapped via `make bootstrap` (`scripts/bootstrap.sh:16`).

## Execution Reference

1. **Select archival prompt pack** – Update or override settings to use the `archival` prompt pack for the target profile. For ad-hoc runs, invoke the CLI with `--profile default --suite-root config/sample_suite --settings config/settings.yaml` and specify `--prompt-pack archival` through configuration overrides.
2. **Enable archival sinks** – Ensure suite defaults or experiment definitions inherit the signed, local bundle, and repository sinks defined in the prompt pack (`config/settings.yaml:55-75`). These include:
   - `signed_artifact` (HMAC manifest)
   - `local_bundle` (JSON bundle for local evidence)
   - `github_repo` / `azure_devops_repo` (dry-run payloads for inspection)
3. **Run sample suite** – Execute `make sample-suite` (uses `config/sample_suite/settings.yaml:1` and `src/elspeth/cli.py:65`) with `ELSPETH_SIGNING_KEY` populated. This drives the orchestration path outlined in the data-flow diagram (`docs/architecture/data-flow-diagrams.md`).
4. **Inspect outputs** – Collect artefacts from:
   - `outputs/bundles/archival` – flattened JSON/CSV (`src/elspeth/plugins/outputs/local_bundle.py`)
   - `outputs/signed/archival_<timestamp>` – `results.json`, `signature.json`, `manifest.json` with cost/aggregates metadata (`src/elspeth/plugins/outputs/signed.py:59`)
   - `outputs/sample_suite_reports` (if reporting enabled)
   - Repository dry-run payload cache recorded in sink instance (`src/elspeth/plugins/outputs/repository.py:70`)

## Evidence Checklist

- **Signed manifests** – Include `signature.json` and `manifest.json` for each run; they encapsulate hash, security level, and generated timestamp (`tests/test_outputs_signed.py:21`).
- **Dry-run payloads** – Export the cached payloads (`self._last_payloads`) to demonstrate what would be pushed to GitHub/Azure DevOps (`src/elspeth/plugins/outputs/repository.py:70`).
- **Logs & telemetry** – Capture middleware channels (`elspeth.audit`, `elspeth.prompt_shield`, `elspeth.azure_content_safety`) if the run employed policy middleware (`src/elspeth/plugins/llms/middleware.py:74`).
- **Configuration snapshot** – Archive the exact `settings.yaml`, suite configs, and environment variable list used for the run (`config/sample_suite/settings.yaml:1`, `config/sample_suite/*/config.json`).

## Accreditation Notes

- This workflow exercises the full security surface: sanitised outputs (`tests/test_sanitize_utils.py:6`), retry metadata (`src/elspeth/core/experiments/runner.py:177`), signed artefacts, and repository manifests, providing a comprehensive audit trail.
- For regulated runs, pair this example with the environment hardening guidance (`docs/architecture/environment-hardening.md`) and threat traceability matrix (`docs/architecture/threat-traceability.md`) to demonstrate defence in depth.
