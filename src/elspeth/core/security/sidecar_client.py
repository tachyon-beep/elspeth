"""Sidecar daemon client for CVE-ADR-002-A-009 secret isolation.

This module implements the Python client for communicating with the Rust
sidecar security daemon over Unix sockets.

Security Architecture:
- Secrets (construction_token, seal_key) live in separate Rust process
- Communication via Unix socket with CBOR serialization
- HMAC-SHA256 authentication prevents request tampering
- Process boundary isolation prevents Python introspection attacks

Protocol Flow:
1. authorize_construct() → daemon creates grant with TTL
2. redeem_grant() → daemon returns construction_ticket + initial seal
3. compute_seal() → daemon computes seal for frame updates
4. verify_seal() → daemon validates seal integrity

Replaces closure-encapsulated secrets (CVE-ADR-002-A-009 vulnerability)
with OS-enforced process boundary isolation.
"""

import hashlib
import hmac
import socket
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

try:
    import cbor2
except ImportError as e:
    raise ImportError(
        "cbor2 is required for sidecar daemon communication. "
        "Install with: pip install cbor2"
    ) from e


@dataclass
class SidecarConfig:
    """Configuration for sidecar daemon connection."""

    socket_path: Path
    session_key_path: Path
    timeout_secs: float = 5.0


