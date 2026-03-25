"""Pipeline dependency resolution — cycle detection, depth limiting, and execution."""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from elspeth.contracts.errors import DependencyFailedError
from elspeth.core.canonical import canonical_json
from elspeth.core.dependency_config import DependencyConfig, DependencyRunResult
from elspeth.engine.bootstrap import bootstrap_and_run


def _load_depends_on(settings_path: Path) -> list[dict[str, str]]:
    """Load only the depends_on key from a settings file.

    This reads raw YAML (not Pydantic-validated config) specifically
    for cycle detection. The depends_on key is optional — absent means
    no dependencies, which is the common case for leaf pipelines.
    """
    with settings_path.open() as f:
        data = yaml.safe_load(f) or {}
    # depends_on is optional in pipeline configs — absence means no dependencies.
    # This is a Tier 3 boundary (raw YAML from operator-authored files).
    deps: list[dict[str, str]] = data.get("depends_on", [])
    return deps


def detect_cycles(
    settings_path: Path,
    *,
    max_depth: int = 3,
    _visited: set[str] | None = None,
    _stack: list[str] | None = None,
    _depth: int = 0,
) -> None:
    """Detect circular dependencies and enforce depth limit.

    Uses DFS on canonicalized (resolved) paths.
    Raises ValueError on cycle or depth limit violation.
    """
    canonical = str(settings_path.resolve())
    visited = _visited if _visited is not None else set()
    stack = _stack if _stack is not None else []

    if _depth >= max_depth:
        raise ValueError(f"Dependency depth limit exceeded ({max_depth}). Chain: {' -> '.join(stack)} -> {canonical}")

    if canonical in stack:
        cycle_start = stack.index(canonical)
        cycle_path = [*stack[cycle_start:], canonical]
        raise ValueError(f"Circular dependency detected: {' -> '.join(cycle_path)}")

    if canonical in visited:
        return  # Already fully explored, no cycle through this node

    stack.append(canonical)
    deps = _load_depends_on(settings_path)

    for dep in deps:
        dep_path = (settings_path.parent / dep["settings"]).resolve()
        detect_cycles(
            Path(dep_path),
            max_depth=max_depth,
            _visited=visited,
            _stack=stack,
            _depth=_depth + 1,
        )

    stack.pop()
    visited.add(canonical)


def _hash_settings_file(path: Path) -> str:
    """SHA-256 hash of the canonical JSON representation of settings."""
    with path.open() as f:
        data = yaml.safe_load(f)
    canonical = canonical_json(data)
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def resolve_dependencies(
    *,
    depends_on: list[DependencyConfig],
    parent_settings_path: Path,
) -> list[DependencyRunResult]:
    """Run dependency pipelines sequentially. Raises on failure.

    KeyboardInterrupt is propagated as-is (not wrapped in DependencyFailedError).
    """
    results: list[DependencyRunResult] = []
    for dep in depends_on:
        dep_path = (parent_settings_path.parent / dep.settings).resolve()

        start_ms = time.monotonic_ns() // 1_000_000
        run_result = bootstrap_and_run(dep_path)
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

        if run_result.status.name != "COMPLETED":
            raise DependencyFailedError(
                dependency_name=dep.name,
                run_id=run_result.run_id,
                reason=f"Dependency pipeline finished with status: {run_result.status.name}",
            )

        results.append(
            DependencyRunResult(
                name=dep.name,
                run_id=run_result.run_id,
                settings_hash=_hash_settings_file(dep_path),
                duration_ms=duration_ms,
                indexed_at=datetime.now(UTC).isoformat(),
            )
        )
    return results
