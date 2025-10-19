# Security Policy

## Reporting a Security Vulnerability

If you discover a security vulnerability in Elspeth, please email the maintainers directly. Do not open a public issue.

## Configuration File Security

### Blob Storage Configuration

**⚠️ CRITICAL**: Never commit real SAS tokens or credentials to git.

The repository includes a tracked placeholder at `config/blob_store.yaml` for reference only (contains no valid secrets). Actual, environment-specific credentials must not be committed and should live in a local override that is ignored by git. The path `config/blob_store.yaml` is listed in `.gitignore` to prevent accidental commits of real credentials.

**To configure blob storage securely**:

1. Use the template:
   ```bash
   cp config/blob_store.yaml.template config/blob_store.yaml
   ```

2. Add your credentials to a local `config/blob_store.yaml` (ignored by git). Do not modify the placeholder in version control.

3. **Recommended**: Use Azure DefaultAzureCredential (no SAS token needed):
   ```yaml
   default:
     account_name: "your-storage-account"
     container_name: "your-container"
     blob_path: "your-data.csv"
     # Omit sas_token to use DefaultAzureCredential
   ```

4. **Alternative**: Use short-lived SAS tokens (≤ 24 hours):
   ```yaml
   default:
     account_name: "your-storage-account"
     container_name: "your-container"
     blob_path: "your-data.csv"
     sas_token: "your-short-lived-token"
   ```

### Historical Note

Prior to commit `9077b01` (October 14, 2025), `config/blob_store.yaml` was tracked in git and contained an expired SAS token (expired October 3, 2025). This token is no longer valid and cannot access the storage account.

If you have concerns about the historical exposure, consider:
- Rotating any credentials that may have been exposed
- Reviewing Azure storage account access logs
- Using Azure Managed Identities for production workloads

## Environment Variables

Sensitive configuration should be stored in environment variables, not committed to git:

- `AZURE_BLOB_SAS_TOKEN` - Azure blob storage SAS token
- `OPENAI_API_KEY` - OpenAI API key
- `AZURE_OPENAI_API_KEY` - Azure OpenAI API key
- Database connection strings
- Any other credentials

## Security Features

Elspeth includes several built-in security features:

### 1. Security Level Enforcement

All datasources, LLM clients, and sinks must declare explicit `security_level`:
- `public`
- `internal`
- `confidential`
- `restricted`

No silent defaults are allowed (enforced since Phase 3 of data flow migration).

### 2. Artifact Pipeline Security

The artifact pipeline enforces "read-up" restrictions:
- Sinks cannot consume artifacts from higher security classifications
- Each artifact carries security metadata
- Cross-tier access is blocked

### 3. Formula Sanitization

CSV and Excel sinks guard against formula injection:
- Configurable via `sanitize_formulas` and `sanitize_guard`
- Prevents execution of malicious formulas in spreadsheet applications

### 4. Prompt Sanitization

Strict Jinja2 rendering without eval:
- No code execution in templates
- Safe variable substitution only

### 5. Middleware Security

Built-in middleware for security:
- **PII Shield**: Detects and blocks personally identifiable information
- **Classified Material Shield**: Detects and blocks classified markings
- **Azure Content Safety**: Integration with Azure Content Safety API
- **Audit Logger**: Security-aware request/response logging

## Best Practices

### 1. Credential Management

✅ **DO**:
- Use Azure Managed Identities in production
- Use short-lived tokens (≤ 24 hours)
- Store credentials in environment variables
- Use Azure Key Vault for production secrets
- Rotate credentials regularly

❌ **DON'T**:
- Commit credentials to git
- Use long-lived SAS tokens
- Share credentials in documentation
- Hardcode API keys in source code

### 2. Configuration Management

✅ **DO**:
- Use `.template` files for configuration examples
- Add config files with secrets to `.gitignore`
- Document required environment variables
- Use explicit security levels for all plugins

❌ **DON'T**:
- Track config files with real credentials
- Use implicit/default security levels
- Share configuration files containing secrets

### 3. Testing

✅ **DO**:
- Use mock clients for tests
- Use environment variables for integration tests
- Test with expired/invalid credentials to verify error handling

❌ **DON'T**:
- Commit test data with real credentials
- Use production credentials in tests

## Dependency Security

Keep dependencies up to date:

```bash
# Check for known vulnerabilities
pip-audit

# Update dependencies
pip install --upgrade -e .[dev,analytics-visual]
```

## Compliance

Elspeth is designed for responsible LLM experimentation with built-in security controls. See:

- `docs/architecture/security-controls.md` - Control inventory
- `docs/architecture/threat-surfaces.md` - Threat model
- `docs/TRACEABILITY_MATRIX.md` - Requirements traceability

