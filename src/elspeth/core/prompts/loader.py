"""Helpers for loading prompt templates from disk."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .engine import PromptEngine
from .template import PromptTemplate


def load_template(
    path: str | Path,
    *,
    engine: PromptEngine | None = None,
    name: str | None = None,
    defaults: Mapping[str, object] | None = None,
) -> PromptTemplate:
    """Load and compile a prompt template from disk."""

    engine = engine or PromptEngine()
    text = Path(path).read_text(encoding="utf-8")
    return engine.compile(text, name=name or Path(path).stem, defaults=defaults)


def load_template_pair(
    system_path: str | Path,
    user_path: str | Path,
    *,
    engine: PromptEngine | None = None,
    defaults: Mapping[str, object] | None = None,
) -> tuple[PromptTemplate, PromptTemplate]:
    """Load system and user prompt templates as a pair."""

    engine = engine or PromptEngine()
    system = load_template(system_path, engine=engine, name="system_prompt", defaults=defaults)
    user = load_template(user_path, engine=engine, name="user_prompt", defaults=defaults)
    return system, user
