"""Result sinks that push artifacts to source control hosting services."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import logging

import requests

from dmp.core.interfaces import ResultSink


logger = logging.getLogger(__name__)

def _default_context(metadata: Mapping[str, Any], timestamp: datetime) -> Dict[str, Any]:
    context = {k: v for k, v in metadata.items() if isinstance(k, str)}
    context.setdefault("timestamp", timestamp.strftime("%Y%m%dT%H%M%SZ"))
    context.setdefault("date", timestamp.strftime("%Y-%m-%d"))
    context.setdefault("time", timestamp.strftime("%H%M%S"))
    context.setdefault("experiment", metadata.get("experiment") or metadata.get("name") or "experiment")
    return context


def _json_bytes(payload: Dict[str, Any]) -> bytes:
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
    _last_payloads: List[Dict[str, Any]] = field(default_factory=list, init=False)
    on_error: str = "abort"

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")

    def write(self, results: Dict[str, Any], *, metadata: Dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        context = _default_context(metadata, timestamp)
        try:
            prefix = self._resolve_prefix(context)
            files = self._prepare_files(results, metadata, prefix, timestamp)
            commit_message = self.commit_message_template.format(**context)
            payload = {
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
            if self.dry_run:
                payload["dry_run"] = True
                self._last_payloads.append(payload)
                return
            self._upload(files, commit_message, metadata, context, timestamp)
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Repository sink failed; skipping upload: %s", exc)
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
        results: Dict[str, Any],
        metadata: Mapping[str, Any],
        prefix: str,
        timestamp: datetime,
    ) -> List[PreparedFile]:
        files: List[PreparedFile] = []
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
        files: List[PreparedFile],
        commit_message: str,
        metadata: Mapping[str, Any],
        context: Mapping[str, Any],
        timestamp: datetime,
    ) -> None:
        raise NotImplementedError

    def produces(self):  # pragma: no cover - placeholder for artifact chaining
        return []

    def consumes(self):  # pragma: no cover - placeholder for artifact chaining
        return []

    def finalize(self, artifacts, *, metadata=None):  # pragma: no cover - optional cleanup
        return None


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
        self._headers_cache: Dict[str, str] | None = None

    # Upload implementation -------------------------------------------------
    def _upload(
        self,
        files: List[PreparedFile],
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
    def _headers(self) -> Dict[str, str]:
        if self._headers_cache is not None:
            return self._headers_cache
        headers = {"Accept": "application/vnd.github+json"}
        token = self._read_token(self.token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._headers_cache = headers
        return headers

    def _get_existing_sha(self, path: str) -> Optional[str]:
        response = self._request(
            "GET",
            f"{self.base_url}/repos/{self.owner}/{self.repo}/contents/{path}",
            expected_status={200, 404},
        )
        if response.status_code == 404:
            return None
        data = response.json()
        return data.get("sha")

    def _request(self, method: str, url: str, expected_status: set[int] | None = None, **kwargs: Any):  # type: ignore[return-any]
        expected_status = expected_status or {200, 201}
        response = self.session.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code not in expected_status:
            raise RuntimeError(f"GitHub API call failed ({response.status_code}): {response.text}")
        return response

    @staticmethod
    def _read_token(env_var: str) -> Optional[str]:
        token = os.getenv(env_var)
        return token.strip() if token else None


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
        self._headers_cache: Dict[str, str] | None = None

    # Upload implementation -------------------------------------------------
    def _upload(
        self,
        files: List[PreparedFile],
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
    def _headers(self) -> Dict[str, str]:
        if self._headers_cache is not None:
            return self._headers_cache
        headers = {"Content-Type": "application/json"}
        token = self._read_token(self.token_env)
        if token:
            auth = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {auth}"
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
        return data["value"][0]["objectId"]

    def _item_exists(self, path: str) -> bool:
        url = (
            f"{self.base_url}/{self.organization}/{self.project}/_apis/git"
            f"/repositories/{self.repository}/items?path={self._ensure_path(path)}"
            f"&includeContentMetadata=true&api-version={self.api_version}"
        )
        response = self._request("GET", url, expected_status={200, 404})
        return response.status_code == 200

    def _request(self, method: str, url: str, expected_status: set[int] | None = None, **kwargs: Any):  # type: ignore[return-any]
        expected_status = expected_status or {200, 201}
        response = self.session.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code not in expected_status:
            raise RuntimeError(
                f"Azure DevOps API call failed ({response.status_code}): {response.text}"
            )
        return response

    def _ensure_path(self, path: str) -> str:
        if not path.startswith("/"):
            return f"/{path}"
        return path

    @staticmethod
    def _read_token(env_var: str) -> Optional[str]:
        token = os.getenv(env_var)
        return token.strip() if token else None


import os  # noqa: E402  (keep at end to avoid circular import during module import)
