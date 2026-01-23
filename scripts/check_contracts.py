#!/usr/bin/env python3
"""AST-based enforcement for contracts package.

Scans the codebase for:
1. dataclasses, TypedDicts, NamedTuples, and Enums used across module boundaries
2. dict[str, Any] type hints that should be typed contracts

Also validates that all whitelist entries are still valid (not stale).

Usage:
    python scripts/check_contracts.py
    python scripts/check_contracts.py --no-fail-on-stale  # Skip stale check

Exit codes:
    0: All contracts properly centralized
    1: Violations found or stale whitelist entries
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]


@dataclass
class Violation:
    """A contract violation found during scanning."""

    file: str
    line: int
    type_name: str
    kind: str
    used_in: list[str]


@dataclass
class DictViolation:
    """A dict[str, Any] usage that should be a typed contract."""

    file: str
    line: int
    context: str  # function name or class.method
    param_name: str  # parameter name or "return"


@dataclass
class StaleEntry:
    """A whitelist entry that doesn't match any code."""

    entry: str
    category: str  # "type" or "dict_pattern"
    reason: str


@dataclass
class WhitelistEntry:
    """Tracked whitelist entry with match status."""

    value: str
    category: str
    matched: bool = field(default=False)


def load_whitelist(path: Path) -> tuple[dict[str, set[str]], list[WhitelistEntry]]:
    """Load whitelisted type definitions and dict patterns.

    Returns:
        Tuple of (whitelist dict for matching, list of entries for stale tracking)
    """
    if not path.exists():
        return {"types": set(), "dicts": set()}, []

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    entries: list[WhitelistEntry] = []

    type_entries = data.get("allowed_external_types", [])
    dict_entries = data.get("allowed_dict_patterns", [])

    for t in type_entries:
        entries.append(WhitelistEntry(value=t, category="type"))
    for d in dict_entries:
        entries.append(WhitelistEntry(value=d, category="dict_pattern"))

    return {
        "types": set(type_entries),
        "dicts": set(dict_entries),
    }, entries


def find_type_definitions(file_path: Path) -> list[tuple[str, int, str]]:
    """Find dataclass, TypedDict, NamedTuple, Enum definitions in a file.

    Returns: List of (type_name, line_number, kind)
    """
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        # Skip files that cannot be parsed (syntax errors or invalid encoding)
        return []

    definitions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check for @dataclass decorator
            for decorator in node.decorator_list:
                is_dataclass_name = isinstance(decorator, ast.Name) and decorator.id == "dataclass"
                is_dataclass_call = (
                    isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "dataclass"
                )
                if is_dataclass_name or is_dataclass_call:
                    definitions.append((node.name, node.lineno, "dataclass"))

            # Check for TypedDict, NamedTuple, Enum base classes
            for base in node.bases:
                if isinstance(base, ast.Name):
                    if base.id == "TypedDict":
                        definitions.append((node.name, node.lineno, "TypedDict"))
                    elif base.id == "NamedTuple":
                        definitions.append((node.name, node.lineno, "NamedTuple"))
                    elif base.id == "Enum":
                        definitions.append((node.name, node.lineno, "Enum"))
                    elif base.id in ("BaseModel", "PluginSchema"):
                        # Pydantic models in config are OK (trust boundary)
                        pass

    return definitions


def _is_dict_str_any(annotation: ast.expr | None) -> bool:
    """Check if annotation is dict[str, Any] or Dict[str, Any]."""
    if annotation is None:
        return False

    # dict[str, Any] - modern syntax
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id in ("dict", "Dict")
        and isinstance(annotation.slice, ast.Tuple)
        and len(annotation.slice.elts) == 2
    ):
        key_type, value_type = annotation.slice.elts
        if isinstance(key_type, ast.Name) and key_type.id == "str" and isinstance(value_type, ast.Name) and value_type.id == "Any":
            return True
    return False


def _is_list_of_dict_str_any(annotation: ast.expr | None) -> bool:
    """Check if annotation is list[dict[str, Any]]."""
    if annotation is None:
        return False

    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name) and annotation.value.id in ("list", "List"):
        return _is_dict_str_any(annotation.slice)
    return False


