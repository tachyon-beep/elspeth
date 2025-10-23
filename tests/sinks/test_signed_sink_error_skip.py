from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink


def test_signed_sink_on_error_skip_swallows_exceptions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sink = SignedArtifactSink(
        base_path=tmp_path / "signed",
        bundle_name="x",
        timestamped=False,
        on_error="skip",
        key="secret",
    )

    # Force failure after results are written by making manifest hashing blow up
    def _raise_runtimeerror(*_args, **_kwargs):  # noqa: D401
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "elspeth.plugins.nodes.sinks.signed.SignedArtifactSink._hash_results",
        _raise_runtimeerror,
    )

    # Should not raise
    sink.write({"results": []}, metadata={})

    # File write may have started; at least ensure it did not crash
    assert (tmp_path / "signed" / "x").exists()