class SidecarClient:
    """Client for communicating with sidecar security daemon.

    Provides methods for authorization, grant redemption, seal computation,
    and seal verification. All secrets remain in the Rust daemon process.

    Security Properties:
    - HMAC-SHA256 request authentication prevents tampering
    - Session key loaded from daemon-created file
    - Unix socket prevents remote access
    - Timeout prevents denial-of-service

    Example:
        config = SidecarConfig(
            socket_path=Path("/run/sidecar/auth.sock"),
            session_key_path=Path("/var/lib/sidecar/session.key")
        )
        client = SidecarClient(config)

        # Authorize construction
        grant_id, expires_at = client.authorize_construct(frame_id, level, digest)

        # Redeem grant
        ticket, seal = client.redeem_grant(grant_id)

        # Compute new seal
        new_seal = client.compute_seal(frame_id, new_level, new_digest)
    """

    def __init__(self, config: SidecarConfig):
        """Initialize client with configuration.

        Args:
            config: Sidecar daemon configuration

        Raises:
            FileNotFoundError: If session key file doesn't exist
            ValueError: If session key is invalid (not 32 bytes)
        """
        self.config = config
        self._session_key = self._load_session_key()

    def _load_session_key(self) -> bytes:
        """Load session key from file.

        Returns:
            32-byte session key

        Raises:
            FileNotFoundError: If session key file doesn't exist
            ValueError: If session key is invalid
        """
        if not self.config.session_key_path.exists():
            raise FileNotFoundError(
                f"Session key not found: {self.config.session_key_path}. "
                "Ensure sidecar daemon is running and has initialized the session key."
            )

        session_key = self.config.session_key_path.read_bytes()

        if len(session_key) != 32:
            raise ValueError(
                f"Invalid session key length: {len(session_key)} bytes (expected 32)"
            )

        return session_key

    def _compute_request_auth(self, request_dict: dict) -> bytes:
        """Compute HMAC-SHA256 authentication for request.

        Args:
            request_dict: Request dictionary without 'auth' field

        Returns:
            32-byte HMAC-SHA256 tag
        """
        # Canonicalize request without auth field
        canonical = self._canonical_bytes_without_auth(request_dict)

        # HMAC-SHA256 authentication
        return hmac.new(self._session_key, canonical, hashlib.sha256).digest()

    def _canonical_bytes_without_auth(self, request_dict: dict) -> bytes:
        """Convert request to canonical CBOR bytes (without auth field).

        Matches Rust implementation in protocol.rs:canonical_bytes_without_auth()

        Args:
            request_dict: Request dictionary

        Returns:
            CBOR-encoded canonical representation
        """
        op = request_dict["op"]

        if op == "authorize_construct":
            # Canonicalize as (frame_id, level, data_digest)
            canonical = (
                request_dict["frame_id"],
                request_dict["level"],
                request_dict["data_digest"],
            )
        elif op == "redeem_grant":
            # Canonicalize as grant_id
            canonical = request_dict["grant_id"]
        elif op == "compute_seal":
            # Canonicalize as (frame_id, level, data_digest)
            canonical = (
                request_dict["frame_id"],
                request_dict["level"],
                request_dict["data_digest"],
            )
        elif op == "verify_seal":
            # Canonicalize as (frame_id, level, data_digest, seal)
            canonical = (
                request_dict["frame_id"],
                request_dict["level"],
                request_dict["data_digest"],
                request_dict["seal"],
            )
        else:
            raise ValueError(f"Unknown operation: {op}")

        return cbor2.dumps(canonical)

    def _send_request(self, request: dict) -> dict:
        """Send CBOR request to daemon and receive response.

        Args:
            request: Request dictionary

        Returns:
            Response dictionary

        Raises:
            ConnectionError: If socket connection fails
            TimeoutError: If request times out
            RuntimeError: If daemon returns error response
        """
        # Compute authentication
        auth = self._compute_request_auth(request)
        request["auth"] = auth

        # Serialize request to CBOR
        request_bytes = cbor2.dumps(request)

        # Connect to Unix socket
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.config.timeout_secs)
            sock.connect(str(self.config.socket_path))

            # Send request
            sock.sendall(request_bytes)

            # Receive response
            response_bytes = sock.recv(4096)

            if not response_bytes:
                raise ConnectionError("Daemon closed connection without response")

            # Deserialize response
            response = cbor2.loads(response_bytes)

            # Check for error response
            if "error" in response:
                raise RuntimeError(
                    f"Daemon error: {response['error']} - {response.get('reason', 'No reason provided')}"
                )

            return response

        except socket.timeout as e:
            raise TimeoutError(
                f"Request timed out after {self.config.timeout_secs}s"
            ) from e
        except OSError as e:
            raise ConnectionError(
                f"Failed to connect to daemon at {self.config.socket_path}: {e}"
            ) from e
        finally:
            sock.close()

    def authorize_construct(
        self, frame_id: UUID, level: int, data_digest: bytes
    ) -> tuple[bytes, float]:
        """Request authorization to construct SecureDataFrame.

        Creates a one-shot grant that can be redeemed within the TTL.

        Args:
            frame_id: UUID identifying the frame
            level: Security level (0-4 for UNOFFICIAL through TOP_SECRET)
            data_digest: 32-byte BLAKE3 digest of canonical Parquet data

        Returns:
            Tuple of (grant_id, expires_at):
            - grant_id: 16-byte one-shot grant handle
            - expires_at: Unix timestamp when grant expires

        Raises:
            ConnectionError: If daemon is unreachable
            RuntimeError: If daemon rejects authorization
        """
        request = {
            "op": "authorize_construct",
            "frame_id": frame_id.bytes,
            "level": level,
            "data_digest": data_digest,
        }

        response = self._send_request(request)

        return response["grant_id"], response["expires_at"]

    def redeem_grant(self, grant_id: bytes) -> tuple[bytes, bytes]:
        """Redeem one-shot grant for construction_ticket + initial seal.

        Consumes the grant (can only be redeemed once) and registers the
        frame for future seal operations.

        Args:
            grant_id: 16-byte grant handle from authorize_construct()

        Returns:
            Tuple of (construction_ticket, seal):
            - construction_ticket: 32-byte capability token
            - seal: 32-byte tamper-evident seal for initial data

        Raises:
            ConnectionError: If daemon is unreachable
            RuntimeError: If grant is invalid/expired/already redeemed
        """
        request = {
            "op": "redeem_grant",
            "grant_id": grant_id,
        }

        response = self._send_request(request)

        return response["construction_ticket"], response["seal"]

    def compute_seal(
        self, frame_id: UUID, level: int, data_digest: bytes
    ) -> bytes:
        """Compute tamper-evident seal for frame data.

        Frame must be registered (via redeem_grant) before seals can be computed.

        Args:
            frame_id: UUID identifying the frame
            level: Security level
            data_digest: 32-byte BLAKE3 digest of canonical Parquet data

        Returns:
            32-byte BLAKE2s-MAC seal

        Raises:
            ConnectionError: If daemon is unreachable
            RuntimeError: If frame is not registered
        """
        request = {
            "op": "compute_seal",
            "frame_id": frame_id.bytes,
            "level": level,
            "data_digest": data_digest,
        }

        response = self._send_request(request)

        return response["seal"]

    def verify_seal(
        self, frame_id: UUID, level: int, data_digest: bytes, seal: bytes
    ) -> bool:
        """Verify tamper-evident seal for frame data.

        Args:
            frame_id: UUID identifying the frame
            level: Security level
            data_digest: 32-byte BLAKE3 digest of canonical Parquet data
            seal: 32-byte seal to verify

        Returns:
            True if seal is valid, False otherwise

        Raises:
            ConnectionError: If daemon is unreachable
            RuntimeError: If frame is not registered
        """
        request = {
            "op": "verify_seal",
            "frame_id": frame_id.bytes,
            "level": level,
            "data_digest": data_digest,
            "seal": seal,
        }

        response = self._send_request(request)

        return response["valid"]
