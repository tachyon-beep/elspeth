# Artifacts, Bundles, and Audit Outputs

This guide describes how Elspeth writes persistent job artifacts for audits and reproducibility.

## Overview

When enabled, Elspeth writes a timestamped folder under `artifacts/` containing:

- `<ts>_single_results.json` or `suite.json` — canonical results payload(s)
- `<ts>_single_settings.yaml` or `settings.yaml` — exact settings used
- Optional: a signed reproducibility bundle under `<name>_bundle/` with:
  - Results (JSON/CSV), datasource snapshot, prompts, plugin code
  - Manifest with SHA256 hashes
  - HMAC signature over the manifest (algorithm configurable)

The `artifacts/` folder is `.gitignore`d by default.

## CLI

- Single run
  - `--artifacts-dir PATH`: base directory for artifacts (default: `artifacts/`)
  - `--signed-bundle`: also create a signed reproducibility bundle
  - `--signing-key-env NAME`: env var for signing key (default: `ELSPETH_SIGNING_KEY`)

- Suite run
  - Same flags as above, with a combined `suite.json` across experiments.

Examples:

```bash
# Single experiment, save artifacts and bundle
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --single-run \
  --artifacts-dir artifacts \
  --signed-bundle

# Suite with reports and bundle
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --artifacts-dir artifacts \
  --signed-bundle
```

## Signing

Elspeth supports both HMAC and asymmetric signatures for local bundles.

Algorithms:

- HMAC: `hmac-sha256` (default), `hmac-sha512`
- Asymmetric: `rsa-pss-sha256`, `ecdsa-p256-sha256`

Key sources (priority order):

1) `key_vault_secret_uri` option or env `ELSPETH_SIGNING_KEY_VAULT_SECRET_URI` / `AZURE_KEYVAULT_SECRET_URI` (Azure Key Vault URI)
2) `key_env` (default: `ELSPETH_SIGNING_KEY`) — HMAC key or PEM private key
3) `COSIGN_KEY` (PEM)

If you use Key Vault, ensure the runtime has `azure-identity` and `azure-keyvault-secrets` and an identity chain for `DefaultAzureCredential`.

Example sink snippet (settings YAML):

```yaml
sinks:
  - plugin: signed
    security_level: OFFICIAL
    options:
      base_path: artifacts/signed
      algorithm: rsa-pss-sha256
      key_vault_secret_uri: ${ELSPETH_SIGNING_KEY_VAULT_SECRET_URI}
      public_key_env: SIGNED_PUBLIC_KEY_PEM
```

Signature file (signature.json) includes:

- `algorithm` (one of the above)
- `signature` (base64)
- `target` (e.g., results.json)
- Optional `key_fingerprint` (SHA256 over the public key in asymmetric modes)

Verification:

- HMAC: recompute over the target with the shared key and compare
- Asymmetric: verify with the corresponding public key (see `verify_signature` in `src/elspeth/core/security/signing.py`)

## Containerized Workflows

In CI, we additionally emit:
- App/runtime SBOM (CycloneDX) for the installed Python environment.
- Image SBOM (CycloneDX) for the built container.
- Grype SARIF for image vulnerabilities (blocked on HIGH by default).

These complement local artifacts and bundles for full supply‑chain transparency.

## Retention & Access

- Treat `artifacts/` as sensitive: may contain input data snapshots and prompts.
- Rotate signing keys per environment and scope them appropriately.
- Retain bundles and SBOMs per your accreditation policies; consider immutability storage for signed bundles.

## Troubleshooting

- “Signing key not provided”: set `ELSPETH_SIGNING_KEY` or pass `--signing-key-env`.
- “No retained source data”: the bundle will serialize the in‑memory DataFrame; prefer enabling datasource retention for perfect fidelity.
