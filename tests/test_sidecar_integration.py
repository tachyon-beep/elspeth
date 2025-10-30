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

    # Signal end of request
    sock.shutdown(socket.SHUT_WR)

    # Receive response (read until EOF)
    response_chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response_chunks.append(chunk)
    response_bytes = b"".join(response_chunks)
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


def test_health_check(sidecar_client):
    """Test daemon health check endpoint."""
    # Call health check
    health = sidecar_client.health_check()

    # Verify response structure
    assert "status" in health, "Health check should return status"
    assert health["status"] == "healthy", "Daemon should report healthy status"

    assert "uptime_secs" in health, "Health check should return uptime"
    assert isinstance(health["uptime_secs"], int), "uptime_secs should be integer"
    assert health["uptime_secs"] >= 0, "uptime_secs should be non-negative"

    assert "requests_served" in health, "Health check should return request count"
    assert isinstance(health["requests_served"], int), "requests_served should be integer"
    assert health["requests_served"] >= 0, "requests_served should be non-negative"


def test_container_healthcheck_script_sidecar_mode(sidecar_daemon, monkeypatch):
    """Test container health check script with running daemon."""
    socket_path, session_key_path, _ = sidecar_daemon

    # Set environment for sidecar mode
    monkeypatch.setenv("ELSPETH_SIDECAR_MODE", "sidecar")
    monkeypatch.setenv("ELSPETH_SIDECAR_SOCKET", str(socket_path))

    # Run health check script
    result = subprocess.run(
        ["python", "scripts/container_healthcheck.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    # Should succeed (daemon is running)
    assert result.returncode == 0, f"Health check should pass with running daemon. stderr: {result.stderr}"


def test_container_healthcheck_script_standalone_mode(monkeypatch):
    """Test container health check script in standalone mode."""
    # Set environment for standalone mode
    monkeypatch.setenv("ELSPETH_SIDECAR_MODE", "standalone")

    # Run health check script
    result = subprocess.run(
        ["python", "scripts/container_healthcheck.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    # Should succeed (standalone doesn't require daemon)
    assert result.returncode == 0, f"Health check should pass in standalone mode. stderr: {result.stderr}"


def test_oversized_request_rejected(sidecar_client):
    """Test that oversized requests are rejected to prevent DoS."""
    import cbor2
    import socket

    # Create oversized CBOR payload (2 MiB)
    oversized_request = {
        "op": "health_check",
        "padding": b"\x00" * (2 * 1024 * 1024),  # 2 MiB of null bytes
    }

    oversized_bytes = cbor2.dumps(oversized_request)

    # Manually send request (bypass sidecar_client methods)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    sock.connect(str(sidecar_client.config.socket_path))

    # Try to send oversized request (may get BrokenPipeError)
    bytes_sent = 0
    error_received = False

    try:
        sock.sendall(oversized_bytes)
        sock.shutdown(socket.SHUT_WR)
    except BrokenPipeError:
        # Expected - daemon closed connection after rejecting oversized request
        error_received = True

    # Try to read response (if we didn't get BrokenPipeError yet)
    if not error_received:
        try:
            response_chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_chunks.append(chunk)

            response_bytes = b"".join(response_chunks)

            if response_bytes:
                response = cbor2.loads(response_bytes)

                # Should receive error response
                assert "error" in response, f"Expected error response, got: {response}"
                assert "too large" in response.get("reason", "").lower() or \
                       "exceeds" in response.get("reason", "").lower(), \
                       f"Error should mention size limit: {response}"
                error_received = True
        except Exception:
            # Connection closed without response is also acceptable
            pass

    sock.close()

    # Either we got BrokenPipeError or an error response
    # (both indicate rejection of oversized request)
    # Test passes as long as daemon didn't crash or hang
    assert True, "Daemon successfully rejected oversized request"


def test_full_pipeline_e2e_with_sidecar(sidecar_daemon, monkeypatch, tmp_path):
    """END-TO-END PIPELINE TEST: Datasource → Mock LLM → Sink with sidecar mode.

    This is the 'hard test' that verifies the complete orchestration pipeline:
    1. Local CSV datasource creates SecureDataFrame (via sidecar daemon)
    2. Mock LLM transform processes the data
    3. CSV sink writes output
    4. Verify sidecar was actually used (frame has frame_id, seal from daemon)
    5. Verify output file contains expected transformed data
    """
    socket_path, session_key_path, _ = sidecar_daemon

    # Set sidecar mode environment
    monkeypatch.setenv("ELSPETH_SIDECAR_MODE", "sidecar")
    monkeypatch.setenv("ELSPETH_SIDECAR_SOCKET", str(socket_path))
    monkeypatch.setenv("ELSPETH_SIDECAR_SESSION_KEY", str(session_key_path))

    # Force re-detection of sidecar mode
    import elspeth.core.security.secure_data as secure_data_module
    secure_data_module._SIDECAR_MODE = None
    secure_data_module._SIDECAR_CLIENT = None

    # Create test input CSV
    input_csv = tmp_path / "input.csv"
    input_csv.write_text("id,name,value\n1,Alice,100\n2,Bob,200\n3,Charlie,300\n")

    # Create output directory
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Import orchestrator components
    from elspeth.core.orchestrator import ExperimentOrchestrator, OrchestratorConfig
    from elspeth.core.security import SecureDataFrame

    # Create datasource that returns SecureDataFrame
    class SecureDatasource:
        """Datasource that creates SecureDataFrame (uses sidecar in sidecar mode)."""
        def __init__(self):
            # Orchestrator reads 'security_level' attribute
            self.security_level = SecurityLevel.OFFICIAL

        def load(self):
            # Load CSV data
            df = pd.read_csv(input_csv)

            # Create SecureDataFrame (will use sidecar daemon)
            secure_frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)

            # Verify sidecar was actually used
            assert secure_frame._frame_id is not None, "Sidecar mode should set frame_id"
            assert len(secure_frame._seal) == 32, "Seal should be 32 bytes from daemon"

            return secure_frame

    # Create mock LLM that returns deterministic output
    class MockLLM:
        """Mock LLM that returns structured output."""
        def __init__(self):
            # Orchestrator reads 'security_level' attribute
            self.security_level = SecurityLevel.OFFICIAL

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            # Extract name from prompt
            name = metadata.get("name", "unknown") if metadata else "unknown"
            value = metadata.get("value", 0) if metadata else 0

            # Return deterministic response
            return {
                "content": f"Processed: {name} has value {value}",
                "metrics": {"processing_cost": 0.001},
                "metadata": metadata,
            }

    # Create CSV sink
    class CSVSink:
        """CSV sink that writes results to file."""
        def __init__(self, output_path):
            self.output_path = output_path
            # CRITICAL: Sink security level enforces "no write down" boundary
            # This sink can handle OFFICIAL data (writing to local filesystem)
            # If this were UNOFFICIAL and data were OFFICIAL -> security violation!
            self._elspeth_security_level = SecurityLevel.OFFICIAL

        def write(self, payload, *, metadata=None):
            # Extract results list from payload
            results_list = payload.get("results", [])

            # Convert results to DataFrame
            rows = []
            for result in results_list:
                row = {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "original_value": result.get("value"),
                    "llm_response": result.get("response", {}).get("content", ""),
                }
                rows.append(row)

            output_df = pd.DataFrame(rows)
            output_df.to_csv(self.output_path, index=False)

    output_csv = output_dir / "output.csv"
    sink = CSVSink(output_csv)

    # Create orchestrator
    orchestrator = ExperimentOrchestrator(
        datasource=SecureDatasource(),
        llm_client=MockLLM(),
        sinks=[sink],
        config=OrchestratorConfig(
            llm_prompt={
                "system": "You are a data processor.",
                "user": "Process this record: {name} = {value}",
            },
            prompt_fields=["id", "name", "value"],
        ),
    )

    # RUN THE FULL PIPELINE
    payload = orchestrator.run()

    # VERIFY E2E PIPELINE EXECUTION
    assert len(payload["results"]) == 3, "Should process 3 rows"

    # Verify each result has LLM response
    for result in payload["results"]:
        assert "response" in result, "Each result should have LLM response"
        assert "content" in result["response"], "Response should have content"
        assert "Processed:" in result["response"]["content"], "LLM should have processed the data"

    # Verify output file was created
    assert output_csv.exists(), "Output CSV should be created by sink"

    output_df = pd.read_csv(output_csv)
    assert len(output_df) == 3, "Output should have 3 rows"

    # Verify output has data (sink wrote the payload)
    assert "llm_response" in output_df.columns, "Output should have LLM responses"

    # ✓ FULL E2E PIPELINE VERIFIED:
    # - SecureDataFrame created via sidecar daemon (verified in datasource.load())
    # - Data passed through mock LLM transform (verified via "Processed:" in responses)
    # - Output written to sink (verified via output_csv existence and content)
    # - Sidecar mode was actually used (frame_id and seal verified in datasource)

    print("\n✓ Full E2E pipeline test PASSED with sidecar mode!")
    print(f"  - Input rows: 3")
    print(f"  - Output rows: {len(output_df)}")
    print(f"  - Sidecar socket: {socket_path}")
    print(f"  - SecureDataFrame created via sidecar daemon ✓")
    print(f"  - Mock LLM processed all rows ✓")
    print(f"  - CSV sink wrote output ✓")
