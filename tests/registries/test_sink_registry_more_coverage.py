from __future__ import annotations

from types import SimpleNamespace

import pytest

import elspeth.core.registries.sink as sink_mod
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.sink import sink_registry


class _Dummy:
    def __init__(self, **_opts):  # noqa: D401
        return None


@pytest.mark.parametrize(
    "name, options",
    [
        ("analytics_report", {"base_path": "."}),
        ("analytics_visual", {"base_path": "."}),
        ("enhanced_visual", {"base_path": "."}),
        ("signed_artifact", {"base_path": "."}),
        ("reproducibility_bundle", {"base_path": "."}),
        ("embeddings_store", {"provider": "pgvector"}),
        ("github_repo", {"owner": "o", "repo": "r"}),
        (
            "azure_devops_repo",
            {"organization": "org", "project": "proj", "repository": "repo"},
        ),
        (
            "azure_devops_artifact_repo",
            {"folder_path": ".", "organization": "org", "project": "proj", "repository": "repo"},
        ),
    ],
)
def test_sink_registry_factory_branches(monkeypatch, name, options):
    # Patch actual classes to lightweight dummies to avoid heavy dependencies
    monkeypatch.setattr(sink_mod, "AnalyticsReportSink", _Dummy)
    monkeypatch.setattr(sink_mod, "VisualAnalyticsSink", _Dummy)
    monkeypatch.setattr(sink_mod, "EnhancedVisualAnalyticsSink", _Dummy)
    monkeypatch.setattr(sink_mod, "SignedArtifactSink", _Dummy)
    monkeypatch.setattr(sink_mod, "ReproducibilityBundleSink", _Dummy)
    monkeypatch.setattr(sink_mod, "EmbeddingsStoreSink", _Dummy)
    monkeypatch.setattr(sink_mod, "GitHubRepoSink", _Dummy)
    monkeypatch.setattr(sink_mod, "AzureDevOpsRepoSink", _Dummy)
    monkeypatch.setattr(sink_mod, "AzureDevOpsArtifactsRepoSink", _Dummy)

    # ADR-002-B: Provide parent context so plugins can derive security_level
    parent_context = PluginContext(
        plugin_name="test_suite",
        plugin_kind="suite",
        security_level="OFFICIAL",
        determinism_level="guaranteed",
        provenance=("test",),
    )

    plugin = sink_registry.create(
        name=name,
        options={
            **options,
            "determinism_level": "guaranteed",
        },
        parent_context=parent_context,
        require_determinism=True,
    )
    assert isinstance(plugin, _Dummy)


def test_sink_registry_azure_blob_minimal(monkeypatch, tmp_path):
    # Patch class and validation to avoid external calls
    monkeypatch.setattr(sink_mod, "BlobResultSink", _Dummy)
    monkeypatch.setattr(sink_mod, "load_blob_config", lambda *a, **k: SimpleNamespace(account_url="https://acct.blob.core.windows.net"))
    monkeypatch.setattr(sink_mod, "validate_azure_blob_endpoint", lambda **_k: None)

    # ADR-002-B: Provide parent context so plugins can derive security_level
    parent_context = PluginContext(
        plugin_name="test_suite",
        plugin_kind="suite",
        security_level="OFFICIAL",
        determinism_level="guaranteed",
        provenance=("test",),
    )

    plugin = sink_registry.create(
        name="azure_blob",
        options={
            "config_path": str(tmp_path / "blob.yaml"),
            "profile": "default",
            "determinism_level": "guaranteed",
        },
        parent_context=parent_context,
        require_determinism=True,
    )
    assert isinstance(plugin, _Dummy)
