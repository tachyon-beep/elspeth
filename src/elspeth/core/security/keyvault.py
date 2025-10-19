"""Azure Key Vault helper utilities for retrieving signing materials.

This module is optional at runtime. It attempts to import Azure SDKs only when
used, so environments without Key Vault support are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class KeyVaultSecretRef:
    vault_url: str
    name: str
    version: Optional[str]


def _parse_secret_uri(secret_uri: str) -> KeyVaultSecretRef:
    """Parse a Key Vault secret URI into components.

    Expected form: https://{vault}.vault.azure.net/secrets/{name}/{version?}
    """
    parsed = urlparse(secret_uri)
    if not parsed.scheme.startswith("http") or not parsed.netloc:
        raise ValueError(f"Invalid Key Vault secret URI: {secret_uri}")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "secrets":
        raise ValueError(f"Invalid Key Vault secret URI path: {parsed.path}")
    name = parts[1]
    version = parts[2] if len(parts) > 2 else None
    vault_url = f"{parsed.scheme}://{parsed.netloc}"
    return KeyVaultSecretRef(vault_url=vault_url, name=name, version=version)


def fetch_secret_from_keyvault(secret_uri: str) -> str:
    """Fetch a secret value from Azure Key Vault using DefaultAzureCredential.

    Args:
        secret_uri: Full URI of the secret (may include version)

    Returns:
        The secret value as a string.

    Raises:
        ImportError: When Azure SDK packages are not available.
        ValueError/RuntimeError: On invalid URIs or retrieval failures.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except Exception as exc:  # pragma: no cover - optional dependency guard
        raise ImportError("Azure Key Vault support requires azure-identity and azure-keyvault-secrets") from exc

    ref = _parse_secret_uri(secret_uri)
    cred = DefaultAzureCredential()
    client = SecretClient(vault_url=ref.vault_url, credential=cred)
    if ref.version:
        secret = client.get_secret(ref.name, ref.version)
    else:
        secret = client.get_secret(ref.name)
    value = secret.value
    if not value:
        raise RuntimeError(f"Key Vault secret '{ref.name}' returned no value")
    return str(value)


__all__ = [
    "fetch_secret_from_keyvault",
]
