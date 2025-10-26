#!/usr/bin/env python3
"""Auto-generate plugin documentation from source code.

Scans src/elspeth/plugins/ for plugin classes and generates:
1. Plugin catalogue (user-guide style) in site-docs/docs/plugins/generated-catalogue.md
2. API reference docs in site-docs/docs/api-reference/plugins/generated-*.md

This script extracts metadata including security-critical parameters like
allow_downgrade to provide complete plugin documentation.

Run this script before building docs (make docs-build) or via CI on every merge.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParameterMetadata:
    """Metadata for a single __init__ parameter."""

    name: str
    type_hint: str | None = None
    default: str | None = None  # String representation of default value
    required: bool = True


@dataclass
class PluginMetadata:
    """Extracted plugin metadata."""

    name: str  # "CSVLocalDatasource"
    type: str  # "datasource" | "transform" | "sink" | "middleware" | "experiment"
    module_path: str  # "elspeth.plugins.nodes.sources.csv_local"
    class_name: str  # "CSVLocalDatasource"
    docstring: str  # Extracted from class
    summary: str  # First line of docstring
    parameters: list[ParameterMetadata] = field(default_factory=list)
    config_type: str = ""  # "csv_local" (inferred from filename)

    # Security metadata
    security_level_default: str | None = None  # Default security level
    allow_downgrade_default: bool | None = None  # True = trusted downgrade, False = frozen

    # File location
    source_file: str = ""  # Relative path for reference


class PluginExtractor(ast.NodeVisitor):
    """AST visitor that extracts plugin metadata from Python source."""

    def __init__(self, filepath: Path, plugin_type: str, module_path: str):
        self.filepath = filepath
        self.plugin_type = plugin_type
        self.module_path = module_path
        self.plugins: list[PluginMetadata] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition and extract if it's a BasePlugin subclass."""
        # Check if inherits from BasePlugin
        inherits_baseplugin = any(
            "BasePlugin" in ast.unparse(base) for base in node.bases
        )

        if not inherits_baseplugin:
            self.generic_visit(node)
            return

        # Extract docstring
        docstring = ast.get_docstring(node) or "No description available."
        summary = docstring.split("\n\n")[0].split("\n")[0]  # First paragraph, first line

        # Find __init__ method
        init_method = None
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                init_method = item
                break

        parameters = []
        security_level_default = None
        allow_downgrade_default = None

        if init_method:
            # First, scan __init__ body for super().__init__() calls to extract allow_downgrade
            for stmt in ast.walk(init_method):
                if isinstance(stmt, ast.Call):
                    # Check if this is super().__init__() or super().__init__(...)
                    if isinstance(stmt.func, ast.Attribute) and stmt.func.attr == "__init__":
                        # Check if called on super()
                        if isinstance(stmt.func.value, ast.Call):
                            # Check if the inner call is super()
                            inner_func = stmt.func.value.func
                            if isinstance(inner_func, ast.Name) and inner_func.id == "super":
                                # Extract keyword arguments from super().__init__(...)
                                for keyword in stmt.keywords:
                                    if keyword.arg == "allow_downgrade":
                                        value_str = ast.unparse(keyword.value).lower()
                                        if value_str == "true":
                                            allow_downgrade_default = True
                                        elif value_str == "false":
                                            allow_downgrade_default = False
                                    elif keyword.arg == "security_level" and security_level_default is None:
                                        security_level_default = ast.unparse(keyword.value)

            # Extract parameters from __init__
            for arg in init_method.args.args:
                if arg.arg == "self":
                    continue

                param = ParameterMetadata(name=arg.arg)

                # Extract type hint
                if arg.annotation:
                    param.type_hint = ast.unparse(arg.annotation)

                # Extract default value
                defaults = init_method.args.defaults
                kwonlyargs = init_method.args.kwonlyargs
                kw_defaults = init_method.args.kw_defaults

                # Check keyword-only args (common for BasePlugin)
                if arg.arg in [kwa.arg for kwa in kwonlyargs]:
                    idx = [kwa.arg for kwa in kwonlyargs].index(arg.arg)
                    if idx < len(kw_defaults) and kw_defaults[idx] is not None:
                        param.default = ast.unparse(kw_defaults[idx])
                        param.required = False
                    else:
                        param.required = True
                else:
                    # Check positional args with defaults
                    total_args = len(init_method.args.args) - 1  # Exclude self
                    default_offset = total_args - len(defaults)
                    arg_idx = init_method.args.args.index(arg) - 1  # Exclude self

                    if arg_idx >= default_offset:
                        default_idx = arg_idx - default_offset
                        param.default = ast.unparse(defaults[default_idx])
                        param.required = False

                parameters.append(param)

                # Capture security-critical parameters
                if arg.arg == "security_level" and param.default:
                    security_level_default = param.default
                elif arg.arg == "allow_downgrade" and param.default:
                    # Parse boolean default
                    default_str = param.default.lower()
                    if default_str == "true":
                        allow_downgrade_default = True
                    elif default_str == "false":
                        allow_downgrade_default = False

        # Infer config type from filename
        config_type = self.filepath.stem  # e.g., "csv_local.py" -> "csv_local"

        # Compute relative path safely (works from worktree or main repo)
        try:
            rel_path = str(self.filepath.relative_to(Path.cwd()))
        except ValueError:
            # File not in current working directory (e.g., running from worktree)
            # Use absolute path or try to compute relative from common ancestor
            parts = self.filepath.parts
            if "src" in parts:
                idx = parts.index("src")
                rel_path = str(Path(*parts[idx:]))
            else:
                rel_path = str(self.filepath)

        metadata = PluginMetadata(
            name=node.name,
            type=self.plugin_type,
            module_path=self.module_path,
            class_name=node.name,
            docstring=docstring,
            summary=summary,
            parameters=parameters,
            config_type=config_type,
            security_level_default=security_level_default,
            allow_downgrade_default=allow_downgrade_default,
            source_file=rel_path,
        )

        self.plugins.append(metadata)
        self.generic_visit(node)


