import os

import pytest

from elspeth.core.base.protocols import LLMRequest
from elspeth.plugins.nodes.transforms.llm.middleware_azure import AzureEnvironmentMiddleware


def test_init_skip_without_env(monkeypatch):
    for k in ("AZUREML_RUN_ID", "AZUREML_ARM_SUBSCRIPTION"):
        monkeypatch.delenv(k, raising=False)
    mw = AzureEnvironmentMiddleware(enable_run_logging=True, on_error="skip")
    assert mw is not None


def test_init_abort_without_env_raises(monkeypatch):
    for k in ("AZUREML_RUN_ID", "AZUREML_ARM_SUBSCRIPTION"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        AzureEnvironmentMiddleware(enable_run_logging=True, on_error="abort")


def test_init_abort_with_env_detected_raises(monkeypatch):
    monkeypatch.setenv("AZUREML_RUN_ID", "run-1")
    with pytest.raises(RuntimeError):
        AzureEnvironmentMiddleware(enable_run_logging=True, on_error="abort")


def test_request_response_flow_sequence_and_metrics(monkeypatch):
    # Disable run logging to force fallback logging paths
    for k in ("AZUREML_RUN_ID", "AZUREML_ARM_SUBSCRIPTION"):
        monkeypatch.delenv(k, raising=False)
    mw = AzureEnvironmentMiddleware(enable_run_logging=False, on_error="skip", log_prompts=True, log_metrics=True)
    req = LLMRequest(system_prompt="sys", user_prompt="user", metadata={})
    req2 = mw.before_request(req)
    assert "azure_sequence" in req2.metadata
    seq = req2.metadata["azure_sequence"]
    resp = mw.after_response(req2, {"metrics": {"tokens": 5}, "error": None})
    assert resp["metrics"]["tokens"] == 5
    # Sequence is consistent
    assert req2.metadata["azure_sequence"] == seq


def test_retry_exhausted_fallback_logging(monkeypatch, caplog):
    caplog.set_level("INFO")
    for k in ("AZUREML_RUN_ID", "AZUREML_ARM_SUBSCRIPTION"):
        monkeypatch.delenv(k, raising=False)
    mw = AzureEnvironmentMiddleware(enable_run_logging=False, on_error="skip")
    req = LLMRequest(system_prompt="s", user_prompt="u", metadata={"azure_sequence": "az-1"})
    metadata = {"attempts": 3, "max_attempts": 3, "history": [{"err": "x"}], "error": "boom", "error_type": "RuntimeError"}
    mw.on_retry_exhausted(req, metadata, RuntimeError("boom"))
    # Fallback logs to logger at INFO level by default
    assert any("llm_retry_exhausted" in rec.message for rec in caplog.records)