def _is_optional_dict(annotation: ast.expr | None) -> bool:
    """Check if annotation is dict[str, Any] | None."""
    if annotation is None:
        return False

    # dict[str, Any] | None
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left_is_dict = _is_dict_str_any(annotation.left)
        right_is_none = isinstance(annotation.right, ast.Constant) and annotation.right.value is None
        if left_is_dict and right_is_none:
            return True
        # None | dict[str, Any]
        left_is_none = isinstance(annotation.left, ast.Constant) and annotation.left.value is None
        right_is_dict = _is_dict_str_any(annotation.right)
        if left_is_none and right_is_dict:
            return True
    return False


def _is_union_with_dict(annotation: ast.expr | None) -> bool:
    """Check if annotation contains dict[str, Any] in a union."""
    if annotation is None:
        return False

    # Check direct dict
    if _is_dict_str_any(annotation):
        return True

    # Check union types (X | Y | Z)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _is_union_with_dict(annotation.left) or _is_union_with_dict(annotation.right)

    return False


def find_dict_patterns_in_file(file_path: Path) -> list[str]:
    """Find all dict[str, Any] patterns in a file.

    Returns list of qualified names like "path:Class.method:param"
    """
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        # Skip files that cannot be parsed (syntax errors or invalid encoding)
        return []

    patterns = []
    relative_path = str(file_path)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func_name = node.name
            class_name = None

            # Try to find enclosing class
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef):
                    for child in ast.walk(parent):
                        if child is node:
                            class_name = parent.name
                            break

            context = f"{class_name}.{func_name}" if class_name else func_name

            # Check parameters
            for arg in node.args.args + node.args.kwonlyargs:
                param_name = arg.arg
                annotation = arg.annotation

                if _is_dict_str_any(annotation) or _is_optional_dict(annotation) or _is_union_with_dict(annotation):
                    patterns.append(f"{relative_path}:{context}:{param_name}")
                elif _is_list_of_dict_str_any(annotation):
                    patterns.append(f"{relative_path}:{context}:{param_name} (list)")

            # Check return type
            if node.returns:
                if _is_dict_str_any(node.returns) or _is_optional_dict(node.returns) or _is_union_with_dict(node.returns):
                    patterns.append(f"{relative_path}:{context}:return")
                elif _is_list_of_dict_str_any(node.returns):
                    patterns.append(f"{relative_path}:{context}:return (list)")

    return patterns


def find_dict_violations(file_path: Path, whitelist: set[str], matched_entries: dict[str, bool]) -> list[DictViolation]:
    """Find dict[str, Any] type hints that should be typed contracts."""
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        # Skip files that cannot be parsed (syntax errors or invalid encoding)
        return []

    violations = []
    relative_path = str(file_path)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func_name = node.name
            class_name = None

            # Try to find enclosing class
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef):
                    for child in ast.walk(parent):
                        if child is node:
                            class_name = parent.name
                            break

            context = f"{class_name}.{func_name}" if class_name else func_name

            # Check parameters
            for arg in node.args.args + node.args.kwonlyargs:
                param_name = arg.arg
                annotation = arg.annotation

                if _is_dict_str_any(annotation) or _is_optional_dict(annotation) or _is_union_with_dict(annotation):
                    # Build qualified name for whitelist check
                    qualified = f"{relative_path}:{context}:{param_name}"
                    if qualified in whitelist:
                        matched_entries[qualified] = True
                    else:
                        violations.append(
                            DictViolation(
                                file=relative_path,
                                line=arg.lineno if hasattr(arg, "lineno") else node.lineno,
                                context=context,
                                param_name=param_name,
                            )
                        )
                elif _is_list_of_dict_str_any(annotation):
                    # List types have "(list)" suffix in whitelist
                    qualified = f"{relative_path}:{context}:{param_name} (list)"
                    if qualified in whitelist:
                        matched_entries[qualified] = True
                    else:
                        violations.append(
                            DictViolation(
                                file=relative_path,
                                line=arg.lineno if hasattr(arg, "lineno") else node.lineno,
                                context=context,
                                param_name=f"{param_name} (list)",
                            )
                        )

            # Check return type
            if node.returns:
                if _is_dict_str_any(node.returns) or _is_optional_dict(node.returns) or _is_union_with_dict(node.returns):
                    qualified = f"{relative_path}:{context}:return"
                    if qualified in whitelist:
                        matched_entries[qualified] = True
                    else:
                        violations.append(
                            DictViolation(
                                file=relative_path,
                                line=node.lineno,
                                context=context,
                                param_name="return",
                            )
                        )
                elif _is_list_of_dict_str_any(node.returns):
                    # List types have "(list)" suffix in whitelist
                    qualified = f"{relative_path}:{context}:return (list)"
                    if qualified in whitelist:
                        matched_entries[qualified] = True
                    else:
                        violations.append(
                            DictViolation(
                                file=relative_path,
                                line=node.lineno,
                                context=context,
                                param_name="return (list)",
                            )
                        )

    return violations


