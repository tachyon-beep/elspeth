"""Coverage tests for SignedArtifactSink to reach 80% coverage.

Focuses on uncovered lines:
- Line 39: Invalid on_error value
- Line 52: plugin_logger event logging
- Line 71-86: Public key fingerprint derivation
- Line 94: Key fingerprint in signature payload
- Line 102-108: File size calculation in logging
- Line 119, 121: Error recovery with on_error='skip'
- Line 151, 153: Aggregates and cost_summary in manifest
- Line 166: Key resolution from env/keyvault
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create temporary output directory."""
    output_dir = tmp_path / "signed_outputs"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def sample_results():
    """Sample results data."""
    return {
        "results": [
            {"input": "test1", "output": "result1"},
            {"input": "test2", "output": "result2"},
        ],
        "aggregates": {
            "score_stats": {"criteria": {"accuracy": {"mean": 0.85}}}
        },
        "cost_summary": {
            "total_cost": 1.23,
            "total_tokens": 1000,
        }
    }


def test_invalid_on_error_raises():
    """Test that invalid on_error raises ValueError - line 39."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        SignedArtifactSink(
            base_path="/tmp/test",
            on_error="invalid"
        )


def test_plugin_logger_event_logging(temp_output_dir, sample_results, monkeypatch):
    """Test plugin_logger event logging - lines 52, 102-108."""
    # Set signing key
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-secret-key")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        bundle_name="test_bundle",
        timestamped=False,
    )

    # Mock plugin_logger
    mock_logger = MagicMock()
    sink.plugin_logger = mock_logger

    metadata = {"experiment": "test_exp"}
    sink.write(sample_results, metadata=metadata)

    # Check that log_event was called for write attempt
    assert mock_logger.log_event.call_count == 2

    # First call: write attempt
    attempt_call = mock_logger.log_event.call_args_list[0]
    assert attempt_call[0][0] == "sink_write_attempt"

    # Second call: write completion with metrics
    completion_call = mock_logger.log_event.call_args_list[1]
    assert completion_call[0][0] == "sink_write"
    assert "bytes" in completion_call[1]["metrics"]
    assert "files" in completion_call[1]["metrics"]
    assert completion_call[1]["metrics"]["files"] == 3


def test_on_error_skip_recovery(temp_output_dir, caplog):
    """Test error recovery with on_error='skip' - lines 119, 121."""
    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        bundle_name="test_bundle",
        on_error="skip",
        key_env="NONEXISTENT_KEY_VAR"  # Will fail to find key
    )

    # Mock plugin_logger
    mock_logger = MagicMock()
    sink.plugin_logger = mock_logger

    # Should not raise, just log warning
    sink.write({"results": []}, metadata={})

    # Check that error was logged
    assert any("Signed artifact sink failed" in record.message for record in caplog.records)

    # Check plugin logger error was called
    mock_logger.log_error.assert_called_once()


def test_aggregates_in_manifest(temp_output_dir, sample_results, monkeypatch):
    """Test aggregates included in manifest - line 151."""
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-secret-key")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        bundle_name="test_bundle",
        timestamped=False,
    )

    sink.write(sample_results, metadata={})

    # Read manifest
    manifest_path = temp_output_dir / "test_bundle" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    # Aggregates should be included
    assert "aggregates" in manifest
    assert manifest["aggregates"]["score_stats"]["criteria"]["accuracy"]["mean"] == 0.85


def test_cost_summary_in_manifest(temp_output_dir, sample_results, monkeypatch):
    """Test cost_summary included in manifest - line 153."""
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-secret-key")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        bundle_name="test_bundle",
        timestamped=False,
    )

    sink.write(sample_results, metadata={})

    # Read manifest
    manifest_path = temp_output_dir / "test_bundle" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    # Cost summary should be included
    assert "cost_summary" in manifest
    assert manifest["cost_summary"]["total_cost"] == 1.23


def test_key_resolution_from_legacy_env(temp_output_dir, monkeypatch, caplog):
    """Test key resolution from legacy DMP_SIGNING_KEY - line 166."""
    import logging
    # Set legacy env var
    monkeypatch.setenv("DMP_SIGNING_KEY", "legacy-key")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        key_env="ELSPETH_SIGNING_KEY",  # Preferred env not set
        timestamped=False,
        bundle_name="legacy_test",
    )

    results = {"results": [{"test": "data"}]}

    # Should use legacy key (with warning)
    with caplog.at_level(logging.WARNING):
        sink.write(results, metadata={})

    # Check that warning was logged
    assert any("Using legacy DMP_SIGNING_KEY" in record.message for record in caplog.records)


def test_key_resolution_from_cosign(temp_output_dir, monkeypatch):
    """Test key resolution from COSIGN_KEY fallback."""
    # Set COSIGN_KEY
    monkeypatch.setenv("COSIGN_KEY", "cosign-key-value")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        key_env="ELSPETH_SIGNING_KEY",  # Not set
    )

    results = {"results": [{"test": "data"}]}
    sink.write(results, metadata={})

    # Should succeed using COSIGN_KEY
    bundle_dir = temp_output_dir / list(temp_output_dir.iterdir())[0].name
    assert (bundle_dir / "signature.json").exists()


def test_key_resolution_no_key_raises(temp_output_dir):
    """Test that missing key raises ValueError."""
    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        key=None,
        key_env=None,
    )

    with pytest.raises(ValueError, match="Signing key not provided"):
        sink.write({"results": []}, metadata={})


def test_rsa_public_key_fingerprint(temp_output_dir, monkeypatch):
    """Test RSA public key fingerprint derivation - lines 71-86, 94."""
    # Mock RSA private key (simplified)
    private_key = "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----"
    public_key = "-----BEGIN PUBLIC KEY-----\ntest_pub\n-----END PUBLIC KEY-----"

    monkeypatch.setenv("ELSPETH_SIGNING_KEY", private_key)
    monkeypatch.setenv("RSA_PUBLIC_KEY", public_key)

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        algorithm="rsa-pss-sha256",
        public_key_env="RSA_PUBLIC_KEY",
        timestamped=False,
        bundle_name="rsa_test",
    )

    # Mock the signature generation and fingerprint
    with patch("elspeth.plugins.nodes.sinks.signed.generate_signature") as mock_sig, \
         patch("elspeth.plugins.nodes.sinks.signed.public_key_fingerprint") as mock_fp:
        mock_sig.return_value = "mock_signature"
        mock_fp.return_value = "sha256:abcd1234"

        results = {"results": [{"test": "data"}]}
        sink.write(results, metadata={})

        # Check that fingerprint was computed
        mock_fp.assert_called_once_with(public_key)

        # Read signature file
        sig_path = temp_output_dir / "rsa_test" / "signature.json"
        sig_data = json.loads(sig_path.read_text())

        # key_fingerprint should be in signature
        assert "key_fingerprint" in sig_data
        assert sig_data["key_fingerprint"] == "sha256:abcd1234"


def test_ecdsa_public_key_from_private_key_bytes(temp_output_dir):
    """Test ECDSA with public key derived from private bytes - lines 71-86."""
    # Simulate a scenario where public key is embedded in private key
    private_key_with_pub = b"-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----"

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        algorithm="ecdsa-p256-sha256",
        key=private_key_with_pub,
        timestamped=False,
        bundle_name="ecdsa_test",
    )

    with patch("elspeth.plugins.nodes.sinks.signed.generate_signature") as mock_sig, \
         patch("elspeth.plugins.nodes.sinks.signed.public_key_fingerprint") as mock_fp:
        mock_sig.return_value = "mock_signature"
        mock_fp.return_value = "sha256:ecdsa_fp"

        results = {"results": [{"test": "data"}]}
        sink.write(results, metadata={})

        # Fingerprint should be computed from embedded public key
        assert mock_fp.called


def test_public_key_fingerprint_exception_handled(temp_output_dir, monkeypatch):
    """Test that public key fingerprint exception is handled gracefully - line 86."""
    private_key = "test-key"

    monkeypatch.setenv("ELSPETH_SIGNING_KEY", private_key)

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        algorithm="rsa-pss-sha256",
        timestamped=False,
        bundle_name="exception_test",
    )

    with patch("elspeth.plugins.nodes.sinks.signed.generate_signature") as mock_sig, \
         patch("elspeth.plugins.nodes.sinks.signed.public_key_fingerprint") as mock_fp:
        mock_sig.return_value = "mock_signature"
        mock_fp.side_effect = Exception("Fingerprint error")

        results = {"results": [{"test": "data"}]}
        # Should not raise, fingerprint is optional
        sink.write(results, metadata={})

        # Read signature file
        sig_path = temp_output_dir / "exception_test" / "signature.json"
        sig_data = json.loads(sig_path.read_text())

        # key_fingerprint should not be in signature
        assert "key_fingerprint" not in sig_data


def test_hmac_no_fingerprint(temp_output_dir, monkeypatch):
    """Test that HMAC algorithms don't add fingerprint."""
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-secret")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        algorithm="hmac-sha256",
        timestamped=False,
        bundle_name="hmac_test",
    )

    results = {"results": [{"test": "data"}]}
    sink.write(results, metadata={})

    # Read signature file
    sig_path = temp_output_dir / "hmac_test" / "signature.json"
    sig_data = json.loads(sig_path.read_text())

    # HMAC should not have key_fingerprint
    assert "key_fingerprint" not in sig_data


def test_produces_consumes_finalize():
    """Test placeholder methods."""
    sink = SignedArtifactSink(base_path="/tmp/test")

    assert sink.produces() == []
    assert sink.consumes() == []
    assert sink.finalize({}) is None


def test_bundle_name_from_metadata(temp_output_dir, monkeypatch):
    """Test bundle name resolution from metadata."""
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-key")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        bundle_name=None,  # Will use metadata
        timestamped=False,
    )

    metadata = {"experiment": "my_experiment"}
    results = {"results": []}
    sink.write(results, metadata=metadata)

    # Bundle should be named after experiment
    assert (temp_output_dir / "my_experiment").exists()


def test_bundle_name_fallback(temp_output_dir, monkeypatch):
    """Test bundle name fallback to 'signed'."""
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-key")

    sink = SignedArtifactSink(
        base_path=str(temp_output_dir),
        bundle_name=None,
        timestamped=False,
    )

    results = {"results": []}
    sink.write(results, metadata={})

    # Bundle should fall back to "signed"
    assert (temp_output_dir / "signed").exists()
