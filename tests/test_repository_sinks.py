"""Tests for repository sinks (GitHub/Azure DevOps) network behavior.

Focus areas:
- Default HTTP timeout is applied to outgoing requests
- Error handling when requests time out: skip vs abort
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from elspeth.plugins.nodes.sinks.repository import (
    AzureDevOpsRepoSink,
    GitHubRepoSink,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data: dict[str, Any] | None = None, text: str = "OK") -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self) -> dict[str, Any]:  # pragma: no cover - thin helper
        return dict(self._json_data)


class _CaptureSession:
    """Capture outgoing request kwargs for assertion."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        """Record the request and return a default OK response."""
        self.calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse(200, json_data={})


class _TimeoutSession:
    """Simulate a session that always times out."""

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        """Raise a requests.Timeout to simulate network stall."""
        raise requests.Timeout(f"Simulated timeout calling {method} {url}")


def test_github_repo_sink_default_timeout_applied() -> None:
    session = _CaptureSession()
    sink = GitHubRepoSink(owner="o", repo="r", session=session, dry_run=True)

    # Call the internal request helper directly to avoid hitting the full upload path
    resp = sink._request("GET", "https://api.github.com/_probe", expected_status={200})  # type: ignore[attr-defined]
    assert isinstance(resp, _FakeResponse)
    assert session.calls, "Expected at least one captured request"
    assert session.calls[-1]["timeout"] == 15, "Default timeout should be 15s for GitHub sink"


def test_azure_devops_repo_sink_default_timeout_applied() -> None:
    session = _CaptureSession()
    sink = AzureDevOpsRepoSink(
        organization="org",
        project="proj",
        repository="repo",
        session=session,
        dry_run=True,
    )

    # Call the internal request helper directly to avoid hitting the full upload path
    resp = sink._request("GET", "https://dev.azure.com/_probe", expected_status={200})  # type: ignore[attr-defined]
    assert isinstance(resp, _FakeResponse)
    assert session.calls, "Expected at least one captured request"
    assert session.calls[-1]["timeout"] == 15, "Default timeout should be 15s for Azure DevOps sink"


def test_repo_sinks_respect_custom_request_timeout() -> None:
    session = _CaptureSession()
    gh = GitHubRepoSink(owner="o", repo="r", session=session, dry_run=True, request_timeout=5)
    resp = gh._request("GET", "https://api.github.com/_probe", expected_status={200})  # type: ignore[attr-defined]
    assert isinstance(resp, _FakeResponse)
    assert session.calls[-1]["timeout"] == 5

    session2 = _CaptureSession()
    az = AzureDevOpsRepoSink(
        organization="org",
        project="proj",
        repository="repo",
        session=session2,
        dry_run=True,
        request_timeout=7,
    )
    resp2 = az._request("GET", "https://dev.azure.com/_probe", expected_status={200})  # type: ignore[attr-defined]
    assert isinstance(resp2, _FakeResponse)
    assert session2.calls[-1]["timeout"] == 7


@pytest.mark.parametrize(
    "sink_factory",
    [
        pytest.param(lambda s: GitHubRepoSink(owner="o", repo="r", session=s, dry_run=False), id="github"),
        pytest.param(
            lambda s: AzureDevOpsRepoSink(organization="org", project="proj", repository="repo", session=s, dry_run=False),
            id="azure-devops",
        ),
    ],
)
def test_repo_sink_timeout_skip_vs_abort(sink_factory) -> None:
    # on_error=skip: should not raise
    sink_skip = sink_factory(_TimeoutSession())
    sink_skip.allow_missing_token()  # Required for dry_run=False without token
    sink_skip.on_error = "skip"
    sink_skip.write({"results": []}, metadata={"experiment": "e"})

    # on_error=abort: should raise original timeout
    sink_abort = sink_factory(_TimeoutSession())
    sink_abort.allow_missing_token()  # Required for dry_run=False without token
    sink_abort.on_error = "abort"
    with pytest.raises(requests.Timeout):
        sink_abort.write({"results": []}, metadata={"experiment": "e"})
