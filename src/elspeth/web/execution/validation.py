"""Dry-run validation using real engine code paths.

Calls the same functions as `elspeth run`: load_settings(),
instantiate_plugins_from_config(), ExecutionGraph.from_plugin_instances(),
graph.validate(), graph.validate_edge_compatibility().

W18 fix: Only typed exceptions are caught. Bare except Exception is forbidden.
Unknown exception types propagate as 500 Internal Server Error, signalling
that this function needs updating — not that the error should be swallowed.

Temp file pattern: load_settings() takes a file path, NOT yaml content.
YAML is written to a NamedTemporaryFile, the path is passed to load_settings(),
and the file is deleted in a finally block.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.core.config import load_settings
from elspeth.core.dag.graph import ExecutionGraph
from elspeth.core.dag.models import GraphValidationError
from elspeth.web.execution.schemas import (
    ValidationCheck,
    ValidationError,
    ValidationResult,
)

# ── Check names (ordered) ─────────────────────────────────────────────
_CHECK_PATH_ALLOWLIST = "source_path_allowlist"
_CHECK_SETTINGS = "settings_load"
_CHECK_PLUGINS = "plugin_instantiation"
_CHECK_GRAPH = "graph_structure"
_CHECK_SCHEMA = "schema_compatibility"

_ALL_CHECKS = [_CHECK_PATH_ALLOWLIST, _CHECK_SETTINGS, _CHECK_PLUGINS, _CHECK_GRAPH, _CHECK_SCHEMA]


def _skipped_checks(from_check: str) -> list[ValidationCheck]:
    """Generate skipped check records for all checks after from_check."""
    skipping = False
    result: list[ValidationCheck] = []
    for name in _ALL_CHECKS:
        if name == from_check:
            skipping = True
            continue
        if skipping:
            result.append(
                ValidationCheck(
                    name=name,
                    passed=False,
                    detail=f"Skipped: {from_check} failed",
                )
            )
    return result


def _extract_component_id(message: str) -> tuple[str | None, str | None]:
    """Best-effort extraction of component_id and type from error message.

    Parses node IDs like 'gate_1', 'transform_2', 'sink_primary' from
    engine error messages. Returns (component_id, component_type) or
    (None, None) for structural errors.
    """
    # NOTE: This relies on error message string format from the engine.
    # Long-term, the engine should raise structured exceptions with
    # component_id as a field, not embedded in message strings. For MVP
    # this is acceptable — attribution degrades to (None, None), not failure.
    # Common patterns: "in gate_1", "node gate_1", "'gate_1'"
    patterns = [
        r"(?:in |node |'|\")((?:gate|transform|sink|source|aggregation)_\w+)",
        r"((?:gate|transform|sink|source|aggregation)_\w+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            node_id = match.group(1)
            # Extract type from prefix
            for prefix in ("gate", "transform", "sink", "source", "aggregation"):
                if node_id.startswith(prefix):
                    return node_id, prefix
    return None, None


def validate_pipeline(state: Any, settings: Any, yaml_generator: Any) -> ValidationResult:
    """Dry-run validation through the real engine code path.

    Steps:
    1. Source path allowlist check (C3/S2 defense-in-depth)
    2. Generate YAML from CompositionState
    3. Write to temp file, load_settings(path) — NOT yaml content
    4. instantiate_plugins_from_config(settings)
    5. ExecutionGraph.from_plugin_instances(bundle fields)
    6. graph.validate() + graph.validate_edge_compatibility()

    Only catches: PydanticValidationError, FileNotFoundError, ValueError,
    GraphValidationError. All other exceptions propagate (W18).

    Args:
        state: CompositionState from the session.
        settings: WebSettings — used for path allowlist check.
        yaml_generator: YamlGenerator module/object with generate_yaml() method.
    """
    checks: list[ValidationCheck] = []
    errors: list[ValidationError] = []
    tmp_path: Path | None = None

    # Step 1: Source path allowlist check (C3/S2 defense-in-depth)
    # Any `path` or `file` key in source options must resolve under
    # an allowed source directory. Uses the shared helper from AD-4.
    from elspeth.web.composer.tools import _allowed_source_directories

    allowed_dirs = _allowed_source_directories(str(settings.data_dir))
    # state is a CompositionState (typed domain object). state.source is a
    # SourceSpec with typed .options attribute (Mapping[str, Any]).
    source_options = dict(state.source.options) if state.source is not None else {}
    path_checked = False
    for key in ("path", "file"):
        value = source_options.get(key)
        if value is not None:
            path_checked = True
            resolved = Path(value).resolve()
            if not any(resolved.is_relative_to(d) for d in allowed_dirs):
                return ValidationResult(
                    is_valid=False,
                    checks=[
                        ValidationCheck(
                            name="source_path_allowlist",
                            passed=False,
                            detail=f"Source {key} '{value}' is outside allowed source directories",
                        ),
                        *_skipped_checks("source_path_allowlist"),
                    ],
                    errors=[
                        ValidationError(
                            component_id="source",
                            component_type="source",
                            message=f"Path traversal blocked: {key}='{value}' resolves outside allowed directories",
                            suggestion="Use a file within the uploads or blobs directory.",
                        ),
                    ],
                )
    # B11 fix: Always record the source_path_allowlist check
    if path_checked:
        checks.append(
            ValidationCheck(
                name=_CHECK_PATH_ALLOWLIST,
                passed=True,
                detail="Source path within allowed upload directory",
            )
        )
    else:
        checks.append(
            ValidationCheck(
                name=_CHECK_PATH_ALLOWLIST,
                passed=True,
                detail="No path option — check skipped",
            )
        )

    # Step 2: Generate YAML
    pipeline_yaml = yaml_generator.generate_yaml(state)

    # Step 3: Settings loading
    try:
        tmp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)  # noqa: SIM115
        tmp_path = Path(tmp_file.name)
        tmp_file.write(pipeline_yaml)
        tmp_file.close()

        elspeth_settings = load_settings(tmp_path)
        checks.append(
            ValidationCheck(
                name=_CHECK_SETTINGS,
                passed=True,
                detail="Settings loaded successfully",
            )
        )
    except (PydanticValidationError, FileNotFoundError, ValueError) as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_SETTINGS,
                passed=False,
                detail=str(exc),
            )
        )
        errors.append(
            ValidationError(
                component_id=None,
                component_type=None,
                message=str(exc),
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_SETTINGS))
        return ValidationResult(is_valid=False, checks=checks, errors=errors)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()

    # Step 4: Plugin instantiation
    try:
        bundle = instantiate_plugins_from_config(elspeth_settings)
        checks.append(
            ValidationCheck(
                name=_CHECK_PLUGINS,
                passed=True,
                detail="All plugins instantiated",
            )
        )
    except ValueError as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_PLUGINS,
                passed=False,
                detail=str(exc),
            )
        )
        comp_id, comp_type = _extract_component_id(str(exc))
        errors.append(
            ValidationError(
                component_id=comp_id,
                component_type=comp_type,
                message=str(exc),
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_PLUGINS))
        return ValidationResult(is_valid=False, checks=checks, errors=errors)

    # Step 5: Graph construction + structural validation
    try:
        graph = ExecutionGraph.from_plugin_instances(
            source=bundle.source,
            source_settings=bundle.source_settings,
            transforms=bundle.transforms,
            sinks=bundle.sinks,
            aggregations=bundle.aggregations,
            gates=list(elspeth_settings.gates),
            coalesce_settings=(list(elspeth_settings.coalesce) if elspeth_settings.coalesce else None),
        )
        graph.validate()
        checks.append(
            ValidationCheck(
                name=_CHECK_GRAPH,
                passed=True,
                detail="Graph structure is valid",
            )
        )
    except GraphValidationError as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_GRAPH,
                passed=False,
                detail=str(exc),
            )
        )
        comp_id, comp_type = _extract_component_id(str(exc))
        errors.append(
            ValidationError(
                component_id=comp_id,
                component_type=comp_type,
                message=str(exc),
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_GRAPH))
        return ValidationResult(is_valid=False, checks=checks, errors=errors)

    # Step 6: Schema compatibility
    try:
        graph.validate_edge_compatibility()
        checks.append(
            ValidationCheck(
                name=_CHECK_SCHEMA,
                passed=True,
                detail="All edge schemas compatible",
            )
        )
    except GraphValidationError as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_SCHEMA,
                passed=False,
                detail=str(exc),
            )
        )
        comp_id, comp_type = _extract_component_id(str(exc))
        errors.append(
            ValidationError(
                component_id=comp_id,
                component_type=comp_type,
                message=str(exc),
                suggestion=None,
            )
        )
        return ValidationResult(is_valid=False, checks=checks, errors=errors)

    return ValidationResult(is_valid=True, checks=checks, errors=errors)
