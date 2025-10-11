# Environment Hardening Guide

## Secrets & Credentials
- **Environment variables only** – LLM clients, repository sinks, and signing bundles read credentials from `*_env` keys (e.g., `ELSPETH_SIGNING_KEY`, `AZURE_CS_KEY`), never static YAML (`src/elspeth/plugins/llms/middleware.py:214`, `src/elspeth/plugins/outputs/signed.py:107`, `src/elspeth/plugins/outputs/repository.py:149`). Use managed secret stores or OS keychains to populate these variables at launch.
- **Managed identity support** – When SAS tokens are absent, blob datasources fall back to `DefaultAzureCredential`, enabling least-privilege access via Azure AD (`src/elspeth/datasources/blob_store.py:125`). Grant the workstation or compute identity read-only blob roles scoped to the dataset container.
- **Legacy compatibility** – The signing sink warns when the deprecated `DMP_SIGNING_KEY` is used (`src/elspeth/plugins/outputs/signed.py:119`, `tests/test_outputs_signed.py:59`); disable legacy env vars in hardened deployments to avoid confusion.

## Network Controls
- **Outbound allowlist** – The only direct network calls originate from HTTP LLM clients, Azure Content Safety, repository sinks, and blob uploads (`src/elspeth/plugins/llms/openai_http.py:43`, `src/elspeth/plugins/llms/middleware.py:249`, `src/elspeth/plugins/outputs/repository.py:168`, `src/elspeth/plugins/outputs/blob.py:130`). Restrict egress to the relevant Azure endpoints and repository hosts.
- **Timeouts & retries** – All HTTP interactions expose configurable timeouts or honor retry wrappers, limiting long-lived connections (`src/elspeth/plugins/llms/openai_http.py:19`, `src/elspeth/core/experiments/runner.py:472`). Align proxy timeouts with these values to avoid premature disconnects.
- **Audit channels** – Middleware logs to named channels (`elspeth.audit`, `elspeth.prompt_shield`, `elspeth.azure_content_safety`, `elspeth.health`) (`src/elspeth/plugins/llms/middleware.py:74`, `src/elspeth/plugins/llms/middleware.py:226`). Route these loggers to central SIEM sinks for anomaly detection.

## Filesystem & Artifact Policies
- **Output directories** – Sinks write to configurable base paths; enforce filesystem ACLs so only the orchestration user can read/write `outputs/` (`src/elspeth/plugins/outputs/local_bundle.py`, `src/elspeth/plugins/outputs/signed.py:37`).
- **Signed manifest storage** – Preserve manifests and signatures as accreditation evidence; store them in append-only vaults post-run (`tests/test_outputs_signed.py:21`).
- **Dry-run repositories** – Keep `dry_run: true` for GitHub/Azure DevOps sinks in non-production to prevent accidental pushes (`config/settings.yaml:64`, `src/elspeth/plugins/outputs/repository.py:70`). When enabling live commits, issue scoped PATs with write-only permissions.

## Classification & Data Segregation
- **Security levels propagate** – Datasources and sinks normalise classification labels (`src/elspeth/plugins/datasources/csv_local.py:35`, `src/elspeth/core/artifact_pipeline.py:192`). Assign clearance to sink definitions via `security_level` and ensure pipeline consumers cannot escalate privileges.
- **Prompt packs with classified sinks** – The `archival` prompt pack demonstrates concurrent signed, bundle, and repository sinks for high-assurance exports (`config/settings.yaml:34-75`). Adapt this model for sensitive suites and confirm each sink inherits the appropriate classification.

## Middleware & Validation Defaults
- **Baseline enforcement** – Enable `prompt_shield` and `azure_content_safety` middleware stacks for regulated suites to ensure pre-flight screening (`config/sample_suite/prompt_shield_demo/config.json:8`, `config/sample_suite/azure_content_safety_demo/config.json:12`).
- **Fail-fast validation** – Use `validation_plugins` such as `regex_match` or `json` to reject malformed model output at runtime (`src/elspeth/plugins/experiments/validation.py:20`, `tests/test_validation_plugins.py`). Accreditation scenarios should standardise which validations are mandatory.

## Runtime User Separation
- **Non-root execution** – When packaging as a desktop or container workload, run the CLI as a dedicated service account without administrative privileges. The codebase never requires elevated file writes outside the working directory (`Makefile:1`, `scripts/bootstrap.sh:3`), simplifying sandboxing.
- **Checkpoint hygiene** – If checkpointing is enabled (`ExperimentRunner.checkpoint_config`), store the JSONL file on encrypted local disks and clear it after successful runs (`src/elspeth/core/experiments/runner.py:70`).
