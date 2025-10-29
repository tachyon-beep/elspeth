"""Integration tests for Python ↔ Rust sidecar daemon communication.

Tests the full end-to-end flow:
1. Start Rust daemon
2. Python SidecarClient connects via Unix socket
3. authorize_construct → redeem_grant → compute_seal → verify_seal
4. SecureDataFrame creation in sidecar mode

Requires:
- Rust daemon binary (cargo build)
- cbor2, blake3, pyarrow packages
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel


@pytest.fixture(scope="module")
def sidecar_daemon():
    """Start sidecar daemon for integration tests.

    Yields:
        Tuple of (socket_path, session_key_path, process)
    """
    # Skip if not in integration test mode
    if not os.environ.get("ELSPETH_RUN_INTEGRATION_TESTS"):
        pytest.skip("Integration tests disabled. Set ELSPETH_RUN_INTEGRATION_TESTS=1 to enable.")

    # Create temporary directory for daemon files
    temp_dir = tempfile.mkdtemp(prefix="sidecar_test_")
    socket_path = Path(temp_dir) / "auth.sock"
    session_key_path = Path(temp_dir) / "session.key"
    config_path = Path(temp_dir) / "sidecar.toml"

    # Write daemon configuration
    config_content = f"""
mode = "sidecar"
socket_path = "{socket_path}"
session_key_path = "{session_key_path}"
appuser_uid = {os.getuid()}
grant_ttl_secs = 60
log_level = "debug"
"""
    config_path.write_text(config_content)

    # Find daemon binary
    daemon_binary = Path(__file__).parent.parent / "sidecar" / "target" / "debug" / "elspeth-sidecar-daemon"

    if not daemon_binary.exists():
        # Try release build
        daemon_binary = Path(__file__).parent.parent / "sidecar" / "target" / "release" / "elspeth-sidecar-daemon"

    if not daemon_binary.exists():
        pytest.skip(f"Daemon binary not found. Run 'cargo build' in sidecar/ directory first.")

    # Start daemon
    # Use DEVNULL to avoid pipe buffer filling (which would block daemon)
    process = subprocess.Popen(
        [str(daemon_binary), str(config_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for daemon to initialize (socket + session key creation)
    max_wait = 5.0
    wait_interval = 0.1
    elapsed = 0.0

    while elapsed < max_wait:
        if socket_path.exists() and session_key_path.exists():
            break
        time.sleep(wait_interval)
        elapsed += wait_interval

    if not (socket_path.exists() and session_key_path.exists()):
        process.kill()
        process.wait(timeout=2.0)
        pytest.fail(
            f"Daemon failed to initialize after {max_wait}s. "
            f"Check that sidecar daemon binary is working correctly."
        )

    yield socket_path, session_key_path, process

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()

    # Remove temporary files
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sidecar_client(sidecar_daemon):
    """Create SidecarClient connected to test daemon.

    Args:
        sidecar_daemon: Daemon fixture

    Returns:
        SidecarClient instance
    """
    socket_path, session_key_path, _ = sidecar_daemon

    from elspeth.core.security.sidecar_client import SidecarClient, SidecarConfig

    config = SidecarConfig(
        socket_path=socket_path,
        session_key_path=session_key_path,
        timeout_secs=5.0
    )

    return SidecarClient(config)


def test_authorize_construct_flow(sidecar_client):
    """Test authorize_construct creates grant."""
    frame_id = uuid4()
    level = 2
    data_digest = b"\xAA" * 32

    grant_id, expires_at = sidecar_client.authorize_construct(
        frame_id=frame_id,
        level=level,
        data_digest=data_digest
    )

    assert len(grant_id) == 16, "Grant ID should be 16 bytes"
    assert isinstance(expires_at, float), "expires_at should be Unix timestamp"
    assert expires_at > time.time(), "Grant should expire in the future"


def test_redeem_grant_flow(sidecar_client):
    """Test redeem_grant consumes grant and returns construction_ticket + seal."""
    frame_id = uuid4()
    level = 3
    data_digest = b"\xBB" * 32

    # Authorize
    grant_id, _ = sidecar_client.authorize_construct(
        frame_id=frame_id,
        level=level,
        data_digest=data_digest
    )

    # Redeem
    construction_ticket, seal = sidecar_client.redeem_grant(grant_id)

    assert len(construction_ticket) == 32, "Construction ticket should be 32 bytes"
    assert len(seal) == 32, "Seal should be 32 bytes"


def test_compute_seal_for_registered_frame(sidecar_client):
    """Test compute_seal works for registered frame."""
    frame_id = uuid4()
    level = 2
    data_digest = b"\xCC" * 32

    # Authorize + redeem to register frame
    grant_id, _ = sidecar_client.authorize_construct(frame_id, level, data_digest)
    sidecar_client.redeem_grant(grant_id)

    # Compute seal for new data
    new_digest = b"\xDD" * 32
    new_level = 3
    seal = sidecar_client.compute_seal(frame_id, new_level, new_digest)

    assert len(seal) == 32, "Seal should be 32 bytes"


def test_compute_seal_for_unregistered_frame_fails(sidecar_client):
    """Test compute_seal fails for unregistered frame."""
    frame_id = uuid4()
    level = 2
    data_digest = b"\xEE" * 32

    # Try to compute seal without registering frame
    with pytest.raises(RuntimeError, match="not registered"):
        sidecar_client.compute_seal(frame_id, level, data_digest)


def test_verify_seal_success(sidecar_client):
    """Test verify_seal validates correct seal."""
    frame_id = uuid4()
    level = 4
    data_digest = b"\xFF" * 32

    # Authorize + redeem
    grant_id, _ = sidecar_client.authorize_construct(frame_id, level, data_digest)
    _, seal = sidecar_client.redeem_grant(grant_id)

    # Verify seal
    valid = sidecar_client.verify_seal(frame_id, level, data_digest, seal)

    assert valid is True, "Seal should be valid"


def test_verify_seal_wrong_digest_fails(sidecar_client):
    """Test verify_seal detects tampered digest."""
    frame_id = uuid4()
    level = 3
    data_digest = b"\x11" * 32

    # Authorize + redeem
    grant_id, _ = sidecar_client.authorize_construct(frame_id, level, data_digest)
    _, seal = sidecar_client.redeem_grant(grant_id)

    # Verify with wrong digest
    wrong_digest = b"\x22" * 32
    valid = sidecar_client.verify_seal(frame_id, level, wrong_digest, seal)

    assert valid is False, "Seal should be invalid for wrong digest"


def test_grant_redemption_is_one_shot(sidecar_client):
    """Test grant can only be redeemed once."""
    frame_id = uuid4()
    level = 2
    data_digest = b"\x33" * 32

    # Authorize
    grant_id, _ = sidecar_client.authorize_construct(frame_id, level, data_digest)

    # First redemption succeeds
    sidecar_client.redeem_grant(grant_id)

    # Second redemption fails
    with pytest.raises(RuntimeError, match="not found|already redeemed"):
        sidecar_client.redeem_grant(grant_id)


def test_invalid_hmac_fails(sidecar_client):
    """Test requests with invalid HMAC are rejected."""
    # Directly construct request with bad auth
    import cbor2
    import socket

    bad_request = {
        "op": "authorize_construct",
        "frame_id": uuid4().bytes,
        "level": 2,
        "data_digest": b"\x44" * 32,
        "auth": b"BAD_AUTH" * 4,  # Invalid HMAC
    }

    request_bytes = cbor2.dumps(bad_request)

    # Send to daemon
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    sock.connect(str(sidecar_client.config.socket_path))
    sock.sendall(request_bytes)

    # Receive response
    response_bytes = sock.recv(4096)
    response = cbor2.loads(response_bytes)

    sock.close()

    # Should get error response
    assert "error" in response, "Should return error for invalid HMAC"
    assert "auth" in response["error"].lower() or "Authentication" in response.get("reason", ""), \
        "Error should mention authentication failure"


def test_securedataframe_sidecar_mode_integration(sidecar_daemon, monkeypatch):
    """Test SecureDataFrame creation in sidecar mode."""
    socket_path, session_key_path, _ = sidecar_daemon

    # Set sidecar mode environment
    monkeypatch.setenv("ELSPETH_SIDECAR_MODE", "sidecar")
    monkeypatch.setenv("ELSPETH_SIDECAR_SOCKET", str(socket_path))
    monkeypatch.setenv("ELSPETH_SIDECAR_SESSION_KEY", str(session_key_path))

    # Force re-detection of sidecar mode
    import elspeth.core.security.secure_data as secure_data_module
    secure_data_module._SIDECAR_MODE = None
    secure_data_module._SIDECAR_CLIENT = None

    from elspeth.core.security.secure_data import SecureDataFrame

    # Create DataFrame
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

    # Create SecureDataFrame in sidecar mode
    frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)

    # Verify frame was created
    assert frame.security_level == SecurityLevel.OFFICIAL
    assert frame._created_by_datasource is True
    assert len(frame._seal) == 32, "Seal should be 32 bytes (from daemon)"
    assert frame._frame_id is not None, "Frame ID should be set"
    assert isinstance(frame._frame_id, type(uuid4())), "Frame ID should be UUID"


def test_securedataframe_standalone_mode_fallback(monkeypatch):
    """Test SecureDataFrame falls back to standalone mode when daemon unavailable."""
    # Set standalone mode
    monkeypatch.setenv("ELSPETH_SIDECAR_MODE", "standalone")

    # Force re-detection
    import elspeth.core.security.secure_data as secure_data_module
    secure_data_module._SIDECAR_MODE = None
    secure_data_module._SIDECAR_CLIENT = None

    from elspeth.core.security.secure_data import SecureDataFrame

    # Create DataFrame
    df = pd.DataFrame({"x": [10, 20, 30]})

    # Create SecureDataFrame in standalone mode
    frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)

    # Verify frame was created
    assert frame.security_level == SecurityLevel.OFFICIAL
    assert frame._created_by_datasource is True
    assert len(frame._seal) == 32, "Seal should be 32 bytes (from closure)"
    assert frame._frame_id is None, "Frame ID should not be set in standalone mode"
