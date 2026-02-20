## Summary

Implement `AwsSecretsManagerLoader` that implements the SecretLoader protocol. This enables AWS-native deployments to use Secrets Manager instead of Azure Key Vault.

## Severity

- Severity: minimal
- Priority: P4
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-3m6

## Details

Should follow same patterns as KeyVaultSecretLoader:
1. Lazy client initialization
2. Per-secret caching
3. Clear error messages

Requires `boto3` optional dependency.

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)

## Affected Subsystems

- `core/security/secret_loader.py`
