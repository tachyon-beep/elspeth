from __future__ import annotations

import pytest

from elspeth.plugins.nodes.transforms.llm.middleware_azure import AzureEnvironmentMiddleware


def test_azure_env_unknown_severity_threshold_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        mw = AzureEnvironmentMiddleware(enable_run_logging=False, severity_threshold="weird", on_error="skip")
    assert mw is not None
    assert any("Unknown severity_threshold" in rec.message for rec in caplog.records)


def test_azure_env_logs_table_fallback_without_run(caplog: pytest.LogCaptureFixture) -> None:
    mw = AzureEnvironmentMiddleware(enable_run_logging=False, on_error="skip")
    with caplog.at_level("INFO"):
        mw.on_experiment_complete(
            "exp",
            {"aggregates": {"score": {"mean": 0.5}}, "results": [{}]},
            metadata={"label": "demo"},
        )
    # Fallback logging path should include the table tag
    assert any("azure_env-table" in rec.message for rec in caplog.records)
