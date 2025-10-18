import json

import pytest

from elspeth.plugins.nodes.transforms.llm.middleware.azure_content_safety import AzureContentSafetyMiddleware
from elspeth.core.base.protocols import LLMRequest


def _mock_post(flagged: bool, severity: int):
    class Resp:
        def __init__(self):
            self._payload = {"results": [{"severity": severity}]}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _post(url, headers, json=None, timeout=10):  # noqa: ARG002
        return Resp()

    return _post


def test_content_safety_abort_on_violation(monkeypatch):
    monkeypatch.setattr(
        "elspeth.plugins.nodes.transforms.llm.middleware.azure_content_safety.requests.post",
        _mock_post(flagged=True, severity=6),
    )
    mw = AzureContentSafetyMiddleware(endpoint="https://safety", key="k", severity_threshold=4, on_violation="abort")
    with pytest.raises(ValueError):
        mw.before_request(LLMRequest(system_prompt="s", user_prompt="bad", metadata={}))


def test_content_safety_mask_on_violation(monkeypatch):
    monkeypatch.setattr(
        "elspeth.plugins.nodes.transforms.llm.middleware.azure_content_safety.requests.post",
        _mock_post(flagged=True, severity=5),
    )
    mw = AzureContentSafetyMiddleware(endpoint="https://safety", key="k", severity_threshold=4, on_violation="mask", mask="[MASK]")
    req = LLMRequest(system_prompt="s", user_prompt="bad", metadata={})
    out = mw.before_request(req)
    assert out.user_prompt == "[MASK]"


def test_content_safety_skip_on_error(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("network")

    monkeypatch.setattr(
        "elspeth.plugins.nodes.transforms.llm.middleware.azure_content_safety.requests.post",
        boom,
    )
    mw = AzureContentSafetyMiddleware(endpoint="https://safety", key="k", on_error="skip")
    req = LLMRequest(system_prompt="s", user_prompt="ok", metadata={})
    out = mw.before_request(req)
    assert out.user_prompt == "ok"
    assert any("Content Safety call failed; skipping" in rec.message for rec in caplog.records)

