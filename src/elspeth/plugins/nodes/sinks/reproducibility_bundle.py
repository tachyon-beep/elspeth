"""Reproducibility bundle sink for complete audit trail and experiment reconstruction.

Creates a cryptographically signed archive containing:
- Experiment results (JSON, CSV)
- Source data snapshot (downloaded from remote datasources)
- Complete configuration files
- Rendered prompts sent to LLM
- Plugin source code used
- Optional: Framework source code
- Signed manifest with SHA256 hashes of all files
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security import generate_signature
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink

logger = logging.getLogger(__name__)

_ERROR_MSG_TEMP_DIR_NOT_INITIALIZED = "temporary directory not initialized"


@dataclass
class ReproducibilityBundleSink(BasePlugin, ResultSink):
    """Create a tamper-evident reproducibility bundle with results, metadata, and code.

    Inherits from BasePlugin to provide security enforcement (ADR-004).
    """

    base_path: str | Path
    bundle_name: str | None = None
    timestamped: bool = True

    # Content options
    include_results_json: bool = True
    include_results_csv: bool = True
    include_source_data: bool = True
    include_config: bool = True
    include_prompts: bool = True
    include_plugins: bool = True
    include_framework_code: bool = False  # Large - only for critical audits

    # File names
    results_json_name: str = "results.json"
    results_csv_name: str = "results.csv"
    source_data_name: str = "source_data.csv"
    config_name: str = "config.yaml"
    prompts_name: str = "prompts.json"
    manifest_name: str = "MANIFEST.json"
    signature_name: str = "SIGNATURE.json"

    # Signing
    algorithm: str = "hmac-sha256"
    key: str | None = None
    key_env: str | None = "ELSPETH_SIGNING_KEY"

    # Behavior
    on_error: str = "abort"
    sanitize_formulas: bool = True
    sanitize_guard: str = "'"
    compression: str = "gz"  # gz, bz2, xz, or none
    security_level: SecurityLevel = SecurityLevel.OFFICIAL  # REQUIRED (ADR-004) - default to OFFICIAL
    allow_downgrade: bool = True  # ADR-005: Sinks are trusted to downgrade (hard-coded policy, not user-configurable)

    # Internal state
    _temp_dir: Path | None = field(default=None, init=False, repr=False)
    _file_hashes: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _consumed_artifacts: dict[str, list[Artifact]] = field(default_factory=dict, init=False, repr=False)
    _last_archive_path: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Normalize configuration and validate on_error early."""
        # Initialize BasePlugin with security level and downgrade policy (ADR-004, ADR-005)
        super().__init__(security_level=self.security_level, allow_downgrade=self.allow_downgrade)

        self.base_path = Path(self.base_path)
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        if self.compression not in {"gz", "bz2", "xz", "none"}:
            raise ValueError("compression must be one of: gz, bz2, xz, none")

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        """Create reproducibility bundle with cryptographic signing."""
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)

        try:
            plugin_logger = getattr(self, "plugin_logger", None)
            if plugin_logger:
                plugin_logger.log_event(
                    "sink_write_attempt",
                    message=f"Reproducibility bundle attempt: {self.base_path}/{self.bundle_name or 'bundle'}",
                    metadata={"path": str(self.base_path)},
                )
            # Create temporary directory for bundle contents
            self._temp_dir = Path(tempfile.mkdtemp(prefix="elspeth_repro_"))

            # Write all bundle components
            if self.include_results_json:
                self._write_results_json(results)

            if self.include_results_csv:
                self._write_results_csv(results, metadata)

            if self.include_source_data:
                self._write_source_data(metadata)

            if self.include_config:
                self._write_config(metadata)

            if self.include_prompts:
                self._write_prompts(results, metadata)

            if self.include_plugins:
                self._write_plugins(metadata)

            if self.include_framework_code:
                self._write_framework_code()

            # Write consumed artifacts from other sinks
            self._write_consumed_artifacts()

            # Generate manifest with file hashes
            manifest = self._build_manifest(results, metadata, timestamp)
            temp_dir = self._ensure_temp_dir()
            manifest_path = temp_dir / self.manifest_name
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            self._file_hashes[self.manifest_name] = self._hash_file(manifest_path)

            # Sign the manifest
            signature_data = self._sign_manifest(manifest, timestamp)
            temp_dir = self._ensure_temp_dir()
            signature_path = temp_dir / self.signature_name
            signature_path.write_text(json.dumps(signature_data, indent=2, sort_keys=True), encoding="utf-8")

            # Create final tarball
            archive_path = self._create_archive(metadata, timestamp)
            self._last_archive_path = str(archive_path)

            if plugin_logger:
                try:
                    size = archive_path.stat().st_size
                except OSError:
                    size = 0
                plugin_logger.log_event(
                    "sink_write",
                    message=f"Reproducibility bundle created: {archive_path.name}",
                    metrics={"files": len(self._file_hashes), "bytes": size},
                    metadata={"path": str(archive_path)},
                )

        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Reproducibility bundle creation failed; skipping: %s", exc)
                plugin_logger = getattr(self, "plugin_logger", None)
                if plugin_logger:
                    plugin_logger.log_error(exc, context="reproducibility bundle write", recoverable=True)
                return
            raise
        finally:
            # Cleanup temp directory
            if self._temp_dir and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
            self._file_hashes = {}
            self._consumed_artifacts = {}

    def _write_results_json(self, results: dict[str, Any]) -> None:
        """Write results as JSON with sorted keys."""
        temp_dir = self._ensure_temp_dir()
        path = temp_dir / self.results_json_name
        # Use custom encoder to handle non-serializable objects
        content = json.dumps(results, indent=2, sort_keys=True, default=self._json_serializer)
        path.write_text(content, encoding="utf-8")
        self._file_hashes[self.results_json_name] = self._hash_string(content)
        logger.debug("Wrote results JSON: %s rows", len(results.get("results", [])))

    def _write_results_csv(self, results: dict[str, Any], metadata: dict[str, Any]) -> None:
        """Write results as sanitized CSV."""
        temp_dir = self._ensure_temp_dir()
        path = temp_dir / self.results_csv_name
        csv_sink = CsvResultSink(
            path=str(path),
            overwrite=True,
            sanitize_formulas=self.sanitize_formulas,
            sanitize_guard=self.sanitize_guard,
            security_level=self.security_level,  # Propagate security level to nested sink (ADR-004)
        )
        csv_sink.write(results, metadata=metadata)
        if path.exists():
            self._file_hashes[self.results_csv_name] = self._hash_file(path)
            logger.debug("Wrote results CSV: %s", self._format_size(path.stat().st_size))

    def _write_source_data(self, metadata: dict[str, Any]) -> None:
        """Write source data snapshot from datasource."""
        source_data = metadata.get("source_data")
        datasource_config = metadata.get("datasource_config")

        retained_path = self._get_retained_path(source_data)
        if retained_path and Path(retained_path).exists():
            self._copy_retained_file(retained_path)
        elif self._is_dataframe(source_data):
            # DataFrame available but no retained copy - save it now
            self._write_source_dataframe(source_data)
            logger.warning("Source data was not retained locally by datasource; saved from DataFrame (may lose original formatting)")

        if datasource_config:
            # Always save datasource config for reference
            self._write_datasource_config(datasource_config)

        if not retained_path and source_data is None:
            logger.warning("Source data not available; skipping snapshot")

    # ---- helpers for source data writing ---------------------------------
    def _ensure_temp_dir(self) -> Path:
        if self._temp_dir is None:  # pragma: no cover - defensive
            raise RuntimeError(_ERROR_MSG_TEMP_DIR_NOT_INITIALIZED)
        return self._temp_dir

    @staticmethod
    def _is_dataframe(obj: Any) -> bool:
        try:
            import pandas as pd  # pylint: disable=import-outside-toplevel

            return isinstance(obj, pd.DataFrame)
        except (ImportError, AttributeError):
            return False

    def _get_retained_path(self, source_data: Any) -> str | None:
        if not self._is_dataframe(source_data):
            return None
        try:
            value = source_data.attrs.get("retained_local_path")
            return value if isinstance(value, str) or value is None else None
        except AttributeError:
            return None

    def _copy_retained_file(self, retained_path: str) -> None:
        temp_dir = self._ensure_temp_dir()
        dest_path = temp_dir / self.source_data_name
        shutil.copy2(retained_path, dest_path)
        self._file_hashes[self.source_data_name] = self._hash_file(dest_path)
        logger.debug("Copied retained source data from %s (%d bytes)", retained_path, dest_path.stat().st_size)

    def _write_source_dataframe(self, df: Any) -> None:
        temp_dir = self._ensure_temp_dir()
        path = temp_dir / self.source_data_name
        # pandas import handled in _is_dataframe
        df.to_csv(path, index=False)
        self._file_hashes[self.source_data_name] = self._hash_file(path)
        try:
            rows = len(df)
        except TypeError:
            rows = 0
        logger.debug("Wrote source data snapshot: %d rows", rows)

    def _write_datasource_config(self, datasource_config: Any) -> None:
        temp_dir = self._ensure_temp_dir()
        config_path = temp_dir / "datasource_config.json"
        config_path.write_text(json.dumps(datasource_config, indent=2, sort_keys=True), encoding="utf-8")
        self._file_hashes["datasource_config.json"] = self._hash_file(config_path)
        logger.debug("Wrote datasource config")

    def _write_config(self, metadata: dict[str, Any]) -> None:
        """Write complete experiment configuration."""
        config = metadata.get("config") or metadata.get("experiment_config")

        if config:
            temp_dir = self._ensure_temp_dir()
            path = temp_dir / self.config_name
            if isinstance(config, dict):
                # Convert dict to YAML
                import yaml  # pylint: disable=import-outside-toplevel

                content = yaml.dump(config, default_flow_style=False, sort_keys=True)
            else:
                content = str(config)
            path.write_text(content, encoding="utf-8")
            self._file_hashes[self.config_name] = self._hash_string(content)
            logger.debug("Wrote experiment configuration")
        else:
            logger.warning("Configuration not available in metadata; skipping")

    def _write_prompts(self, results: dict[str, Any], metadata: dict[str, Any]) -> None:
        """Extract and write all rendered prompts sent to LLM."""
        prompts = []

        # Extract prompts from results
        for idx, entry in enumerate(results.get("results", [])):
            if isinstance(entry, dict):
                request = entry.get("request") or entry.get("llm_request")
                if isinstance(request, dict):
                    prompts.append(
                        {
                            "row_index": idx,
                            "system_prompt": request.get("system_prompt"),
                            "user_prompt": request.get("user_prompt"),
                            "metadata": request.get("metadata", {}),
                        }
                    )

        # Also check metadata for prompt templates
        if metadata.get("prompt_templates"):
            prompts.append(
                {
                    "type": "templates",
                    "data": metadata["prompt_templates"],
                }
            )

        if prompts:
            temp_dir = self._ensure_temp_dir()
            path = temp_dir / self.prompts_name
            path.write_text(json.dumps(prompts, indent=2, sort_keys=True), encoding="utf-8")
            self._file_hashes[self.prompts_name] = self._hash_file(path)
            logger.debug("Wrote %d prompts", len([p for p in prompts if "row_index" in p]))
        else:
            logger.warning("No prompts found in results; skipping")

    def _write_plugins(self, metadata: dict[str, Any]) -> None:
        """Copy source code of all plugins used in this experiment."""
        temp_dir = self._ensure_temp_dir()
        plugins_dir = temp_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)

        plugin_info_raw = metadata.get("plugins")
        plugin_info = plugin_info_raw if isinstance(plugin_info_raw, Mapping) else {}
        copied = 0

        for plugin_type, plugin_name in self._iter_plugin_metadata(plugin_info):
            source_path = self._find_plugin_source(plugin_name, plugin_type)
            if source_path and source_path.exists():
                dest_path = plugins_dir / f"{plugin_type}_{plugin_name}.py"
                shutil.copy2(source_path, dest_path)
                rel_path = f"plugins/{dest_path.name}"
                self._file_hashes[rel_path] = self._hash_file(dest_path)
                copied += 1

        if copied > 0:
            logger.debug("Copied %d plugin source files", copied)
        else:
            logger.warning("No plugin source files found; skipping")

    def _iter_plugin_metadata(self, plugin_info: Mapping[str, Any]) -> Iterator[tuple[str, str]]:
        """Yield normalized plugin metadata entries as (type, name) pairs."""
        for plugin_type, plugin_list in plugin_info.items():
            for entry in self._iter_plugin_values(plugin_list):
                normalized_name = self._extract_plugin_name(entry)
                if normalized_name is not None:
                    yield plugin_type, normalized_name

    def _iter_plugin_values(self, plugin_list: Any) -> Iterator[Any]:
        """Iterate over plugin metadata entries regardless of container type."""
        if not plugin_list:
            return
        if isinstance(plugin_list, list):
            for entry in plugin_list:
                if entry:
                    yield entry
            return
        yield plugin_list

    def _extract_plugin_name(self, entry: Any) -> str | None:
        """Return normalized plugin name or None if not resolvable."""
        candidate = entry
        if isinstance(candidate, Mapping):
            candidate = candidate.get("name") or candidate.get("plugin")

        if not isinstance(candidate, str):
            logger.warning("Skipping plugin entry with unsupported type: %r", entry)
            return None

        normalized_name = candidate.strip()
        if not normalized_name:
            logger.warning("Skipping plugin entry with empty name: %r", entry)
            return None

        return normalized_name

    def _find_plugin_source(self, plugin_name: str, plugin_type: str) -> Path | None:
        """Locate plugin source file by name and type."""
        # Common plugin locations
        search_paths = [
            Path(__file__).parent,  # Same dir as this sink
            Path(__file__).parent.parent / "transforms" / "llm",  # LLM middleware
            Path(__file__).parent.parent / "datasources",  # Datasources
            Path(__file__).parent.parent.parent / "plugins" / "experiments",  # Experiment plugins
        ]

        # Try various filename patterns
        patterns = [
            f"{plugin_name}.py",
            f"middleware_{plugin_name}.py",
            f"{plugin_type}_{plugin_name}.py",
        ]

        for search_path in search_paths:
            if not search_path.exists():
                continue
            for pattern in patterns:
                candidate = search_path / pattern
                if candidate.exists():
                    return candidate

        return None

    def _write_framework_code(self) -> None:
        """Create snapshot of Elspeth framework source code."""
        framework_dir = Path(__file__).parent.parent.parent.parent  # src/elspeth

        if not framework_dir.exists():
            logger.warning("Framework source directory not found; skipping")
            return

        # Create tarball of framework code
        temp_dir = self._ensure_temp_dir()
        framework_tar = temp_dir / "framework_source.tar.gz"
        with tarfile.open(framework_tar, "w:gz") as tar:
            tar.add(framework_dir, arcname="elspeth", filter=self._filter_framework_files)

        self._file_hashes["framework_source.tar.gz"] = self._hash_file(framework_tar)
        logger.debug("Wrote framework source snapshot: %s", self._format_size(framework_tar.stat().st_size))

    @staticmethod
    def _filter_framework_files(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
        """Filter out non-essential framework files."""
        # Skip pycache, .pyc files, test files
        if "__pycache__" in tarinfo.name or tarinfo.name.endswith(".pyc"):
            return None
        if "/tests/" in tarinfo.name or "/test_" in tarinfo.name:
            return None
        return tarinfo

    def _write_consumed_artifacts(self) -> None:
        """Write artifacts consumed from other sinks."""
        if not self._consumed_artifacts:
            return

        temp_dir = self._ensure_temp_dir()
        artifacts_dir = temp_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)

        for artifact_type, artifacts in self._consumed_artifacts.items():
            for idx, artifact in enumerate(artifacts):
                filename = f"{artifact_type}_{idx}"
                if artifact.path:
                    src_path = Path(artifact.path)
                    dest_path = artifacts_dir / src_path.name
                    shutil.copy2(src_path, dest_path)
                    rel_path = f"artifacts/{dest_path.name}"
                    self._file_hashes[rel_path] = self._hash_file(dest_path)
                elif artifact.payload:
                    dest_path = artifacts_dir / f"{filename}.json"
                    dest_path.write_text(json.dumps(artifact.payload, indent=2, sort_keys=True), encoding="utf-8")
                    rel_path = f"artifacts/{dest_path.name}"
                    self._file_hashes[rel_path] = self._hash_file(dest_path)

    def _build_manifest(
        self,
        results: dict[str, Any],
        metadata: dict[str, Any],
        timestamp: datetime,
    ) -> dict[str, Any]:
        """Build comprehensive manifest with file hashes and metadata."""
        return {
            "bundle_type": "elspeth_reproducibility_bundle",
            "version": "1.0",
            "generated_at": timestamp.isoformat(),
            "experiment": {
                "name": metadata.get("experiment") or metadata.get("name"),
                "rows": len(results.get("results", [])),
                "failures": len(results.get("failures", [])),
                "aggregates": results.get("aggregates"),
                "cost_summary": results.get("cost_summary"),
            },
            "metadata": {
                k: v
                for k, v in metadata.items()
                if k not in {"source_data", "config", "plugins"}  # Already captured separately
            },
            "files": {
                "count": len(self._file_hashes),
                "hashes": self._file_hashes,
                "algorithm": "sha256",
            },
            "sanitization": {
                "enabled": self.sanitize_formulas,
                "guard": self.sanitize_guard,
            },
            "bundle_options": {
                "include_source_data": self.include_source_data,
                "include_config": self.include_config,
                "include_prompts": self.include_prompts,
                "include_plugins": self.include_plugins,
                "include_framework_code": self.include_framework_code,
            },
        }

    def _sign_manifest(self, manifest: dict[str, Any], timestamp: datetime) -> dict[str, Any]:
        """Cryptographically sign the manifest."""
        key = self._resolve_signing_key()
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
        algo: Literal["hmac-sha256", "hmac-sha512"] = "hmac-sha256" if self.algorithm == "hmac-sha256" else "hmac-sha512"
        signature = generate_signature(manifest_bytes, key, algorithm=algo)

        return {
            "algorithm": self.algorithm,
            "signature": signature,
            "signed_at": timestamp.isoformat(),
            "target": self.manifest_name,
            "manifest_hash": hashlib.sha256(manifest_bytes).hexdigest(),
        }

    def _resolve_signing_key(self) -> str:
        """Resolve signing key from config or environment."""
        if self.key:
            return self.key
        if self.key_env:
            env_value = os.getenv(self.key_env)
            if env_value:
                return env_value
        raise ValueError(f"Signing key not provided; set 'key' option or {self.key_env} environment variable")

    def _create_archive(self, metadata: dict[str, Any], timestamp: datetime) -> Path:
        """Create final compressed tarball."""
        temp_dir = self._ensure_temp_dir()
        name = self.bundle_name or str(metadata.get("experiment") or metadata.get("name") or "experiment")
        if self.timestamped:
            name = f"{name}_{timestamp.strftime('%Y%m%dT%H%M%SZ')}"

        # Determine compression mode
        if self.compression == "none":
            mode = "w"
            ext = ".tar"
        else:
            mode = f"w:{self.compression}"
            ext = f".tar.{self.compression}"

        archive_path = Path(self.base_path) / f"{name}{ext}"
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, mode) as tar:  # type: ignore[call-overload]
            tar.add(temp_dir, arcname=name)

        return archive_path

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _hash_string(content: str) -> str:
        """Calculate SHA256 hash of string."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size for logging."""
        size_float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size_float < 1024.0:
                return f"{size_float:.1f} {unit}"
            size_float /= 1024.0
        return f"{size_float:.1f} TB"

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Custom JSON serializer for objects not serializable by default json encoder.

        Handles common non-serializable types from LLM responses, DataFrames, etc.
        """
        # Handle Pydantic models (OpenAI responses use these)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()

        # Handle objects with to_dict method
        if hasattr(obj, "to_dict"):
            return obj.to_dict()

        # Handle objects with dict representation
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}

        # Fallback to string representation
        return str(obj)

    # Artifact chaining protocol

    def produces(self) -> list[ArtifactDescriptor]:
        """Declare produced artifacts."""
        ext = "tar.gz" if self.compression == "gz" else f"tar.{self.compression}"
        return [
            ArtifactDescriptor(
                name="reproducibility_bundle",
                type=f"file/{ext}",
                persist=True,
                alias="repro_bundle",
            )
        ]

    def consumes(self) -> list[str]:
        """Declare consumed artifact types (consume all)."""
        return []  # Empty means consume all available artifacts

    def prepare_artifacts(self, artifacts: Mapping[str, list[Artifact]]) -> None:
        """Receive artifacts from upstream sinks."""
        self._consumed_artifacts = {k: list(v) for k, v in artifacts.items() if v}

    def collect_artifacts(self) -> dict[str, Artifact]:
        """Provide bundle artifact for downstream consumption."""
        if not self._last_archive_path:
            return {}

        # Initialize with required args only; set optional fields explicitly to
        # keep static analyzers happy about dataclass construction.
        artifact = Artifact("reproducibility_bundle", f"file/tar.{self.compression}")
        artifact.path = self._last_archive_path
        artifact.metadata = {
            "bundle_type": "reproducibility",
            "signed": True,
            "compression": self.compression,
        }
        artifact.persist = True

        self._last_archive_path = None
        return {"reproducibility_bundle": artifact}

    def finalize(self, artifacts: Mapping[str, Artifact], *, metadata: dict[str, Any] | None = None) -> None:
        """Optional cleanup after sink pipeline completes."""
        return None


__all__ = ["ReproducibilityBundleSink"]
