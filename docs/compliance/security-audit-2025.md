# Security Audit: Configuration Files

**Date**: October 14, 2025
**Auditor**: Automated security review
**Status**: ✅ All critical issues resolved

---

## Summary

Comprehensive audit of all configuration files for hardcoded credentials, API keys, SAS tokens, and other secrets.

## Findings

### 🔴 CRITICAL - RESOLVED

#### 1. Expired SAS Token in `config/blob_store.yaml`

**Issue**: File contained an expired SAS token (expired 2025-10-03)
**Risk**: Low (token already expired)
**Resolution**:

- Added `config/blob_store.yaml` to `.gitignore`
- Replaced token with placeholder
- Created `config/blob_store.yaml.template` for reference
- Created `SECURITY.md` with credential management guidelines

**Commit**: `e92607d` - "security: Remove SAS token from config and add security documentation"

### 🟢 PASSED - Environment Variables

All other configuration files correctly use environment variables for sensitive credentials:

| File | Secret Type | Method | Status |
|------|-------------|--------|--------|
| `config/settings.yaml` | Signing key | `key_env: ELSPETH_SIGNING_KEY` | ✅ Secure |
| `config/sample_suite/azure_content_safety_demo/config.json` | API key | `key_env: AZURE_CONTENT_SAFETY_KEY` | ✅ Secure |
| `config/sample_suite/secure_azure_workflow.yaml` | API key | `key_env: AZURE_CONTENT_SAFETY_KEY` | ✅ Secure |
| `config/sample_suite/secure_azure_workflow.yaml` | PAT token | `token_env: AZURE_DEVOPS_PAT` | ✅ Secure |

### 🟡 INFO - Internal IP Address

#### `config/settings_colour_animals.yaml`

**Finding**: Contains local IP address `api_base: http://192.168.1.240:5000`
**Risk**: Low (RFC 1918 private address, not internet-routable)
**Recommendation**: Acceptable for local development config
**Action**: None required (this is a sample/test config)

---

## Files Audited

```
config/
├── blob_store.yaml ⚠️ (now in .gitignore)
├── blob_store.yaml.template ✅ (template only)
├── settings.yaml ✅
├── settings_colour_animals.yaml ℹ️ (contains local IP)
├── settings_prompt_variants.yaml ✅
└── sample_suite/
    ├── azure_content_safety_demo/config.json ✅
    ├── azure_telemetry/config.json ✅
    ├── baseline/config.json ✅
    ├── early_stop_fast_exit/config.json ✅
    ├── early_stop_threshold/config.json ✅
    ├── prompt_shield_demo/config.json ✅
    ├── secure_azure_workflow.yaml ✅
    ├── settings.yaml ✅
    ├── slow_rate_limit_demo/config.json ✅
    ├── variant_prompt/config.json ✅
    └── variant_rate_limit/config.json ✅
```

---

## Patterns Searched

✅ No hardcoded secrets found for:

- `api_key` / `apikey` / `api-key`
- `secret` / `password`
- `token` (except `_env` references)
- `credential`

✅ All sensitive values use `_env` suffix patterns:

- `api_key_env`
- `key_env`
- `token_env`

---

## .gitignore Configuration

Updated `.gitignore` to prevent future credential commits:

```gitignore
# dotenv
.env
.env.*

# Config files with secrets
config/blob_store.yaml

# Orchestration packs (user-specific configs)
/orchestration_packs/*/
```

---

## Recommendations

### ✅ Already Implemented

1. **Environment Variables**: All configs use `_env` suffix for secrets ✅
2. **Template Files**: Created `.template` files for config examples ✅
3. **Gitignore**: Added secret config files to `.gitignore` ✅
4. **Documentation**: Created `SECURITY.md` with best practices ✅

### 📋 Future Enhancements

1. **Pre-commit Hook**: Consider adding a pre-commit hook to detect secrets

   ```bash
   # Example using detect-secrets
   pip install detect-secrets
   detect-secrets scan
   ```

2. **Azure Key Vault Integration**: For production, consider Azure Key Vault

   ```yaml
   llm:
     config: azure_openai_config  # Loads from Key Vault
   ```

3. **Automated Scanning**: Add secret scanning to CI/CD pipeline
   - GitHub: Enable secret scanning alerts
   - Use tools like `truffleHog`, `gitleaks`, or `detect-secrets`

4. **Credential Rotation**: Document credential rotation procedures
   - SAS tokens: ≤ 24 hours
   - API keys: Quarterly rotation
   - PAT tokens: 90-day expiration

---

## Verification Commands

```bash
# Search for potential secrets (excluding env var references)
grep -r "api_key\|secret\|password\|token" config/ \
  --include="*.yaml" --include="*.json" \
  | grep -v "key_env\|token_env\|api_key_env\|#"

# Check gitignore patterns
git status --ignored

# Verify no secrets in git history
git log -p --all -- config/blob_store.yaml | grep "sas_token"
```

---

## Compliance Status

| Control | Status | Notes |
|---------|--------|-------|
| No hardcoded secrets | ✅ Pass | All use environment variables |
| Sensitive files in .gitignore | ✅ Pass | `config/blob_store.yaml` ignored |
| Template files provided | ✅ Pass | `.template` files created |
| Documentation | ✅ Pass | `SECURITY.md` created |
| Historical exposure | ⚠️ Reviewed | Expired token (Oct 3, 2025) |

---

## Sign-off

**Audit Date**: October 14, 2025
**Auditor**: Automated security review
**Status**: All critical issues resolved ✅
**Recommendation**: Safe to merge

**Next Review**: After any new config files are added
