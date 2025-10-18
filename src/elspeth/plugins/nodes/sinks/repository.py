"""Result sinks that push artifacts to source control hosting services."""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 15


def _default_context(metadata: Mapping[str, Any], timestamp: datetime) -> dict[str, Any]:
    context = {k: v for k, v in metadata.items() if isinstance(k, str)}
    context.setdefault("timestamp", timestamp.strftime("%Y%m%dT%H%M%SZ"))
    context.setdefault("date", timestamp.strftime("%Y-%m-%d"))
    context.setdefault("time", timestamp.strftime("%H%M%S"))
    context.setdefault("experiment", metadata.get("experiment") or metadata.get("name") or "experiment")
    return context


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


@dataclass
class PreparedFile:
    path: str
    content: bytes
    content_type: str = "application/json"


@dataclass
class _RepoSinkBase(ResultSink):
    path_template: str = "experiments/{experiment}/{timestamp}"
    commit_message_template: str = "Add experiment results for {experiment}"
    include_manifest: bool = True
    dry_run: bool = True
    session: requests.Session | None = None
    # Network behavior
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT
    _last_payloads: list[dict[str, Any]] = field(default_factory=list, init=False)
    on_error: str = "abort"

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
            # Mount retry adapter to improve resilience on transient failures
            try:  # pragma: no cover - adapter import/availability varies by env
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry

                retry = Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET", "PUT", "POST"],
                )
                adapter = HTTPAdapter(max_retries=retry)
                self.session.mount("https://", adapter)
                self.session.mount("http://", adapter)
            except Exception:
                # Non-fatal if retry adapter isn't available
                pass
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        if self.dry_run:
            logger.warning(
                "Repository sink running in dry-run mode; no remote writes will occur. "
                "Enable --live-outputs via CLI or set dry_run=False in configuration for actual pushes."
            )

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        context = _default_context(metadata, timestamp)
        try:
            prefix = self._resolve_prefix(context)
            files = self._prepare_files(results, metadata, prefix, timestamp)
            commit_message = self.commit_message_template.format(**context)
            payload: dict[str, Any] = {
                "context": context,
                "commit_message": commit_message,
                "files": [
                    {
                        "path": file.path,
                        "size": len(file.content),
                        "content_type": file.content_type,
                    }
                    for file in files
                ],
            }
            plugin_logger = getattr(self, "plugin_logger", None)
            if plugin_logger:
                plugin_logger.log_event(
                    "sink_write_attempt",
                    message=f"Repo write attempt: {prefix}",
                    metrics={"files": len(files)},
                    metadata={"repo_path": prefix, "commit_message": commit_message},
                )
            if self.dry_run:
                payload["dry_run"] = True
                self._last_payloads.append(payload)
                if plugin_logger:
                    plugin_logger.log_event(
                        "sink_write",
                        message=f"Repo dry-run payload prepared: {prefix}",
                        metrics={"files": len(files)},
                        metadata={"repo_path": prefix},
                    )
                return
            self._upload(files, commit_message, metadata, context, timestamp)
            if plugin_logger:
                plugin_logger.log_event(
                    "sink_write",
                    message=f"Repo write completed: {prefix}",
                    metrics={"files": len(files)},
                    metadata={"repo_path": prefix},
                )
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Repository sink failed; skipping upload: %s", exc)
                plugin_logger = getattr(self, "plugin_logger", None)
                if plugin_logger:
                    plugin_logger.log_error(exc, context="repo sink write", recoverable=True)
                return
            raise

    # ------------------------------------------------------------------ internals
    def _resolve_prefix(self, context: Mapping[str, Any]) -> str:
        try:
            return self.path_template.format(**context)
        except KeyError as exc:  # pragma: no cover - configuration error
            missing = exc.args[0]
            raise ValueError(f"Missing placeholder '{missing}' in path template") from exc

    def _prepare_files(
        self,
        results: dict[str, Any],
        metadata: Mapping[str, Any],
        prefix: str,
        timestamp: datetime,
    ) -> list[PreparedFile]:
        files: list[PreparedFile] = []
        results_path = f"{prefix}/results.json"
        manifest_path = f"{prefix}/manifest.json"
        files.append(PreparedFile(path=results_path, content=_json_bytes(results)))
        if self.include_manifest:
            manifest = {
                "generated_at": timestamp.isoformat(),
                "rows": len(results.get("results", [])),
                "metadata": dict(metadata),
            }
            if "aggregates" in results:
                manifest["aggregates"] = results["aggregates"]
            if "cost_summary" in results:
                manifest["cost_summary"] = results["cost_summary"]
            files.append(PreparedFile(path=manifest_path, content=_json_bytes(manifest)))
        return files

    # To be implemented by subclasses
    def _upload(
        self,
        files: list[PreparedFile],
        commit_message: str,
        metadata: Mapping[str, Any],
        context: Mapping[str, Any],
        timestamp: datetime,
    ) -> None:
        raise NotImplementedError

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - placeholder for artifact chaining
        return []

    def consumes(self) -> list[str]:  # pragma: no cover - placeholder for artifact chaining
        return []

    def finalize(self, artifacts: Mapping[str, Artifact], *, metadata: dict[str, Any] | None = None) -> None:  # pragma: no cover - optional cleanup
        return None

    @staticmethod
    def _read_token(env_var: str) -> str | None:
        """Read and strip token from environment variable.

        Args:
            env_var: Environment variable name

        Returns:
            Stripped token string or None if not set
        """

        token = os.getenv(env_var)
        return token.strip() if token else None


