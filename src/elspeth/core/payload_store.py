# src/elspeth/core/payload_store.py
"""
Payload store for separating large blobs from audit tables.

Uses content-addressable storage (hash-based) for:
- Automatic deduplication of identical content
- Integrity verification on retrieval
- Efficient storage of large payloads referenced by multiple rows
"""

import hashlib
import hmac
import re
from pathlib import Path

import elspeth.contracts.payload_store as payload_contracts

__all__ = ["FilesystemPayloadStore"]

# SHA-256 hex digest: exactly 64 lowercase hex characters
# Compiled regex for performance on repeated validation
_SHA256_HEX_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class FilesystemPayloadStore:
    """Filesystem-based payload store.

    Stores payloads in a directory structure using first 2 characters
    of hash as subdirectory for better file distribution.

    Structure: base_path/ab/abcdef123...
    """

    def __init__(self, base_path: Path) -> None:
        """Initialize filesystem store.

        Args:
            base_path: Root directory for payload storage
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path_for_hash(self, content_hash: str) -> Path:
        """Get filesystem path for content hash.

        Validates content_hash format and ensures path containment.

        Args:
            content_hash: Must be a valid SHA-256 hex digest (64 lowercase hex chars)

        Returns:
            Path under base_path for the content

        Raises:
            ValueError: If content_hash is not a valid SHA-256 hex digest
                        or if resolved path escapes base_path
        """
        # Validate hash format - must be exactly 64 lowercase hex characters
        # Per CLAUDE.md Tier 1 rules: crash immediately on invalid audit data
        if not _SHA256_HEX_PATTERN.match(content_hash):
            raise ValueError(f"Invalid content_hash: must be 64 lowercase hex characters, got {repr(content_hash)[:50]}")

        # Construct path using first 2 chars as subdirectory
        path = self.base_path / content_hash[:2] / content_hash

        # Defense in depth: verify path is contained within base_path
        # This catches any edge cases the regex might miss
        try:
            resolved = path.resolve()
            base_resolved = self.base_path.resolve()
            if not resolved.is_relative_to(base_resolved):
                raise ValueError(f"Invalid content_hash: path traversal detected, resolved path {resolved} is not under {base_resolved}")
        except (OSError, ValueError) as e:
            # Path resolution failed - treat as invalid
            raise ValueError(f"Invalid content_hash: path resolution failed for {repr(content_hash)[:50]}") from e

        return path

    def store(self, content: bytes) -> str:
        """Store content and return its hash.

        If file already exists, verifies integrity before returning hash.
        This prevents corrupted files from being silently accepted.

        Raises:
            IntegrityError: If existing file doesn't match expected hash
        """
        content_hash = hashlib.sha256(content).hexdigest()
        path = self._path_for_hash(content_hash)

        if path.exists():
            # BUG #5: Verify existing file matches expected hash
            # Without this check, corrupted files (bit rot, tampering) would be
            # silently accepted, violating Tier-1 audit integrity.
            existing_content = path.read_bytes()
            actual_hash = hashlib.sha256(existing_content).hexdigest()

            # Use timing-safe comparison (same as retrieve())
            if not hmac.compare_digest(actual_hash, content_hash):
                raise payload_contracts.IntegrityError(
                    f"Payload integrity check failed on store: existing file has hash {actual_hash}, expected {content_hash}"
                )
        else:
            # File doesn't exist - write it
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        return content_hash

    def retrieve(self, content_hash: str) -> bytes:
        """Retrieve content by hash with integrity verification.

        Raises:
            KeyError: If content not found
            IntegrityError: If content doesn't match expected hash
        """
        path = self._path_for_hash(content_hash)
        if not path.exists():
            raise KeyError(f"Payload not found: {content_hash}")

        content = path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()

        # Use timing-safe comparison to prevent timing attacks that could
        # allow an attacker to incrementally discover expected hashes
        if not hmac.compare_digest(actual_hash, content_hash):
            raise payload_contracts.IntegrityError(f"Payload integrity check failed: expected {content_hash}, got {actual_hash}")

        return content

    def exists(self, content_hash: str) -> bool:
        """Check if content exists."""
        return self._path_for_hash(content_hash).exists()

    def delete(self, content_hash: str) -> bool:
        """Delete content by hash.

        Returns:
            True if content was deleted, False if not found
        """
        path = self._path_for_hash(content_hash)
        if not path.exists():
            return False
        path.unlink()
        return True
