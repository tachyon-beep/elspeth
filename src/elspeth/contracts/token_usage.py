"""Token usage contract for LLM responses.

Replaces loose ``dict[str, int]`` with a frozen dataclass that encodes
``None = unknown`` at the type level.  This eliminates an entire class
of fabrication bugs where ``.get("prompt_tokens", 0)`` silently converts
"provider didn't report" into "zero tokens used."

Trust-tier notes
----------------
* ``known()`` / ``unknown()`` — used by our code (Tier 1/2).
* ``from_dict()`` — the **only** Tier 3 reconstruction path.
  Coerces non-int values to ``None`` so callers never need to
  ``isinstance``-check individual fields again.
* ``to_dict()`` — serialization boundary.  Omits ``None`` keys so
  downstream row storage (still plain dicts) is backward-compatible:
  ``{}`` for fully unknown, ``{"prompt_tokens": 10}`` for partial.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """LLM token usage with explicit unknown semantics.

    Attributes:
        prompt_tokens: Tokens consumed by the prompt, or ``None``
            if the provider did not report this.
        completion_tokens: Tokens generated in the response, or ``None``
            if the provider did not report this.
    """

    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def __post_init__(self) -> None:
        """Validate token counts are non-negative when known.

        Negative token counts are physically impossible and indicate
        either an API bug or data corruption. Zero is acceptable
        (e.g., cached responses with 0 completion tokens).
        """
        if self.prompt_tokens is not None and self.prompt_tokens < 0:
            raise ValueError(f"prompt_tokens must be non-negative, got {self.prompt_tokens}")
        if self.completion_tokens is not None and self.completion_tokens < 0:
            raise ValueError(f"completion_tokens must be non-negative, got {self.completion_tokens}")

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def total_tokens(self) -> int | None:
        """Sum of prompt + completion, or ``None`` if either is unknown."""
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens

    @property
    def is_known(self) -> bool:
        """``True`` when both token counts were reported by the provider."""
        return self.prompt_tokens is not None and self.completion_tokens is not None

    @property
    def has_data(self) -> bool:
        """``True`` when at least one token count was reported.

        Unlike ``is_known`` (which requires *both* counters), this returns
        ``True`` for partial provider responses that include only one counter.
        Use this when deciding whether to emit usage to telemetry — partial
        data is still valuable operational signal.
        """
        return self.prompt_tokens is not None or self.completion_tokens is not None

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, int]:
        """Convert to a plain dict, omitting unknown (``None``) fields.

        Returns ``{}`` for fully unknown, ``{"prompt_tokens": 10}`` for
        partial, or the full dict when both fields are known.
        """
        result: dict[str, int] = {}
        if self.prompt_tokens is not None:
            result["prompt_tokens"] = self.prompt_tokens
        if self.completion_tokens is not None:
            result["completion_tokens"] = self.completion_tokens
        return result

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def unknown(cls) -> TokenUsage:
        """Factory for fully-unknown usage (provider omitted data)."""
        return cls(prompt_tokens=None, completion_tokens=None)

    @classmethod
    def known(cls, prompt_tokens: int, completion_tokens: int) -> TokenUsage:
        """Factory for fully-known usage.

        Args:
            prompt_tokens: Number of prompt tokens consumed.
            completion_tokens: Number of completion tokens generated.
        """
        return cls(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    @classmethod
    def from_dict(cls, data: Any) -> TokenUsage:
        """Reconstruct from external (Tier 3) data.

        Coerces non-``int`` values to ``None`` so callers never need to
        validate individual fields.  Handles:
        - Missing keys  → ``None``
        - ``None`` values → ``None``
        - Non-int types (``float``, ``str``, …) → ``None``
        - Empty / non-dict input → fully unknown

        Args:
            data: Raw dict from an LLM API response, or ``None``/non-dict.
        """
        from collections.abc import Mapping

        if not isinstance(data, Mapping):
            return cls.unknown()

        raw_prompt = data.get("prompt_tokens")
        raw_completion = data.get("completion_tokens")

        # bool is a subclass of int in Python, so isinstance(True, int) is True.
        # But True/False are not valid token counts — reject them as non-int.
        prompt = raw_prompt if isinstance(raw_prompt, int) and not isinstance(raw_prompt, bool) else None
        completion = raw_completion if isinstance(raw_completion, int) and not isinstance(raw_completion, bool) else None

        return cls(prompt_tokens=prompt, completion_tokens=completion)
