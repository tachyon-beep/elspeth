# Azure Key Vault Secrets Example

This example demonstrates ELSPETH's **Azure Key Vault integration** for secure secret management. Instead of storing sensitive credentials in configuration files or environment variables, this pipeline loads them directly from Azure Key Vault at startup.

## What It Does

1. Loads secrets from Azure Key Vault during initialization:
   - API keys and endpoints
   - The ELSPETH fingerprint key (for audit trail integrity)
2. Injects them into environment variables
3. Runs a simple passthrough pipeline to demonstrate the flow
4. Records all secret resolution events in the audit trail with fingerprints (not plaintext secrets)

## Prerequisites

### 1. Azure Key Vault

You need an Azure Key Vault resource. Create one if you don't have it:

```bash
# Create a new Key Vault (if needed)
az keyvault create \
  --name YOUR-VAULT-NAME \
  --resource-group YOUR-RESOURCE-GROUP \
  --location eastus
```

### 2. Azure Authentication

ELSPETH uses Azure's **DefaultAzureCredential**, which checks credentials in this order:

1. **Environment variables** (service principal)
2. **Azure CLI login** (recommended for development)
3. **Managed Identity** (for Azure-hosted workloads)

**For local development**, use Azure CLI login:

```bash
# Login with Azure CLI
az login

# Verify you can access your vault
az keyvault secret show --vault-name YOUR-VAULT-NAME --name test-secret
```

**For production**, use service principal environment variables:

```bash
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
```

Or for Azure-hosted workloads, enable Managed Identity.

### 3. Create Secrets in Key Vault

Add the required secrets to your Key Vault:

```bash
# Generate a random fingerprint key (used for audit integrity)
FINGERPRINT_KEY=$(openssl rand -base64 32)

# Create the secrets
az keyvault secret set \
  --vault-name YOUR-VAULT-NAME \
  --name azure-openai-api-key \
  --value "your-azure-openai-key"

az keyvault secret set \
  --vault-name YOUR-VAULT-NAME \
  --name azure-openai-endpoint \
  --value "https://your-resource.openai.azure.com"

az keyvault secret set \
  --vault-name YOUR-VAULT-NAME \
  --name elspeth-fingerprint-key \
  --value "$FINGERPRINT_KEY"
```

**Note:** The fingerprint key is used to compute HMAC hashes of actual secrets for the audit trail. Only fingerprints are recorded, never plaintext secrets.

## Setup Instructions

### Step 1: Update settings.yaml

Edit `examples/azure_keyvault_secrets/settings.yaml` and replace:

```yaml
vault_url: https://YOUR-VAULT-NAME.vault.azure.net
```

With your actual vault name:

```yaml
vault_url: https://my-vault.vault.azure.net
```

### Step 2: Verify Authentication

Test that you can access your vault:

```bash
# If using Azure CLI login (dev)
az login

# If using service principal (prod)
export AZURE_TENANT_ID="..."
export AZURE_CLIENT_ID="..."
export AZURE_CLIENT_SECRET="..."

# Try to fetch a secret directly
az keyvault secret show --vault-name YOUR-VAULT-NAME --name elspeth-fingerprint-key
```

### Step 3: Run the Pipeline

```bash
# Execute with secret loading from Key Vault
uv run elspeth run -s examples/azure_keyvault_secrets/settings.yaml --execute
```

## How It Works

### Secret Loading Flow

```
┌──────────────────────────────┐
│  1. CLI startup              │
│  Load settings.yaml          │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│  2. Secret resolution        │
│  Check secrets.source        │
│  - "env": use OS environ     │
│  - "keyvault": fetch + inject│
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│  3. Azure Key Vault call     │
│  GET /secrets/secret-name    │
│  Returns secret value        │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│  4. Inject into environ      │
│  os.environ[env_var] = value │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│  5. Run pipeline             │
│  Use injected secrets        │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│  6. Audit trail recording    │
│  Record resolution events    │
│  (with HMAC fingerprints)    │
└──────────────────────────────┘
```

### Timing

- **Secrets loaded**: During CLI initialization (before run creation)
- **Audit recording**: Deferred to after the run is created
- **Fingerprinting**: Only HMAC hashes recorded, not plaintext

## Configuration Reference

### Minimal Config (Azure CLI Login)

```yaml
secrets:
  source: keyvault
  vault_url: https://my-vault.vault.azure.net
  mapping:
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
```

### Full Config (Service Principal)

```yaml
secrets:
  source: keyvault
  vault_url: https://my-vault.vault.azure.net
  mapping:
    AZURE_OPENAI_KEY: azure-openai-api-key
    AZURE_OPENAI_ENDPOINT: azure-openai-endpoint
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
    CUSTOM_API_KEY: my-custom-secret
```

### Supported Secret Names

Map any environment variable name to any Key Vault secret name:

- **Standard format**: `azure-openai-api-key` (hyphens, lowercase)
- **Underscores**: `my_secret_name` (also supported)
- **Mixed case**: `MySecretName` (Key Vault is case-insensitive)

Environment variables must follow shell variable naming rules (uppercase, underscores, alphanumeric).

## Security Considerations

### Secret Handling in Audit Trail

ELSPETH **never stores plaintext secrets** in the audit trail:

1. When a secret is loaded, only the **HMAC fingerprint** is recorded
2. The fingerprint is computed using the ELSPETH fingerprint key
3. To verify a secret hasn't changed: recompute the fingerprint and compare

### Example: Verifying Audit Integrity

