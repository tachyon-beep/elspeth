# Ad‑hoc Job Configs

Elspeth can run simple ad‑hoc jobs that assemble a datasource, optional LLM transform (with prompts and middlewares), and one or more sinks, without a full suite configuration.

## Minimal schema

```yaml
job:
  security_level: OFFICIAL
  determinism_level: high
  datasource:
    plugin: csv_local
    security_level: OFFICIAL
    options: { path: data.csv, retain_local: true }
  llm:
    plugin: mock
    security_level: OFFICIAL
    options: { seed: 42 }
  prompt:
    system: "..."
    user: "..."
    fields: [A, B, C]
  llm_middlewares:
    - name: prompt_shield
      options: {}
  # If middlewares are declared and are critical for this job, require them.
  # When true and initialization fails, the job will fail-fast instead of degrading.
  llm_middlewares_required: false
  sinks:
    - plugin: csv
      security_level: OFFICIAL
      options: { path: outputs/job_results.csv }
```

- `llm` and `prompt` are optional together. If `llm` is omitted, rows are written as-is to sinks.
- `security_level`/`determinism_level` propagate through the job context.

## Run

```bash
python -m elspeth.cli --job-config config/jobs/sample_job.yaml --head 5 \
  --artifacts-dir artifacts --signed-bundle
```

This produces results and optional signed bundle under `artifacts/<timestamp>/`.

## Notes

- Middlewares are supported via the existing registry (`llm_middlewares`). Use `llm_middlewares_required: true`
  to fail-fast if one or more middlewares cannot be initialized; otherwise the job degrades gracefully and
  continues with `runner.llm_middlewares = []`.
- Failure semantics: the job payload always includes `failures` (list), even when empty; aggregators included
  under `payload["aggregates"]` also include `failures` (the runner normalizes this for consistency).
- Sinks use the standard sink registry and may include local CSV/Excel/ZIP, repository, blob, etc.
- Signing options for bundles:
  - HMAC: `export ELSPETH_SIGNING_KEY="super-secret"`
  - Asymmetric (RSA/ECDSA): `export ELSPETH_SIGNING_KEY="$(cat private.pem)"`
  - Azure Key Vault: `export ELSPETH_SIGNING_KEY_VAULT_SECRET_URI="https://<vault>.vault.azure.net/secrets/<name>/<version?>"`
    - Requires `azure-identity` and `azure-keyvault-secrets` installed
  - Optional public key for fingerprint: `export SIGNED_PUBLIC_KEY_PEM="$(cat public.pem)"` and set `public_key_env: SIGNED_PUBLIC_KEY_PEM` in sink options.

## Container usage

Build and run using the multi-stage Dockerfile.

```bash
# Build devtest image (runs pytest by default)
docker build --target dev -t elspeth:devtest .

# Run tests in container (explicit)
docker run --rm elspeth:devtest pytest -m "not slow" --maxfail=1 --disable-warnings

# Build runtime image
docker build --target runtime -t elspeth:runtime .

# Use runtime image to execute the CLI with a mounted workspace
docker run --rm \
  -e ELSPETH_SIGNING_KEY="$ELSPETH_SIGNING_KEY" \
  -v "$PWD:/workspace" -w /workspace \
  elspeth:runtime \
  python -m elspeth.cli --job-config config/jobs/sample_job.yaml \
    --artifacts-dir artifacts --signed-bundle --head 0
```
