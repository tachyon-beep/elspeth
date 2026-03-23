"""Shared Jinja2 template infrastructure for transform plugins.

Provides a sandboxed Jinja2 environment factory and the TemplateError exception.
Used by both LLM prompt templates and RAG query templates.

The sandbox prevents attribute access, method calls, and module imports.
It does NOT limit CPU or memory consumption from template loops — templates
are authored by pipeline architects (trusted config), not end users.
"""

from __future__ import annotations

from jinja2 import StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment


class TemplateError(Exception):
    """Error in template rendering (including sandbox violations)."""


def create_sandboxed_environment() -> ImmutableSandboxedEnvironment:
    """Create an ImmutableSandboxedEnvironment with StrictUndefined.

    Returns:
        A sandboxed Jinja2 environment that:
        - Raises on undefined variables (StrictUndefined)
        - Blocks attribute access and method calls (ImmutableSandboxedEnvironment)
        - Does not HTML-escape output (autoescape=False)
    """
    return ImmutableSandboxedEnvironment(
        undefined=StrictUndefined,
        autoescape=False,
    )