### Signed Artifacts (Local) — HMAC and Asymmetric

Elspeth can produce a signed local artifact bundle for evidence trails. The `SignedArtifactSink` supports:

- HMAC (shared secret): `hmac-sha256` (default), `hmac-sha512`
- Asymmetric (private/public key): `rsa-pss-sha256`, `ecdsa-p256-sha256`

Keys can be provided directly (env var with PEM contents) or fetched from Azure Key Vault.

Environment variables (any of the following):

- `ELSPETH_SIGNING_KEY` — HMAC key, or PEM-encoded private key for asymmetric modes
- `COSIGN_KEY` — Alternative PEM source (for CI parity)
- `ELSPETH_SIGNING_KEY_VAULT_SECRET_URI` or `AZURE_KEYVAULT_SECRET_URI` — Full Key Vault secret URI
  - Example: `https://myvault.vault.azure.net/secrets/elspeth-private/abcd1234`
  - Requires `azure-identity` and `azure-keyvault-secrets` in the runtime environment

Optional public key (to embed a fingerprint in signature.json):

- `SIGNED_PUBLIC_KEY_PEM` (set `public_key_env: SIGNED_PUBLIC_KEY_PEM` on the sink) — PEM-encoded public key

Signed sink options (YAML):

```yaml
  - plugin: signed
    security_level: OFFICIAL
    options:
      base_path: artifacts/signed
      algorithm: rsa-pss-sha256   # or hmac-sha256, ecdsa-p256-sha256, hmac-sha512
      # Direct env key (PEM or HMAC)
      key_env: ELSPETH_SIGNING_KEY
      # or fetch from Key Vault when present (takes precedence if set)
      key_vault_secret_uri: ${ELSPETH_SIGNING_KEY_VAULT_SECRET_URI}
      # Optional: embed public key fingerprint
      public_key_env: SIGNED_PUBLIC_KEY_PEM
```

CLI usage:

```bash
# HMAC example
export ELSPETH_SIGNING_KEY="super-secret-key"

# Asymmetric (RSA) example — PEM as env var
export ELSPETH_SIGNING_KEY="$(cat private.pem)"

# Azure Key Vault example (requires azure-identity + azure-keyvault-secrets)
export ELSPETH_SIGNING_KEY_VAULT_SECRET_URI="https://myvault.vault.azure.net/secrets/elspeth-private/abcd1234"

python -m elspeth.cli --signed-bundle --artifacts-dir artifacts ...
```

Verification: signature.json contains algorithm, signature (base64), target, and an optional `key_fingerprint` (SHA256 over SubjectPublicKeyInfo) for asymmetric modes. You can verify with the matching public key using the `verify_signature` helper (see `src/elspeth/core/security/signing.py`).

### Container Signing & SBOM Attestation

All release images are signed with Sigstore Cosign and include a CycloneDX SBOM attestation.

- Default: Keyless signing via GitHub OIDC (no private key required). The CI workflow grants `id-token: write` and treats signing/attestation as hard gates.
- Internal signing (optional/dual‑sign): Provide either `COSIGN_KMS_URI` (e.g., `awskms://…`, `gcpkms://…`, `azurekeyvault://…`) or `COSIGN_KEY` + `COSIGN_PASSWORD`. CI will prefer KMS/key when present, otherwise it uses keyless.

Verification examples:

```bash
# Keyless (GitHub OIDC)
cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "https://github.com/OWNER/REPO/.*" \
  ghcr.io/OWNER/REPO:TAG

# Internal KMS/key
cosign verify --key awskms://arn:aws:kms:... ghcr.io/OWNER/REPO:TAG

# SBOM attestation (CycloneDX)
cosign verify-attestation --type cyclonedx ghcr.io/OWNER/REPO:TAG | jq
```

Policy: During migration you may accept either signature; eventually enforce internal signing only via your admission policy (e.g., Gatekeeper/Kyverno).

## Security Audit Trail

Major security improvements:

- **2025-10-14**: Phase 3 security hardening - removed critical silent defaults
- **2025-10-14**: Added `config/blob_store.yaml` to `.gitignore`
- **2025-10-14**: Created security documentation and configuration templates

## Questions?

For security-related questions, contact the maintainers directly.
### 6. Path Containment & Atomic Writes

- Local sinks (CSV, Excel, local bundle, ZIP bundle) enforce write-path allowlists
  (default base: `./outputs`) and reject symlinked ancestors/targets to prevent
  path traversal and symlink attacks.
- Files are written atomically via a temporary file followed by `os.replace` to
  avoid partially written artefacts on failure.
- In STRICT deployments, configure sink base directories explicitly and audit
  them in CI.
