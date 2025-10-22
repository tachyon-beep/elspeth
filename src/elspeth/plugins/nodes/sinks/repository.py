"""Result sinks that push artifacts to source control hosting services."""

from __future__ import annotations

import base64
import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.security.secure_mode import SecureMode, get_secure_mode

try:
    HTTP_ADAPTER_CLS = getattr(importlib.import_module("requests.adapters"), "HTTPAdapter")
except (ImportError, AttributeError):  # pragma: no cover - optional dependency
    HTTP_ADAPTER_CLS = None

try:
    RETRY_CLS = getattr(importlib.import_module("urllib3.util.retry"), "Retry")
except (ImportError, AttributeError):  # pragma: no cover - optional dependency
    RETRY_CLS = None

logger = logging.getLogger(__name__)
DEFAULT_REQUEST_TIMEOUT = 15
DRY_RUN_WARNING_MESSAGE = (
    "Repository sink running in dry-run mode; no remote writes will occur. "
    "Set dry_run=False in configuration to enable remote publishing. "
    "When invoking the CLI, include --live-outputs to opt into live sink writes."
)

# Note: warning throttle flags are stored on the base class to avoid globals


class _RepoRequestError(RuntimeError):
    """Error raised when a repository API request fails."""

    def __init__(self, message: str, *, status: int | None = None, transient: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.transient = transient


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
    """Simple container for a prepared file upload payload."""
    path: str
    content: bytes
    content_type: str = "application/json"


@dataclass
class _RepoSinkBase(ResultSink):
    """Common repository sink behavior (auth, retries, dry-run, error handling)."""

    path_template: str = "experiments/{experiment}/{timestamp}"
    commit_message_template: str = "Add experiment results for {experiment}"
    include_manifest: bool = True
    dry_run: bool = True
    session: requests.Session | None = None
    # Network behavior
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT
    _last_payloads: list[dict[str, Any]] = field(default_factory=list, init=False)
    on_error: str = "abort"
    _allow_missing_token: bool = field(default=False, init=False, repr=False)
    # Throttle spammy warnings to once per process
    _dry_run_warned_once: bool = False
    _strict_dry_run_warned_once: bool = False

    def __post_init__(self) -> None:
        # Validate on_error early for clearer error messages
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")

        # Enforce STRICT mode policy: skip-on-error not permitted for repository sinks
        self._enforce_strict_mode_policy()
        if self.session is None:
            self.session = requests.Session()
            # Mount retry adapter to improve resilience on transient failures
            if HTTP_ADAPTER_CLS is not None and RETRY_CLS is not None:  # pragma: no branch - simple availability check
                retry = RETRY_CLS(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET", "PUT", "POST"],
                )
                adapter = HTTP_ADAPTER_CLS(max_retries=retry)
                # Enforce TLS for all external repository operations
                self.session.mount("https://", adapter)
            else:  # pragma: no cover - optional deps may be absent in limited envs
                logger.debug(
                    "Retry adapter not mounted; proceeding without retries (HTTPAdapter=%s, Retry=%s)",
                    HTTP_ADAPTER_CLS,
                    RETRY_CLS,
                    exc_info=False,
                )
        if self.dry_run:
            cls = self.__class__
            if not cls._dry_run_warned_once:
                logger.warning(DRY_RUN_WARNING_MESSAGE)
                cls._dry_run_warned_once = True
            # In STRICT mode, highlight that dry-run prevents remote writes
            if get_secure_mode() == SecureMode.STRICT and not cls._strict_dry_run_warned_once:
                logger.warning("STRICT mode: repository sink is in dry-run; remote publishing disabled")
                cls._strict_dry_run_warned_once = True

    def _require_session(self) -> requests.Session:
        if self.session is None:  # pragma: no cover - defensive
            raise RuntimeError("session must be initialized")
        return self.session

    def _enforce_strict_mode_policy(self) -> None:
        if get_secure_mode() == SecureMode.STRICT and self.on_error == "skip":
            raise ValueError("Repository sinks cannot use on_error='skip' in STRICT mode")

    def allow_missing_token(self) -> None:
        """Permit missing auth tokens for testing or dry-run scaffolding."""

        self._allow_missing_token = True

    def _should_require_auth_token(self) -> bool:
        return not self.dry_run and not self._allow_missing_token

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        context = _default_context(metadata, timestamp)
        plugin_logger = getattr(self, "plugin_logger", None)

        try:
            prefix = self._resolve_prefix(context)
            files = self._prepare_files(results, metadata, prefix, timestamp)
            commit_message = self.commit_message_template.format(**context)
            payload = self._build_payload(context, commit_message, files)

            self._log_attempt(plugin_logger, prefix, commit_message, len(files))

            if self.dry_run:
                self._handle_dry_run(payload, prefix, len(files), plugin_logger)
                return

            self._upload(files, commit_message, metadata, context, timestamp)
            self._log_success(plugin_logger, prefix, len(files))
        except _RepoRequestError as exc:
            if not self._handle_repo_exception(exc, plugin_logger):
                raise
        except (OSError, RuntimeError) as exc:
            if not self._handle_generic_exception(exc, plugin_logger):
                raise

    def _build_payload(
        self,
        context: Mapping[str, Any],
        commit_message: str,
        files: list[PreparedFile],
    ) -> dict[str, Any]:
        return {
            "context": dict(context),
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

    def _handle_dry_run(
        self,
        payload: dict[str, Any],
        prefix: str,
        file_count: int,
        plugin_logger: Any | None,
    ) -> None:
        payload["dry_run"] = True
        self._last_payloads.append(payload)
        if plugin_logger:
            plugin_logger.log_event(
                "sink_write",
                message=f"Repo dry-run payload prepared: {prefix}",
                metrics={"files": file_count},
                metadata={"repo_path": prefix},
            )

    def _log_attempt(
        self,
        plugin_logger: Any | None,
        prefix: str,
        commit_message: str,
        file_count: int,
    ) -> None:
        if plugin_logger:
            plugin_logger.log_event(
                "sink_write_attempt",
                message=f"Repo write attempt: {prefix}",
                metrics={"files": file_count},
                metadata={"repo_path": prefix, "commit_message": commit_message},
            )

    def _log_success(self, plugin_logger: Any | None, prefix: str, file_count: int) -> None:
        if plugin_logger:
            plugin_logger.log_event(
                "sink_write",
                message=f"Repo write completed: {prefix}",
                metrics={"files": file_count},
                metadata={"repo_path": prefix},
            )

    def _log_plugin_error(self, plugin_logger: Any | None, exc: Exception) -> None:
        if plugin_logger:
            plugin_logger.log_error(exc, context="repo sink write", recoverable=True)

    def _handle_repo_exception(self, exc: _RepoRequestError, plugin_logger: Any | None) -> bool:
        if self.on_error != "skip":
            return False
        if exc.transient:
            logger.warning("Transient repo error; skipping (on_error=skip): %s", exc)
        else:
            logger.warning("Repository sink failed; skipping upload: %s", exc)
        self._log_plugin_error(plugin_logger, exc)
        return True

    def _handle_generic_exception(self, exc: Exception, plugin_logger: Any | None) -> bool:
        if self.on_error != "skip":
            return False
        logger.warning("Repository sink failed; skipping upload: %s", exc)
        self._log_plugin_error(plugin_logger, exc)
        return True

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

    def finalize(
        self, artifacts: Mapping[str, Artifact], *, metadata: dict[str, Any] | None = None
    ) -> None:  # pragma: no cover - optional cleanup
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
    """Publish JSON and binary artifacts to a GitHub repository via REST API."""

    def __init__(
        self,
        *,
        owner: str,
        repo: str,
        branch: str = "main",
        token_env: str = "GITHUB_TOKEN",
        base_url: str = "https://api.github.com",
        fail_fast_missing_token: bool = False,
        **kwargs: Any,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.token_env = token_env
        self.base_url = base_url.rstrip("/")
        self._headers_cache: dict[str, str] | None = None
        self._fail_fast_missing_token = bool(fail_fast_missing_token)
        super().__init__(**kwargs)
        # Optional: Fail-fast on missing token for better UX when not in dry-run
        if self._fail_fast_missing_token and not self.dry_run and not self._read_token(self.token_env):
            raise RuntimeError(f"GitHub token missing; set '{self.token_env}' or enable dry-run mode")

    # Note: Token validation occurs lazily in _headers(); creation does not fail-fast to preserve test behavior.

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
        elif self._should_require_auth_token():
            raise RuntimeError(f"GitHub token missing; set '{self.token_env}' or enable dry-run mode")
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
        session = self._require_session()
        timeout = kwargs.pop("timeout", self.request_timeout)
        response = session.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
        if response.status_code not in expected_status:
            status = response.status_code
            transient = status in {429, 500, 502, 503, 504}
            raise _RepoRequestError(f"GitHub API call failed ({status}): {response.text}", status=status, transient=transient)
        return response


class AzureDevOpsRepoSink(_RepoSinkBase):
    """Publish artifacts to Azure DevOps Git repositories via REST API."""

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
        fail_fast_missing_token: bool = False,
        **kwargs: Any,
    ) -> None:
        self.organization = organization
        self.project = project
        self.repository = repository
        self.branch = branch
        self.token_env = token_env
        self.api_version = api_version
        self.base_url = base_url.rstrip("/")
        self._headers_cache: dict[str, str] | None = None
        self._fail_fast_missing_token = bool(fail_fast_missing_token)
        super().__init__(**kwargs)
        if self._fail_fast_missing_token and not self.dry_run and not self._read_token(self.token_env):
            raise RuntimeError(f"Azure DevOps PAT missing; set '{self.token_env}' or enable dry-run mode")

    # Note: Token validation occurs lazily in _headers(); creation does not fail-fast to preserve test behavior.

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
        elif self._should_require_auth_token():
            raise RuntimeError("Azure DevOps PAT missing; set environment variable AZURE_DEVOPS_PAT or enable dry-run mode")
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
        session = self._require_session()
        timeout = kwargs.pop("timeout", self.request_timeout)
        response = session.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
        if response.status_code not in expected_status:
            status = response.status_code
            transient = status in {429, 500, 502, 503, 504}
            raise _RepoRequestError(f"Azure DevOps API call failed ({status}): {response.text}", status=status, transient=transient)
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
        plugin_logger = getattr(self, "plugin_logger", None)
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
        except _RepoRequestError as exc:
            if not self._handle_repo_exception(exc, plugin_logger):
                raise
        except (OSError, RuntimeError) as exc:
            if not self._handle_generic_exception(exc, plugin_logger):
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