```python
import hmac
import hashlib

# From audit trail (fingerprint only, safe to store)
recorded_fingerprint = "abc123..."

# At verification time (with actual secret)
secret_value = "actual-key-value"
fingerprint_key = os.environ["ELSPETH_FINGERPRINT_KEY"]

computed_fingerprint = hmac.new(
    fingerprint_key.encode(),
    secret_value.encode(),
    hashlib.sha256
).hexdigest()

if computed_fingerprint == recorded_fingerprint:
    print("Secret has not been tampered with")
else:
    print("Secret may have been modified")
```

### Best Practices

| Practice | Reason |
|----------|--------|
| **Use Key Vault in production** | Avoids plaintext secrets in config files |
| **Use Azure CLI for dev** | Easy local authentication without service principals |
| **Rotate secrets regularly** | Update in Key Vault; pipeline automatically uses new value next run |
| **Enable Key Vault access policies** | Grant only necessary permissions (get, not list) |
| **Use Managed Identity in Azure** | No credentials in environment variables |
| **Never commit vault URL changes** | Keep vault name in config, not in git history |

## Troubleshooting

### "ClientAuthenticationError: Server failed to authenticate the request"

**Cause**: DefaultAzureCredential cannot find valid credentials

**Solution**:
```bash
# Check Azure CLI login
az account show

# If not logged in:
az login

# If using service principal, verify environment variables:
echo $AZURE_TENANT_ID
echo $AZURE_CLIENT_ID
echo $AZURE_CLIENT_SECRET
```

### "ResourceNotFoundError: The specified vault does not exist"

**Cause**: vault_url is incorrect or resource is in different region

**Solution**:
```bash
# List your vaults
az keyvault list --output table

# Update settings.yaml with correct URL
vault_url: https://YOUR-VAULT-NAME.vault.azure.net
```

### "ResourceNotFoundError: The specified secret does not exist"

**Cause**: Secret name in mapping doesn't exist in vault

**Solution**:
```bash
# List secrets in vault
az keyvault secret list --vault-name YOUR-VAULT-NAME --output table

# Create the missing secret
az keyvault secret set \
  --vault-name YOUR-VAULT-NAME \
  --name my-secret \
  --value "secret-value"
```

### "Forbidden: Access denied" or "not authorized"

**Cause**: Current identity doesn't have permission to read secrets

**Solution**:
```bash
# Grant current user permission
# For service principal:
az keyvault set-policy \
  --name YOUR-VAULT-NAME \
  --spn $AZURE_CLIENT_ID \
  --secret-permissions get

# For Azure CLI user:
az keyvault set-policy \
  --name YOUR-VAULT-NAME \
  --upn $(az account show --query user.name -o tsv) \
  --secret-permissions get
```

## Migration Guide: From Old ELSPETH_KEYVAULT_URL

This example uses the new **settings.yaml-based secret loading**, which is different from the old `ELSPETH_KEYVAULT_URL` environment variable approach.

### Old Approach (Deprecated)

```bash
export ELSPETH_KEYVAULT_URL="https://my-vault.vault.azure.net"
export ELSPETH_KEYVAULT_SECRET_NAME="elspeth-fingerprint-key"
# Only the fingerprint key was loaded
```

### New Approach (Recommended)

```yaml
# settings.yaml
secrets:
  source: keyvault
  vault_url: https://my-vault.vault.azure.net
  mapping:
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
    # Can load any other secrets too:
    AZURE_OPENAI_KEY: azure-openai-api-key
    CUSTOM_API_KEY: my-custom-secret
```

### Benefits of New Approach

| Aspect | Old | New |
|--------|-----|-----|
| **Multiple secrets** | No, only fingerprint key | Yes, unlimited secrets |
| **Configuration** | Environment variables | Pipeline config (settings.yaml) |
| **Flexibility** | Fixed secret names | Custom mapping |
| **Audit trail** | No recording | Full resolution audit trail |
| **Development** | ENV fallback only | ENV fallback option |

### Migration Steps

1. **Option A: Minimal (fingerprint only)**
   ```yaml
   secrets:
     source: keyvault
     vault_url: https://my-vault.vault.azure.net
     mapping:
       ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
   ```

2. **Option B: Comprehensive (all secrets)**
   ```yaml
   secrets:
     source: keyvault
     vault_url: https://my-vault.vault.azure.net
     mapping:
       ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
       AZURE_OPENAI_KEY: azure-openai-api-key
       AZURE_OPENAI_ENDPOINT: azure-openai-endpoint
   ```

3. **Option C: Development with ENV fallback**
   ```yaml
   secrets:
     source: env  # Uses environment variables
     # mapping is optional when source is 'env'
   ```
   Then:
   ```bash
   export ELSPETH_FINGERPRINT_KEY="dev-key-12345"
   uv run elspeth run -s settings.yaml --execute
   ```

## Audit Trail

The pipeline records all secret resolution events in the audit trail. Query them with the Landscape MCP tools:

```bash
# Run the MCP server
uv run elspeth-mcp --database examples/azure_keyvault_secrets/runs/audit.db

# In the MCP prompt:
> list_operations(run_id="<run-id>", operation_type="source_load")

# Or query directly for secret resolution events
> query(sql="SELECT env_var_name, source, vault_url, latency_ms FROM secret_resolutions WHERE run_id = '<run-id>'")
```

## Files

| File | Purpose |
|------|---------|
| `settings.yaml` | Pipeline configuration with Key Vault mapping |
| `input/data.csv` | Sample input data (5 simple rows) |
| `output/results.csv` | Output after pipeline runs |
| `runs/audit.db` | Audit trail database (created on first run) |
| `README.md` | This file |

## Next Steps

- **Integrate with LLM transforms**: Add `azure_openai` transform that uses the loaded API key
- **Custom secret mappings**: Add your own secrets to Key Vault and configure mappings
- **Production deployment**: Use Managed Identity instead of CLI login
- **Verify audit trail**: Use Landscape MCP tools to inspect secret resolution records
