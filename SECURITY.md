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

## Security Audit Trail

Major security improvements:

- **2025-10-14**: Phase 3 security hardening - removed critical silent defaults
- **2025-10-14**: Added `config/blob_store.yaml` to `.gitignore`
- **2025-10-14**: Created security documentation and configuration templates

## Questions?

For security-related questions, contact the maintainers directly.