class GitHubRepoSink(_RepoSinkBase):
    """Push experiment artifacts to a GitHub repository via the REST API."""

    def __init__(
        self,
        *,
        owner: str,
        repo: str,
        branch: str = "main",
        token_env: str = "GITHUB_TOKEN",
        base_url: str = "https://api.github.com",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.token_env = token_env
        self.base_url = base_url.rstrip("/")
        self._headers_cache: dict[str, str] | None = None

    # Upload implementation -------------------------------------------------
    def _upload(
        self,
        files: list[PreparedFile],
        commit_message: str,
        metadata: Mapping[str, Any],
        context: Mapping[str, Any],
        timestamp: datetime,
    ) -> None:
        for prepared in files:
            sha = self._get_existing_sha(prepared.path)
            payload = {
                "message": commit_message,
                "branch": self.branch,
                "content": base64.b64encode(prepared.content).decode("ascii"),
            }
            if sha:
                payload["sha"] = sha
            self._request(
                "PUT",
                f"{self.base_url}/repos/{self.owner}/{self.repo}/contents/{prepared.path}",
                json=payload,
            )

    # Helpers ----------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        if self._headers_cache is not None:
            return self._headers_cache
        headers = {"Accept": "application/vnd.github+json"}
        token = self._read_token(self.token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif not self.dry_run and isinstance(self.session, requests.Session):
            # Fail fast in typical execution when using a real requests.Session.
            # Custom sessions (e.g., tests) proceed to allow simulated failures (timeouts, etc.).
            raise RuntimeError(f"GitHub token missing; set '{self.token_env}' or enable dry-run")
        self._headers_cache = headers
        return headers

    def _get_existing_sha(self, path: str) -> str | None:
        response = self._request(
            "GET",
            f"{self.base_url}/repos/{self.owner}/{self.repo}/contents/{path}",
            expected_status={200, 404},
        )
        if response.status_code == 404:
            return None
        data = response.json()
        # response.json() returns Any, so dict access returns Any despite runtime str value
        return data.get("sha")  # type: ignore[no-any-return]

    def _request(self, method: str, url: str, expected_status: set[int] | None = None, **kwargs: Any) -> Any:
        expected_status = expected_status or {200, 201}
        if self.session is None:  # pragma: no cover - defensive
            raise RuntimeError("session must be initialized")
        timeout = kwargs.pop("timeout", self.request_timeout)
        response = self.session.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
        if response.status_code not in expected_status:
            raise RuntimeError(f"GitHub API call failed ({response.status_code}): {response.text}")
        return response


class AzureDevOpsRepoSink(_RepoSinkBase):
    """Push experiment artifacts to an Azure DevOps Git repository."""

    def __init__(
        self,
        *,
        organization: str,
        project: str,
        repository: str,
        branch: str = "main",
        token_env: str = "AZURE_DEVOPS_PAT",
        api_version: str = "7.1-preview",
        base_url: str = "https://dev.azure.com",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.organization = organization
        self.project = project
        self.repository = repository
        self.branch = branch
        self.token_env = token_env
        self.api_version = api_version
        self.base_url = base_url.rstrip("/")
        self._headers_cache: dict[str, str] | None = None

    # Upload implementation -------------------------------------------------
    def _upload(
        self,
        files: list[PreparedFile],
        commit_message: str,
        metadata: Mapping[str, Any],
        context: Mapping[str, Any],
        timestamp: datetime,
    ) -> None:
        branch_ref = self._get_branch_ref()
        changes = []
        for prepared in files:
            existing = self._item_exists(prepared.path)
            change_type = "edit" if existing else "add"
            changes.append(
                {
                    "changeType": change_type,
                    "item": {"path": self._ensure_path(prepared.path)},
                    "newContent": {
                        "content": prepared.content.decode("utf-8"),
                        "contentType": "rawtext",
                    },
                }
            )
        payload = {
            "refUpdates": [
                {
                    "name": f"refs/heads/{self.branch}",
                    "oldObjectId": branch_ref,
                }
            ],
            "commits": [
                {
                    "comment": commit_message,
                    "changes": changes,
                }
            ],
        }
        url = (
            f"{self.base_url}/{self.organization}/{self.project}/_apis/git"
            f"/repositories/{self.repository}/pushes?api-version={self.api_version}"
        )
        self._request("POST", url, json=payload, expected_status={200, 201})

    # Helpers ----------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        if self._headers_cache is not None:
            return self._headers_cache
        headers = {"Content-Type": "application/json"}
        token = self._read_token(self.token_env)
        if token:
            auth = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {auth}"
        elif not self.dry_run and isinstance(self.session, requests.Session):
            raise RuntimeError(f"Azure DevOps PAT missing; set '{self.token_env}' or enable dry-run")
        self._headers_cache = headers
        return headers

    def _get_branch_ref(self) -> str:
        url = (
            f"{self.base_url}/{self.organization}/{self.project}/_apis/git"
            f"/repositories/{self.repository}/refs?filter=heads/{self.branch}"
            f"&api-version={self.api_version}"
        )
        response = self._request("GET", url, expected_status={200})
        data = response.json()
        if not data.get("value"):
            raise RuntimeError(f"Branch '{self.branch}' not found")
        # response.json() returns Any, so nested dict/list access returns Any despite runtime str value
        return data["value"][0]["objectId"]  # type: ignore[no-any-return]

    def _item_exists(self, path: str) -> bool:
        url = (
            f"{self.base_url}/{self.organization}/{self.project}/_apis/git"
            f"/repositories/{self.repository}/items?path={self._ensure_path(path)}"
            f"&includeContentMetadata=true&api-version={self.api_version}"
        )
        response = self._request("GET", url, expected_status={200, 404})
        # Comparison expression inferred as Any due to response type annotation gaps
        return response.status_code == 200  # type: ignore[no-any-return]

    def _request(self, method: str, url: str, expected_status: set[int] | None = None, **kwargs: Any) -> Any:
        expected_status = expected_status or {200, 201}
        if self.session is None:  # pragma: no cover - defensive
            raise RuntimeError("session must be initialized")
        timeout = kwargs.pop("timeout", self.request_timeout)
        response = self.session.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
        if response.status_code not in expected_status:
            raise RuntimeError(f"Azure DevOps API call failed ({response.status_code}): {response.text}")
        return response

    def _ensure_path(self, path: str) -> str:
        if not path.startswith("/"):
            return f"/{path}"
        return path


class AzureDevOpsArtifactsRepoSink(AzureDevOpsRepoSink):
    """Publish local folders or archives to an Azure DevOps Git repository.

    This sink uploads all files under a local `folder_path` into the target
    repository under `dest_prefix_template` (defaults to artifacts/{timestamp}).
    Files are committed in a single push. Binary files are uploaded using
    base64-encoded content.
    """

    def __init__(
        self,
        *,
        folder_path: str,
        dest_prefix_template: str = "artifacts/{timestamp}",
        commit_message_template: str = "Publish artifacts for {experiment}",
        **kwargs: Any,
    ) -> None:
        super().__init__(commit_message_template=commit_message_template, **kwargs)
        self.folder_path = folder_path
        self.dest_prefix_template = dest_prefix_template

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        context = _default_context(metadata, timestamp)
        prefix = self._resolve_prefix(context)
        commit_message = self.commit_message_template.format(**context)
        try:
            changes = self._collect_changes(prefix)
            if not changes:
                logger.info("No files found to publish from %s", self.folder_path)
                return
            payload = {
                "refUpdates": [
                    {
                        "name": f"refs/heads/{self.branch}",
                        "oldObjectId": self._get_branch_ref(),
                    }
                ],
                "commits": [
                    {
                        "comment": commit_message,
                        "changes": changes,
                    }
                ],
            }
            url = (
                f"{self.base_url}/{self.organization}/{self.project}/_apis/git"
                f"/repositories/{self.repository}/pushes?api-version={self.api_version}"
            )
            if not self.dry_run:
                self._request("POST", url, json=payload, expected_status={200, 201})
            else:
                logger.warning("AzureDevOpsArtifactsRepoSink in dry-run mode; not pushing changes.")
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Artifacts repo sink failed; skipping upload: %s", exc)
                return
            raise

    def _resolve_prefix(self, context: Mapping[str, Any]) -> str:
        template = self.dest_prefix_template or "artifacts/{timestamp}"
        try:
            return template.format(**context)
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(f"Missing placeholder '{missing}' in dest prefix template") from exc

    def _collect_changes(self, prefix: str) -> list[dict[str, Any]]:
        root = Path(self.folder_path)
        if not root.exists() or not root.is_dir():
            return []
        changes: list[dict[str, Any]] = []
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(root).as_posix()
            dest = f"/{prefix}/{rel}"
            b = path.read_bytes()
            # Use base64encoded to handle binaries safely
            encoded = base64.b64encode(b).decode("ascii")
            change_type = "edit" if self._item_exists(dest) else "add"
            changes.append(
                {
                    "changeType": change_type,
                    "item": {"path": dest},
                    "newContent": {
                        "content": encoded,
                        "contentType": "base64encoded",
                    },
                }
            )
        return changes