def get_top_level_module(file_path: Path, src_dir: Path) -> str:
    """Get the top-level module name for a file.

    For example:
        src/elspeth/tui/types.py -> tui
        src/elspeth/core/config.py -> core
    """
    relative = file_path.relative_to(src_dir)
    parts = relative.parts
    if len(parts) > 0:
        return parts[0]
    return ""


def is_cross_boundary_usage(defining_file: Path, using_file: Path, src_dir: Path) -> bool:
    """Check if usage crosses module boundaries.

    Cross-boundary means the using file is in a different top-level module
    than the defining file.
    """
    defining_module = get_top_level_module(defining_file, src_dir)
    using_module = get_top_level_module(using_file, src_dir)
    return defining_module != using_module


def find_cross_boundary_usages(src_dir: Path, type_name: str, defining_file: Path) -> list[Path]:
    """Find files that import a type from a DIFFERENT top-level module."""
    usages = []
    defining_module = defining_file.relative_to(src_dir).with_suffix("").as_posix().replace("/", ".")

    for py_file in src_dir.rglob("*.py"):
        if py_file == defining_file:
            continue

        # Only count as violation if crossing module boundary
        if not is_cross_boundary_usage(defining_file, py_file, src_dir):
            continue

        try:
            source = py_file.read_text()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and defining_module in node.module:
                for alias in node.names:
                    if alias.name == type_name:
                        usages.append(py_file)

    return usages


def validate_type_entry(entry: str, src_dir: Path) -> str | None:
    """Validate that an allowed_external_types entry exists.

    Entry format: "module/path:TypeName"

    Returns None if valid, or an error message if stale.
    """
    try:
        module_path, type_name = entry.rsplit(":", 1)
    except ValueError:
        return "Invalid format (expected 'path:TypeName')"

    # Convert module path to file path
    file_path = src_dir / f"{module_path}.py"

    if not file_path.exists():
        return f"File not found: {file_path}"

    # Check if type exists in file
    definitions = find_type_definitions(file_path)
    type_names = {name for name, _, _ in definitions}

    # Also check for regular class definitions (not just dataclass/TypedDict/etc)
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                type_names.add(node.name)
    except (SyntaxError, UnicodeDecodeError):
        # Skip files that cannot be parsed; rely on definitions from find_type_definitions
        pass

    if type_name not in type_names:
        return f"Type '{type_name}' not found in {file_path}"

    return None


def validate_dict_pattern_entry(entry: str, src_dir: Path) -> str | None:
    """Validate that an allowed_dict_patterns entry exists.

    Entry format: "src/elspeth/path/file.py:Class.method:param"

    Returns None if valid, or an error message if stale.
    """
    try:
        parts = entry.split(":")
        if len(parts) != 3:
            return f"Invalid format (expected 'file:context:param', got {len(parts)} parts)"

        file_path_str, context, param = parts
    except ValueError:
        return "Invalid format (expected 'file:context:param')"

    file_path = Path(file_path_str)

    if not file_path.exists():
        return f"File not found: {file_path}"

    # Find all dict patterns in the file
    patterns = find_dict_patterns_in_file(file_path)

    # Check if this entry matches any pattern
    if entry in patterns:
        return None

    # Check for partial matches to give better error messages
    matching_file_patterns = [p for p in patterns if p.startswith(file_path_str)]
    if not matching_file_patterns:
        return f"No dict[str, Any] patterns found in {file_path}"

    # Check if context exists
    matching_context_patterns = [p for p in matching_file_patterns if f":{context}:" in p]
    if not matching_context_patterns:
        return f"Context '{context}' not found in {file_path}"

    # Parameter doesn't match
    available_params = [p.split(":")[-1] for p in matching_context_patterns]
    return f"Parameter '{param}' not found in {context}. Available: {available_params}"


