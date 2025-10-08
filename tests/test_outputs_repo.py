import base64
import json

import pytest

from dmp.plugins.outputs.repository import GitHubRepoSink, AzureDevOpsRepoSink


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def sample_results():
    return {
        "results": [
            {
                "row": {"APPID": "1"},
                "response": {"content": "ok"},
            }
        ],
        "aggregates": {"score": {"mean": 0.7}},
    }


def test_github_repo_sink_dry_run():
    sink = GitHubRepoSink(owner="org", repo="repo", dry_run=True)
    sink.write(sample_results(), metadata={"experiment": "exp1"})

    assert len(sink._last_payloads) == 1
    payload = sink._last_payloads[0]
    assert payload["dry_run"] is True
    paths = [entry["path"] for entry in payload["files"]]
    assert any(path.endswith("results.json") for path in paths)
    assert any(path.endswith("manifest.json") for path in paths)


def test_github_repo_sink_upload(monkeypatch):
    calls = []

    def fake_request(self, method, url, expected_status=None, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return DummyResponse(status_code=404)
        if method == "PUT":
            data = kwargs.get("json", {})
            content = base64.b64decode(data["content"]).decode("utf-8")
            loaded = json.loads(content)
            if "results" in loaded:
                assert loaded["results"][0]["row"]["APPID"] == "1"
            return DummyResponse(status_code=201)
        raise AssertionError(f"Unexpected method {method}")

    sink = GitHubRepoSink(owner="org", repo="repo", dry_run=False)
    monkeypatch.setattr(GitHubRepoSink, "_request", fake_request)

    sink.write(sample_results(), metadata={"experiment": "exp1"})

    assert any(call[0] == "PUT" for call in calls)


def test_azure_devops_repo_sink_upload(monkeypatch):
    calls = []

    def fake_request(self, method, url, expected_status=None, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET" and "/refs" in url:
            return DummyResponse(payload={"value": [{"objectId": "abc123"}]})
        if method == "GET" and "/items" in url:
            return DummyResponse(status_code=404)
        if method == "POST":
            payload = kwargs.get("json", {})
            assert payload["refUpdates"][0]["oldObjectId"] == "abc123"
            change = payload["commits"][0]["changes"][0]
            assert change["changeType"] == "add"
            assert json.loads(change["newContent"]["content"])["results"][0]["row"]["APPID"] == "1"
            assert change["item"]["path"].startswith("/runs/exp1/")
            return DummyResponse(status_code=201)
        raise AssertionError(f"Unexpected call {method} {url}")

    sink = AzureDevOpsRepoSink(
        organization="org",
        project="proj",
        repository="repo",
        dry_run=False,
        path_template="runs/{experiment}/{timestamp}",
        commit_message_template="Results for {experiment}",
    )
    monkeypatch.setattr(AzureDevOpsRepoSink, "_request", fake_request)

    sink.write(sample_results(), metadata={"experiment": "exp1"})

    assert any(call[0] == "POST" for call in calls)
    post_payload = next(kwargs for method, _, kwargs in calls if method == "POST")["json"]
    assert post_payload["commits"][0]["comment"] == "Results for exp1"


def test_azure_devops_repo_sink_skip_on_error(monkeypatch, caplog):
    def fake_request(self, method, url, expected_status=None, **kwargs):
        raise RuntimeError("boom")

    sink = AzureDevOpsRepoSink(
        organization="org",
        project="proj",
        repository="repo",
        dry_run=False,
        on_error="skip",
    )
    monkeypatch.setattr(AzureDevOpsRepoSink, "_request", fake_request)

    with caplog.at_level("WARNING"):
        sink.write(sample_results(), metadata={"experiment": "exp1"})

    assert "skipping upload" in "".join(caplog.messages)