def discover_plugins(base_path: Path) -> list[PluginMetadata]:
    """Scan filesystem and extract all plugin metadata.

    Args:
        base_path: Root path to elspeth/plugins directory

    Returns:
        List of plugin metadata objects
    """
    plugins = []

    # Define plugin type mappings (directory -> type)
    plugin_dirs = [
        ("nodes/sources", "datasource"),
        ("nodes/sinks", "sink"),
        ("nodes/transforms/llm", "transform"),
        ("nodes/transforms/llm/middleware", "middleware"),
        ("experiments/row", "row_experiment"),
        ("experiments/aggregators", "aggregator"),
        ("experiments/baseline", "baseline"),
        ("experiments/validation", "validation"),
        ("experiments/early_stop", "early_stop"),
    ]

    for subdir, plugin_type in plugin_dirs:
        dir_path = base_path / subdir
        if not dir_path.exists():
            continue

        for file in dir_path.glob("*.py"):
            if file.name.startswith("_"):  # Skip __init__.py, _base.py, etc.
                continue

            plugins.extend(extract_plugins_from_file(file, plugin_type))

    return plugins


def extract_plugins_from_file(filepath: Path, plugin_type: str) -> list[PluginMetadata]:
    """Parse Python file with AST and extract plugin classes.

    Args:
        filepath: Path to Python source file
        plugin_type: Type of plugin expected in this file

    Returns:
        List of extracted plugin metadata
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(filepath))

        # Construct module path
        # e.g., src/elspeth/plugins/nodes/sources/csv_local.py -> elspeth.plugins.nodes.sources.csv_local
        parts = filepath.parts
        if "src" in parts:
            src_idx = parts.index("src")
            module_parts = parts[src_idx + 1 :]
            module_path = ".".join(module_parts).replace(".py", "")
        else:
            # Fallback if not in src/
            module_path = f"elspeth.plugins.{filepath.stem}"

        extractor = PluginExtractor(filepath, plugin_type, module_path)
        extractor.visit(tree)

        return extractor.plugins

    except Exception as e:
        print(f"⚠️  Warning: Failed to parse {filepath}: {e}", file=sys.stderr)
        return []


def generate_security_badge(metadata: PluginMetadata) -> str:
    """Generate security capability badge for plugin.

    Args:
        metadata: Plugin metadata

    Returns:
        Markdown badge string
    """
    if metadata.allow_downgrade_default is None:
        return "❓ Unknown"  # No explicit allow_downgrade found
    elif metadata.allow_downgrade_default is True:
        return "✅ Trusted Downgrade"  # Can operate at lower levels
    else:
        return "🔒 Frozen"  # Cannot downgrade, exact level only


def generate_user_catalogue(plugins: list[PluginMetadata]) -> str:
    """Generate user-guide style catalogue with decision trees.

    Args:
        plugins: List of plugin metadata

    Returns:
        Markdown content for catalogue
    """
    md = [
        "# Plugin Catalogue (Auto-Generated)",
        "",
        "!!! warning \"Auto-Generated Documentation\"",
        "    This file is automatically generated from source code. Do not edit manually.",
        "    ",
        "    **Generated from**: `scripts/generate_plugin_docs.py`  ",
        "    **Last generated**: Run `make docs-generate` to update",
        "",
        "---",
        "",
    ]

    # Group by type
    datasources = [p for p in plugins if p.type == "datasource"]
    transforms = [p for p in plugins if p.type == "transform"]
    middlewares = [p for p in plugins if p.type == "middleware"]
    sinks = [p for p in plugins if p.type == "sink"]
    row_experiments = [p for p in plugins if p.type == "row_experiment"]
    aggregators = [p for p in plugins if p.type == "aggregator"]
    baselines = [p for p in plugins if p.type == "baseline"]
    validations = [p for p in plugins if p.type == "validation"]
    early_stops = [p for p in plugins if p.type == "early_stop"]

    # Datasources section
    if datasources:
        md.extend([
            "## Loading Data (Datasources)",
            "",
            f"**{len(datasources)} datasource plugins** available for loading data into experiments.",
            "",
            "| Plugin | Description | Security | Key Parameters |",
            "|--------|-------------|----------|----------------|",
        ])

        for p in sorted(datasources, key=lambda x: x.config_type):
            params = ", ".join(
                f"`{pm.name}`" for pm in p.parameters if pm.required and pm.name not in ("security_level", "allow_downgrade")
            )[:50]  # Truncate long parameter lists
            if len(params) == 50:
                params += "..."

            security_badge = generate_security_badge(p)
            md.append(f"| **`{p.config_type}`** | {p.summary} | {security_badge} | {params or 'None'} |")

        md.extend(["", "---", ""])

    # Transforms section
    if transforms:
        md.extend([
            "## Processing with LLMs (Transforms)",
            "",
            f"**{len(transforms)} transform plugins** available for processing data.",
            "",
            "| Plugin | Description | Security | Key Parameters |",
            "|--------|-------------|----------|----------------|",
        ])

        for p in sorted(transforms, key=lambda x: x.config_type):
            params = ", ".join(
                f"`{pm.name}`" for pm in p.parameters if pm.required and pm.name not in ("security_level", "allow_downgrade")
            )[:50]
            if len(params) == 50:
                params += "..."

            security_badge = generate_security_badge(p)
            md.append(f"| **`{p.config_type}`** | {p.summary} | {security_badge} | {params or 'None'} |")

        md.extend(["", "---", ""])

    # Middleware section
    if middlewares:
        md.extend([
            "## LLM Middleware",
            "",
            f"**{len(middlewares)} middleware plugins** for request/response processing.",
            "",
            "| Plugin | Description | Security |",
            "|--------|-------------|----------|",
        ])

        for p in sorted(middlewares, key=lambda x: x.config_type):
            security_badge = generate_security_badge(p)
            md.append(f"| **`{p.config_type}`** | {p.summary} | {security_badge} |")

        md.extend(["", "---", ""])

    # Sinks section
    if sinks:
        md.extend([
            "## Saving Results (Sinks)",
            "",
            f"**{len(sinks)} sink plugins** available for writing experiment outputs.",
            "",
            "| Plugin | Description | Security | Key Parameters |",
            "|--------|-------------|----------|----------------|",
        ])

        for p in sorted(sinks, key=lambda x: x.config_type):
            params = ", ".join(
                f"`{pm.name}`" for pm in p.parameters if pm.required and pm.name not in ("security_level", "allow_downgrade")
            )[:50]
            if len(params) == 50:
                params += "..."

            security_badge = generate_security_badge(p)
            md.append(f"| **`{p.config_type}`** | {p.summary} | {security_badge} | {params or 'None'} |")

        md.extend(["", "---", ""])

    # Experiment helpers
    experiment_sections = [
        ("Row Plugins", row_experiments),
        ("Aggregators", aggregators),
        ("Baseline Comparison", baselines),
        ("Validation Plugins", validations),
        ("Early Stop Plugins", early_stops),
    ]

    for section_name, section_plugins in experiment_sections:
        if not section_plugins:
            continue

        md.extend([
            f"## {section_name}",
            "",
            f"**{len(section_plugins)} {section_name.lower()}** available.",
            "",
            "| Plugin | Description | Security |",
            "|--------|-------------|----------|",
        ])

        for p in sorted(section_plugins, key=lambda x: x.config_type):
            security_badge = generate_security_badge(p)
            md.append(f"| **`{p.config_type}`** | {p.summary} | {security_badge} |")

        md.extend(["", "---", ""])

    # Security legend
    md.extend([
        "## Security Capability Legend",
        "",
        "| Badge | Meaning | Description |",
        "|-------|---------|-------------|",
        "| ✅ Trusted Downgrade | `allow_downgrade=True` | Plugin can operate at lower security levels (trusted to filter appropriately) |",
        "| 🔒 Frozen | `allow_downgrade=False` | Plugin requires exact security level matching (dedicated classification domains) |",
        "| ❓ Unknown | Not specified | Security behavior not explicitly declared in source |",
        "",
        "See [Security Policy](../architecture/security-policy.md#policy-4-frozen-plugin-capability) for details on trusted downgrade vs frozen plugins.",
        "",
    ])

    return "\n".join(md)


def generate_api_reference(plugins: list[PluginMetadata], plugin_type: str, type_label: str) -> str:
    """Generate API reference with mkdocstrings directives.

    Args:
        plugins: All plugin metadata
        plugin_type: Plugin type to filter by
        type_label: Human-readable label (e.g., "Datasources")

    Returns:
        Markdown content for API reference
    """
    filtered = [p for p in plugins if p.type == plugin_type]

    if not filtered:
        return ""  # No plugins of this type

    md = [
        f"# {type_label} API (Auto-Generated)",
        "",
        "!!! warning \"Auto-Generated Documentation\"",
        "    This file is automatically generated from source code. Do not edit manually.",
        "    ",
        "    **Generated from**: `scripts/generate_plugin_docs.py`  ",
        "    **Last generated**: Run `make docs-generate` to update",
        "",
        f"API documentation for **{len(filtered)} {type_label.lower()}** that {_get_purpose(plugin_type)}.",
        "",
        "---",
        "",
    ]

    for p in sorted(filtered, key=lambda x: x.config_type):
        md.extend([
            f"## {p.name}",
            "",
            f"**Configuration Type**: `{p.config_type}`  ",
            f"**Security**: {generate_security_badge(p)}  ",
            f"**Source**: `{p.source_file}`",
            "",
        ])

        # mkdocstrings directive
        md.extend([
            f"::: {p.module_path}.{p.class_name}",
            "    options:",
            "      members:",
            "        - __init__",
        ])

        # Add plugin-specific methods
        if plugin_type == "datasource":
            md.append("        - load_data")
        elif plugin_type == "transform":
            md.append("        - transform")
        elif plugin_type == "sink":
            md.append("        - write")

        md.extend([
            "      show_root_heading: true",
            "      show_root_full_path: false",
            "      heading_level: 3",
            "",
        ])

        # Example YAML configuration
        md.extend([
            "**Example Configuration**:",
            "```yaml",
        ])

        if plugin_type == "datasource":
            md.append("datasource:")
        elif plugin_type == "transform":
            md.append("transform:")
        elif plugin_type == "sink":
            md.append("sinks:")
            md.append("  - type: " + p.config_type)
        else:
            md.append("plugin:")

        if plugin_type != "sink":
            md.append(f"  type: {p.config_type}")

        # Add required parameters
        for param in p.parameters:
            if param.required and param.name not in ("self", "kwargs"):
                example_value = _get_example_value(param)
                md.append(f"  {param.name}: {example_value}")

        # Add security parameters if not already present
        if not any(p.name == "security_level" for p in p.parameters):
            md.append("  security_level: OFFICIAL")
        if p.allow_downgrade_default is not None and not any(p.name == "allow_downgrade" for p in p.parameters):
            md.append(f"  allow_downgrade: {str(p.allow_downgrade_default).lower()}")

        md.extend([
            "```",
            "",
            "---",
            "",
        ])

    return "\n".join(md)


def _get_purpose(plugin_type: str) -> str:
    """Get purpose description for plugin type."""
    purposes = {
        "datasource": "load data into experiments",
        "transform": "process and transform data",
        "sink": "write experiment outputs",
        "middleware": "intercept and modify LLM requests/responses",
        "row_experiment": "process individual rows during experiments",
        "aggregator": "aggregate results after experiments",
        "baseline": "compare experiments against baselines",
        "validation": "validate experiment configurations",
        "early_stop": "stop experiments based on criteria",
    }
    return purposes.get(plugin_type, "perform plugin-specific tasks")


def _get_example_value(param: ParameterMetadata) -> str:
    """Generate example value for parameter based on type hint and name."""
    name = param.name.lower()
    type_hint = param.type_hint or ""

    # String parameters
    if "str" in type_hint or name in ("path", "name", "endpoint", "api_key", "content"):
        if "path" in name:
            return "data/example.csv"
        elif "endpoint" in name:
            return "https://api.example.com"
        elif "key" in name:
            return "${API_KEY}"
        else:
            return "example_value"

    # Boolean parameters
    if "bool" in type_hint or name in ("overwrite", "sanitize", "enabled"):
        return "true"

    # Integer parameters
    if "int" in type_hint or name in ("port", "timeout", "retries"):
        return "100"

    # Float parameters
    if "float" in type_hint or name in ("temperature", "score", "threshold"):
        return "0.7"

    # Dict parameters
    if "dict" in type_hint or "Mapping" in type_hint:
        return "{}"

    # List parameters
    if "list" in type_hint or "List" in type_hint:
        return "[]"

    # SecurityLevel
    if "SecurityLevel" in type_hint:
        return "OFFICIAL"

    # Default
    return "value"


def main():
    """Main entry point for plugin documentation generation."""
    print("🔍 Discovering plugins...")

    # Find base path (assuming script runs from repo root or site-docs/)
    repo_root = Path.cwd()
    if repo_root.name == "site-docs":
        repo_root = repo_root.parent

    plugins_path = repo_root / "src" / "elspeth" / "plugins"
    if not plugins_path.exists():
        print(f"❌ Error: Plugins directory not found at {plugins_path}", file=sys.stderr)
        print(f"   Current directory: {Path.cwd()}", file=sys.stderr)
        print(f"   Expected structure: src/elspeth/plugins/", file=sys.stderr)
        sys.exit(1)

    # Discover all plugins
    plugins = discover_plugins(plugins_path)

    if not plugins:
        print("⚠️  Warning: No plugins discovered!", file=sys.stderr)
        sys.exit(1)

    print(f"✅ Discovered {len(plugins)} plugins:")
    for plugin_type in set(p.type for p in plugins):
        count = sum(1 for p in plugins if p.type == plugin_type)
        print(f"   - {plugin_type}: {count}")

    # Generate user catalogue
    print("\n📝 Generating user catalogue...")
    catalogue = generate_user_catalogue(plugins)
    catalogue_path = repo_root / "site-docs" / "docs" / "plugins" / "generated-catalogue.md"
    catalogue_path.parent.mkdir(parents=True, exist_ok=True)
    catalogue_path.write_text(catalogue, encoding="utf-8")
    print(f"   ✅ Written to {catalogue_path.relative_to(repo_root)}")

    # Generate API reference pages
    print("\n📚 Generating API reference pages...")
    api_specs = [
        ("datasource", "Datasources"),
        ("transform", "Transforms"),
        ("middleware", "Middleware"),
        ("sink", "Sinks"),
        ("row_experiment", "Row Experiment Plugins"),
        ("aggregator", "Aggregator Plugins"),
        ("baseline", "Baseline Plugins"),
        ("validation", "Validation Plugins"),
        ("early_stop", "Early Stop Plugins"),
    ]

    for plugin_type, type_label in api_specs:
        api_ref = generate_api_reference(plugins, plugin_type, type_label)
        if api_ref:  # Only write if plugins of this type exist
            filename = f"generated-{plugin_type.replace('_', '-')}s.md"
            api_path = repo_root / "site-docs" / "docs" / "api-reference" / "plugins" / filename
            api_path.parent.mkdir(parents=True, exist_ok=True)
            api_path.write_text(api_ref, encoding="utf-8")
            print(f"   ✅ {type_label}: {api_path.relative_to(repo_root)}")

    print("\n🎉 Plugin documentation generation complete!")
    print(f"\n💡 Tip: Run 'make docs-serve' to preview the generated documentation")


if __name__ == "__main__":
    main()