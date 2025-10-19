"""Sink that produces locally signed artifacts."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.security import generate_signature, public_key_fingerprint
from elspeth.core.security.keyvault import fetch_secret_from_keyvault
from elspeth.core.security.secure_mode import SecureMode, get_secure_mode

logger = logging.getLogger(__name__)


@dataclass
class SignedArtifactSink(ResultSink):
    base_path: str | Path
    bundle_name: str | None = None
    timestamped: bool = True
    results_name: str = "results.json"
    signature_name: str = "signature.json"
    manifest_name: str = "manifest.json"
    algorithm: Literal["hmac-sha256", "hmac-sha512", "rsa-pss-sha256", "ecdsa-p256-sha256"] = "hmac-sha256"
    key: str | bytes | None = None
    key_env: str | None = "ELSPETH_SIGNING_KEY"
    public_key_env: str | None = None
    key_vault_secret_uri: str | None = None
    on_error: str = "abort"

    def __post_init__(self) -> None:
        self.base_path: Path = Path(self.base_path)
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        try:
            if get_secure_mode() == SecureMode.STRICT and self.on_error == "skip":
                raise ValueError("SignedArtifactSink cannot use on_error='skip' in STRICT mode")
        except Exception as exc:
            logger.debug("Secure mode check unavailable; proceeding (reason: %s)", exc, exc_info=False)

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        try:
            plugin_logger = getattr(self, "plugin_logger", None)
            if plugin_logger:
                plugin_logger.log_event(
                    "sink_write_attempt",
                    message=f"Signed artifact write attempt: {self.base_path}/{self.bundle_name or 'signed'}",
                    metadata={"path": str(self.base_path)},
                )
            bundle_dir = self._resolve_bundle_dir(metadata, timestamp)
            bundle_dir.mkdir(parents=True, exist_ok=True)

            results_path = bundle_dir / self.results_name
            results_bytes = json.dumps(results, indent=2, sort_keys=True).encode("utf-8")
            results_path.write_bytes(results_bytes)

            key = self._resolve_key()
            signature_value = generate_signature(results_bytes, key, algorithm=self.algorithm)
            key_fp = None
            # For asymmetric signing, compute a public key fingerprint if possible
            if self.algorithm.startswith("rsa-") or self.algorithm.startswith("ecdsa-"):
                pub_pem = os.getenv(self.public_key_env) if self.public_key_env else None
                # If public key not provided, attempt to derive from private PEM (best-effort)
                if not pub_pem:
                    try:
                        if isinstance(key, (bytes, bytearray)):
                            if b"BEGIN PUBLIC KEY" in key:
                                pub_pem = key  # bytes OK
                        else:
                            if "BEGIN PUBLIC KEY" in key:
                                pub_pem = key  # str OK
                    except TypeError:
                        # If key type is unexpected, skip fingerprint derivation gracefully
                        pub_pem = None
                if pub_pem:
                    try:
                        key_fp = public_key_fingerprint(pub_pem)
                    except Exception:  # nosec - optional
                        key_fp = None
            signature_payload = {
                "algorithm": self.algorithm,
                "signature": signature_value,
                "generated_at": timestamp.isoformat(),
                "target": self.results_name,
            }
            if key_fp:
                signature_payload["key_fingerprint"] = key_fp
            signature_path = bundle_dir / self.signature_name
            signature_path.write_text(json.dumps(signature_payload, indent=2, sort_keys=True), encoding="utf-8")

            manifest = self._build_manifest(results, metadata, timestamp, signature_value)
            manifest_path = bundle_dir / self.manifest_name
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            if plugin_logger:
                total_bytes = 0
                for p in (results_path, signature_path, manifest_path):
                    try:
                        total_bytes += p.stat().st_size
                    except Exception:  # nosec B110 - tolerate stat() errors; do not block artifact write
                        pass
                plugin_logger.log_event(
                    "sink_write",
                    message=f"Signed artifact written under {bundle_dir}",
                    metrics={"bytes": total_bytes, "files": 3},
                    metadata={"path": str(bundle_dir)},
                )
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Signed artifact sink failed; skipping bundle creation: %s", exc)
                plugin_logger = getattr(self, "plugin_logger", None)
                if plugin_logger:
                    plugin_logger.log_error(exc, context="signed artifact sink write", recoverable=True)
                return
            raise

    def _resolve_bundle_dir(self, metadata: dict[str, Any], timestamp: datetime) -> Path:
        name = self.bundle_name or str(metadata.get("experiment") or metadata.get("name") or "signed")
        if self.timestamped:
            stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
            name = f"{name}_{stamp}"
        # base_path is guaranteed to be Path after __post_init__
        return Path(self.base_path) / name

    def _build_manifest(
        self,
        results: dict[str, Any],
        metadata: dict[str, Any],
        timestamp: datetime,
        signature: str,
    ) -> dict[str, Any]:
        digest = self._hash_results(results)
        manifest = {
            "generated_at": timestamp.isoformat(),
            "rows": len(results.get("results", [])),
            "metadata": metadata,
            "signature": {
                "algorithm": self.algorithm,
                "value": signature,
                "target": self.results_name,
            },
            "digest": digest,
        }
        if "aggregates" in results:
            manifest["aggregates"] = results["aggregates"]
        if "cost_summary" in results:
            manifest["cost_summary"] = results["cost_summary"]
        return manifest

    @staticmethod
    def _hash_results(results: dict[str, Any]) -> str:
        import hashlib

        payload = json.dumps(results, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _resolve_key(self) -> str | bytes:
        if self.key:
            return self.key
        if self.key_env:
            env_value = os.getenv(self.key_env)
            if env_value:
                self.key = env_value
                return env_value
            # Legacy fallback for pre-rebrand deployments
            # TODO(v2.0): Remove DMP_SIGNING_KEY backward compatibility
            if self.key_env == "ELSPETH_SIGNING_KEY":
                legacy_env = os.getenv("DMP_SIGNING_KEY")
                if legacy_env:
                    logger.warning("Using legacy DMP_SIGNING_KEY environment variable; please migrate to ELSPETH_SIGNING_KEY")
                    self.key = legacy_env
                    return legacy_env
        # Additional fallback for asymmetric/KMS-style env keys often used in CI
        alt = os.getenv("COSIGN_KEY")
        if alt:
            self.key = alt
            return alt
        # Key Vault secret URI support (direct or via env variables)
        kv_uri = self.key_vault_secret_uri or os.getenv("ELSPETH_SIGNING_KEY_VAULT_SECRET_URI") or os.getenv("AZURE_KEYVAULT_SECRET_URI")
        if kv_uri:
            pem = fetch_secret_from_keyvault(kv_uri)
            self.key = pem
            return pem
        raise ValueError("Signing key not provided; set 'key' or environment variable")

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - placeholder for artifact chaining
        return []

    def consumes(self) -> list[str]:  # pragma: no cover - placeholder for artifact chaining
        return []

    def finalize(
        self, artifacts: Mapping[str, Artifact], *, metadata: dict[str, Any] | None = None
    ) -> None:  # pragma: no cover - optional cleanup
        return None
