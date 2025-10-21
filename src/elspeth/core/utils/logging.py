"""Comprehensive plugin logging system for audit and observability.

This module provides structured logging for all Elspeth plugins, capturing:
- Plugin initialization (name, version, path, configuration hash)
- Lifecycle events (load, execute, write, etc.)
- Data flow metrics (rows loaded, tokens used, files written)
- Error conditions and warnings

All logs are written in JSON Lines format for easy parsing and analysis.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from elspeth.core.base.plugin_context import PluginContext

# Optional POSIX file locking for cross-process log serialization
try:  # pragma: no cover - platform dependent
    import fcntl as _fcntl

    _HAS_FCNTL = True
except Exception:  # pragma: no cover - Windows or restricted env
    _HAS_FCNTL = False

class PluginLogger:
    """Structured logger for plugin lifecycle events and metrics.

    Each plugin receives a PluginLogger instance that automatically logs:
    - Initialization with version, path, and configuration hash
    - Lifecycle events (load, execute, write, etc.)
    - Data flow metrics
    - Errors and warnings

    Logs are written in JSON Lines format to a per-run log file.
    """

    def __init__(
        self,
        *,
        plugin_instance: Any,
        context: PluginContext,
        log_dir: Path | None = None,
    ):
        """Initialize plugin logger.

        Args:
            plugin_instance: The plugin instance being logged
            context: Plugin context with metadata
            log_dir: Override log directory (defaults to suite_root/logs)
        """
        self.plugin_instance = plugin_instance
        self.context = context

        # Determine log directory
        if log_dir:
            self.log_dir = Path(log_dir)
        elif context.suite_root:
            self.log_dir = Path(context.suite_root) / "logs"
        else:
            self.log_dir = Path("logs")

        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Standard Python logger for traditional logging (set early for retention logs)
        self.logger = logging.getLogger(f"elspeth.{context.plugin_kind}.{context.plugin_name}")

        # Apply simple retention policy if configured via environment
        # ELSPETH_LOG_MAX_FILES: keep at most N newest files (int > 0)
        # ELSPETH_LOG_MAX_AGE_DAYS: delete files older than given days (int > 0)
        try:
            self._apply_retention()
        except Exception as exc:
            # Retention is best-effort and should never block execution
            self.logger.debug("Log retention maintenance skipped: %s", exc, exc_info=False)

        # Generate run timestamp (shared across all plugins in this run)
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        # Log file path
        self.log_file = self.log_dir / f"run_{self.run_id}.jsonl"
        # Cross-process lock file path (POSIX advisory lock)
        self._lock_file = Path(str(self.log_file) + ".lock")

        # Standard Python logger already set above; recompute name if needed
        # (kept for clarity, but reference is identical)
        self.logger = logging.getLogger(f"elspeth.{context.plugin_kind}.{context.plugin_name}")

        # Serialise file appends across threads (must exist before first write)
        import threading

        self._file_lock = threading.Lock()
        # Log initialization
        self._log_initialization()

    # ------------------------------------------------------------------ retention
    def _apply_retention(self) -> None:
        max_files_raw = os.getenv("ELSPETH_LOG_MAX_FILES")
        max_age_days_raw = os.getenv("ELSPETH_LOG_MAX_AGE_DAYS")
        try:
            max_files = int(max_files_raw) if max_files_raw else None
        except ValueError:
            max_files = None
        try:
            max_age_days = int(max_age_days_raw) if max_age_days_raw else None
        except ValueError:
            max_age_days = None

        # Cache (path, mtime) to avoid repeated stat() calls
        candidates = [(p, p.stat().st_mtime) for p in self.log_dir.glob("run_*.jsonl")]
        candidates.sort(key=lambda x: x[1], reverse=True)
        now = datetime.now(timezone.utc)
        # Safety margin to avoid deleting files that may still be written by another process
        # (in seconds, default 30). Can be overridden via ELSPETH_LOG_RETENTION_SAFETY_SECONDS.
        try:
            safety_sec = int(os.getenv("ELSPETH_LOG_RETENTION_SAFETY_SECONDS", "30"))
        except ValueError:
            safety_sec = 30
        safety_cutoff = now - timedelta(seconds=max(safety_sec, 0))
        # Age-based pruning
        deleted_age = 0
        errors_age = 0
        if max_age_days and max_age_days > 0:
            cutoff = now - timedelta(days=max_age_days)
            for p, mtime in candidates:
                try:
                    mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                    # Skip files newer than the safety margin window
                    if mtime_dt >= safety_cutoff:
                        continue
                    if mtime_dt < cutoff:
                        p.unlink(missing_ok=True)
                        deleted_age += 1
                except (OSError, PermissionError) as exc:
                    # Ignore deletion errors but record for diagnostics
                    errors_age += 1
                    self.logger.debug("Retention age-prune failed for %s: %s", p, exc, exc_info=False)
            # Refresh candidate list after age-based deletions
            candidates = [(p, p.stat().st_mtime) for p in self.log_dir.glob("run_*.jsonl")]
            candidates.sort(key=lambda x: x[1], reverse=True)
            if deleted_age or errors_age:
                level = logging.WARNING if errors_age else logging.DEBUG
                self.logger.log(level, "Retention age-pruned files: %d (errors: %d)", deleted_age, errors_age)
        # Count-based pruning
        deleted_count = 0
        errors_count = 0
        if max_files and max_files > 0 and len(candidates) > max_files:
            for p, _ in candidates[max_files:]:
                try:
                    p.unlink(missing_ok=True)
                    deleted_count += 1
                except (OSError, PermissionError) as exc:
                    errors_count += 1
                    self.logger.debug("Retention count-prune failed for %s: %s", p, exc, exc_info=False)
            if deleted_count or errors_count:
                level = logging.WARNING if errors_count else logging.DEBUG
                self.logger.log(level, "Retention count-pruned files: %d (errors: %d)", deleted_count, errors_count)

    def _compute_config_hash(self) -> str:
        """Compute SHA256 hash of plugin configuration."""
        # Extract configuration from context metadata or plugin attributes
        config_data = {}

        # Try to get options from plugin
        if hasattr(self.plugin_instance, "__dict__"):
            # Filter out private attributes and methods
            config_data = {k: v for k, v in self.plugin_instance.__dict__.items() if not k.startswith("_") and not callable(v)}

        # Serialize and hash
        config_str = json.dumps(config_data, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def _compute_code_hash(self) -> str:
        """Compute SHA256 hash of plugin source code."""
        try:
            source = inspect.getsource(self.plugin_instance.__class__)
            return hashlib.sha256(source.encode()).hexdigest()[:16]
        except (OSError, TypeError):
            # If we can't get source (e.g., built-in class), use class name
            class_name = self.plugin_instance.__class__.__name__
            return hashlib.sha256(class_name.encode()).hexdigest()[:16]

    def _get_plugin_version(self) -> str:
        """Extract plugin version from class or module."""
        # Try class attribute
        if hasattr(self.plugin_instance.__class__, "__version__"):
            return str(self.plugin_instance.__class__.__version__)

        # Try module attribute
        module = inspect.getmodule(self.plugin_instance.__class__)
        if module and hasattr(module, "__version__"):
            return str(module.__version__)

        # Try package version (for installed packages)
        try:
            module_name = self.plugin_instance.__class__.__module__.split(".")[0]
            return importlib.metadata.version(module_name)
        except (importlib.metadata.PackageNotFoundError, AttributeError, ValueError):
            # Package not in metadata or invalid module structure
            return "unknown"

    def _get_plugin_path(self) -> str:
        """Get file path of plugin source code."""
        try:
            return inspect.getfile(self.plugin_instance.__class__)
        except (OSError, TypeError):
            return "unknown"

    def _log_initialization(self) -> None:
        """Log plugin initialization with full metadata."""
        init_event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event_type": "plugin_initialization",
            "plugin": {
                "name": self.context.plugin_name,
                "kind": self.context.plugin_kind,
                "class": self.plugin_instance.__class__.__name__,
                "version": self._get_plugin_version(),
                "path": self._get_plugin_path(),
                "config_hash": self._compute_config_hash(),
                "code_hash": self._compute_code_hash(),
            },
            "context": {
                "security_level": self.context.security_level,
                "determinism_level": self.context.determinism_level,
                "provenance": list(self.context.provenance),
                "suite_root": str(self.context.suite_root) if self.context.suite_root else None,
                "config_path": str(self.context.config_path) if self.context.config_path else None,
            },
        }

        self._write_log_entry(init_event)

        # Also log to standard logger
        plugin_meta = cast(dict[str, Any], init_event.get("plugin", {}))
        config_hash = str(plugin_meta.get("config_hash", "unknown"))
        code_hash = str(plugin_meta.get("code_hash", "unknown"))

        self.logger.info(
            "Plugin initialized: %s (%s) [config_hash=%s, code_hash=%s]",
            self.context.plugin_name,
            self.context.plugin_kind,
            config_hash,
            code_hash,
        )

    def log_event(
        self,
        event_type: str,
        *,
        message: str | None = None,
        metrics: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        """Log a plugin lifecycle event.

        Args:
            event_type: Type of event (e.g., "data_loaded", "llm_request", "sink_write")
            message: Human-readable message
            metrics: Numeric metrics (rows, tokens, bytes, duration, etc.)
            metadata: Additional structured metadata
            level: Log level (debug, info, warning, error)
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event_type": event_type,
            "plugin": {
                "name": self.context.plugin_name,
                "kind": self.context.plugin_kind,
            },
            "level": level,
        }

        if message:
            event["message"] = message

        if metrics:
            event["metrics"] = metrics

        if metadata:
            event["metadata"] = metadata

        self._write_log_entry(event)

        # Also log to standard logger
        log_func = getattr(self.logger, level, self.logger.info)
        msg = message or event_type
        if metrics:
            msg += f" | metrics: {metrics}"
        log_func(msg)

    def log_datasource_event(
        self,
        event: str,
        *,
        rows: int | None = None,
        columns: int | None = None,
        schema: str | None = None,
        source_path: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log datasource-specific event.

        Args:
            event: Event type (connected, loaded, schema_validated, etc.)
            rows: Number of rows
            columns: Number of columns
            schema: Schema name
            source_path: Source file/connection path
            duration_ms: Duration in milliseconds
            metadata: Additional metadata
        """
        metrics: dict[str, int | float] = {}
        if rows is not None:
            metrics["rows"] = rows
        if columns is not None:
            metrics["columns"] = columns
        if duration_ms is not None:
            metrics["duration_ms"] = duration_ms

        meta = metadata or {}
        if schema:
            meta["schema"] = schema
        if source_path:
            meta["source_path"] = source_path

        self.log_event(f"datasource_{event}", metrics=metrics, metadata=meta)

    def log_llm_event(
        self,
        event: str,
        *,
        model: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        duration_ms: float | None = None,
        temperature: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log LLM-specific event.

        Args:
            event: Event type (request_sent, response_received, etc.)
            model: Model name
            prompt_tokens: Prompt token count
            completion_tokens: Completion token count
            total_tokens: Total token count
            duration_ms: Duration in milliseconds
            temperature: Temperature setting
            metadata: Additional metadata
        """
        metrics: dict[str, int | float] = {}
        if prompt_tokens is not None:
            metrics["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            metrics["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            metrics["total_tokens"] = total_tokens
        if duration_ms is not None:
            metrics["duration_ms"] = duration_ms

        meta = metadata or {}
        if model:
            meta["model"] = model
        if temperature is not None:
            meta["temperature"] = temperature

        self.log_event(f"llm_{event}", metrics=metrics, metadata=meta)

    def log_sink_event(
        self,
        event: str,
        *,
        output_path: str | None = None,
        rows_written: int | None = None,
        bytes_written: int | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log sink-specific event.

        Args:
            event: Event type (write_started, write_completed, etc.)
            output_path: Output file/location path
            rows_written: Number of rows written
            bytes_written: Number of bytes written
            duration_ms: Duration in milliseconds
            metadata: Additional metadata
        """
        metrics: dict[str, int | float] = {}
        if rows_written is not None:
            metrics["rows_written"] = rows_written
        if bytes_written is not None:
            metrics["bytes_written"] = bytes_written
        if duration_ms is not None:
            metrics["duration_ms"] = duration_ms

        meta = metadata or {}
        if output_path:
            meta["output_path"] = output_path

        self.log_event(f"sink_{event}", metrics=metrics, metadata=meta)

    def log_error(
        self,
        error: Exception | str,
        *,
        context: str | None = None,
        recoverable: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log an error event.

        Args:
            error: Exception or error message
            context: Context where error occurred
            recoverable: Whether the error is recoverable
            metadata: Additional metadata
        """
        meta = metadata or {}
        meta["recoverable"] = recoverable

        if isinstance(error, Exception):
            meta["error_type"] = error.__class__.__name__
            message = f"{context}: {error}" if context else str(error)
        else:
            message = f"{context}: {error}" if context else error

        self.log_event(
            "error",
            message=message,
            metadata=meta,
            level="error",
        )

    def _write_log_entry(self, entry: dict[str, Any]) -> None:
        """Write a log entry to the JSON Lines log file.

        Args:
            entry: Log entry dictionary
        """
        try:
            with self._file_lock:
                if _HAS_FCNTL:
                    # Use POSIX advisory lock to serialize writes across processes
                    # Create/open the lock file once per write (short critical section)
                    with open(self._lock_file, "a") as lf:  # nosec - lock file path is internal
                        _fcntl.flock(lf, _fcntl.LOCK_EX)
                        try:
                            with open(self.log_file, "a", encoding="utf-8") as f:
                                f.write(json.dumps(entry) + "\n")
                        finally:
                            _fcntl.flock(lf, _fcntl.LOCK_UN)
                else:
                    # Fallback: rely on per-process threading lock only
                    with open(self.log_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry) + "\n")
        except (OSError, IOError) as exc:
            # Fallback to standard logger if file write fails
            self.logger.error("Failed to write log entry: %s", exc)


def attach_plugin_logger(instance: Any, context: PluginContext) -> PluginLogger:
    """Attach a PluginLogger to a plugin instance.

    This function is called automatically by apply_plugin_context().

    Args:
        instance: Plugin instance
        context: Plugin context

    Returns:
        The created PluginLogger
    """
    plugin_logger = PluginLogger(
        plugin_instance=instance,
        context=context,
    )

    # Attach to plugin instance
    setattr(instance, "_elspeth_logger", plugin_logger)
    setattr(instance, "plugin_logger", plugin_logger)

    return plugin_logger


__all__ = ["PluginLogger", "attach_plugin_logger"]
