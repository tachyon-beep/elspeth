from __future__ import annotations

import os
from pathlib import Path

from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink


def test_signed_sink_uses_cosign_key_fallback(tmp_path: Path, monkeypatch) -> None:
    # Ensure the primary env is unset and COSIGN_KEY is available
    monkeypatch.delenv("UNSET_ENV", raising=False)
    monkeypatch.setenv("COSIGN_KEY", "alt-secret-key")

    sink = SignedArtifactSink(
        base_path=tmp_path / "signed",
        bundle_name="exp",
        timestamped=False,
        key=None,
        key_env="UNSET_ENV",
    )

    # Should successfully write results and signature using the alt env key
    sink.write({"results": []}, metadata={})

    bundle_dir = tmp_path / "signed" / "exp"
    assert (bundle_dir / "results.json").exists()
    assert (bundle_dir / "signature.json").exists()


def test_signed_sink_uses_legacy_dmp_env(tmp_path: Path, monkeypatch) -> None:
    # Simulate legacy env variable present, primary unset
    monkeypatch.delenv("ELSPETH_SIGNING_KEY", raising=False)
    monkeypatch.setenv("DMP_SIGNING_KEY", "legacy-secret")

    sink = SignedArtifactSink(
        base_path=tmp_path / "signed",
        bundle_name="legacy",
        timestamped=False,
    )

    sink.write({"results": []}, metadata={})
    assert (tmp_path / "signed" / "legacy" / "signature.json").exists()