def find_stale_entries(
    entries: list[WhitelistEntry],
    matched_dict_patterns: dict[str, bool],
    matched_type_patterns: set[str],
    src_dir: Path,
) -> list[StaleEntry]:
    """Find whitelist entries that don't match any code."""
    stale = []

    for entry in entries:
        if entry.category == "type":
            # Check if this type entry is valid
            if entry.value in matched_type_patterns:
                continue
            error = validate_type_entry(entry.value, src_dir)
            if error:
                stale.append(StaleEntry(entry=entry.value, category="type", reason=error))

        elif entry.category == "dict_pattern":
            # Check if this pattern was matched during scanning
            if matched_dict_patterns.get(entry.value, False):
                continue
            # Validate the entry
            error = validate_dict_pattern_entry(entry.value, src_dir)
            if error:
                stale.append(StaleEntry(entry=entry.value, category="dict_pattern", reason=error))

    return stale


def main() -> int:
    """Run the contracts enforcement check."""
    parser = argparse.ArgumentParser(description="Check that cross-boundary types are in contracts/ and whitelist entries are valid")
    parser.add_argument(
        "--no-fail-on-stale",
        action="store_true",
        help="Don't fail on stale whitelist entries (just warn)",
    )
    args = parser.parse_args()

    src_dir = Path("src/elspeth")
    contracts_dir = src_dir / "contracts"
    whitelist_path = Path("config/cicd/contracts-whitelist.yaml")

    whitelist, all_entries = load_whitelist(whitelist_path)
    violations: list[Violation] = []
    dict_violations: list[DictViolation] = []
    matched_dict_patterns: dict[str, bool] = dict.fromkeys(whitelist["dicts"], False)
    matched_type_patterns: set[str] = set()

    # Scan all Python files outside contracts/
    for py_file in src_dir.rglob("*.py"):
        if contracts_dir in py_file.parents or py_file.parent == contracts_dir:
            continue  # Skip contracts/ itself

        # Check for type definitions
        definitions = find_type_definitions(py_file)
        for type_name, line_no, kind in definitions:
            qualified_name = f"{py_file.relative_to(src_dir).with_suffix('')}:{type_name}"

            if qualified_name in whitelist["types"]:
                matched_type_patterns.add(qualified_name)
                continue

            # Check if used across module boundaries
            usages = find_cross_boundary_usages(src_dir, type_name, py_file)
            if usages:
                violations.append(
                    Violation(
                        file=str(py_file),
                        line=line_no,
                        type_name=type_name,
                        kind=kind,
                        used_in=[str(u) for u in usages[:3]],  # First 3
                    )
                )

        # Check for dict[str, Any] patterns
        dict_violations.extend(find_dict_violations(py_file, whitelist["dicts"], matched_dict_patterns))

    # Find stale whitelist entries
    stale_entries = find_stale_entries(all_entries, matched_dict_patterns, matched_type_patterns, src_dir)

    has_violations = False
    has_stale = False

    if violations:
        has_violations = True
        print("❌ Type definition violations found:\n")
        for v in violations:
            print(f"  {v.file}:{v.line}: {v.kind} '{v.type_name}'")
            print(f"    Used in: {', '.join(v.used_in)}")
            fix_msg = "    Fix: Move to src/elspeth/contracts/ or add to config/cicd/contracts-whitelist.yaml\n"
            print(fix_msg)

    if dict_violations:
        has_violations = True
        print("❌ dict[str, Any] violations found:\n")
        for dv in dict_violations:
            print(f"  {dv.file}:{dv.line}: {dv.context} - {dv.param_name}")
            print("    Fix: Use TypedDict/dataclass or add to allowed_dict_patterns\n")

    if stale_entries:
        has_stale = True
        print("❌ Stale whitelist entries found:\n")
        print("  (These entries don't match any code - remove them from the whitelist)\n")
        for se in stale_entries:
            print(f"  [{se.category}] {se.entry}")
            print(f"    Reason: {se.reason}\n")

    if has_violations:
        return 1

    if has_stale:
        if args.no_fail_on_stale:
            print("⚠️  Stale entries found but --no-fail-on-stale was specified")
        else:
            print("❌ Stale whitelist entries cause check failure")
            print("   Use --no-fail-on-stale to warn instead of fail")
            return 1

    print("✅ All cross-boundary types are properly centralized in contracts/")
    if not stale_entries:
        print("✅ All whitelist entries are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
