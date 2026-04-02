"""Skill packs for the LLM pipeline composer.

Skill packs are markdown files loaded into the system prompt to teach
the LLM how to use the composition tools effectively.
"""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent


def load_skill(name: str) -> str:
    """Load a skill pack by name (without extension).

    Args:
        name: Skill filename without .md extension (e.g. 'pipeline_composer').

    Returns:
        The skill content as a string.

    Raises:
        FileNotFoundError: If the skill file does not exist.
    """
    path = _SKILLS_DIR / f"{name}.md"
    return path.read_text()
