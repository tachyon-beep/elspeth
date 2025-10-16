"""PromptShieldMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
from typing import Sequence

from elspeth.core.llm_middleware_registry import register_middleware
from elspeth.core.protocols import LLMMiddleware, LLMRequest

logger = logging.getLogger(__name__)

_PROMPT_SHIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "denied_terms": {"type": "array", "items": {"type": "string"}},
        "mask": {"type": "string"},
        "on_violation": {"type": "string", "enum": ["abort", "mask", "log"]},
        "channel": {"type": "string"},
    },
    "additionalProperties": True,
}


class PromptShieldMiddleware(LLMMiddleware):
    name = "prompt_shield"

    def __init__(
        self,
        *,
        denied_terms: Sequence[str] | None = None,
        mask: str = "[REDACTED]",
        on_violation: str = "abort",
        channel: str | None = None,
    ):
        self.denied_terms = [term.lower() for term in denied_terms or []]
        self.mask = mask
        mode = (on_violation or "abort").lower()
        if mode not in {"abort", "mask", "log"}:
            mode = "abort"
        self.mode = mode
        self.channel = channel or "elspeth.prompt_shield"

    def before_request(self, request: LLMRequest) -> LLMRequest:
        lowered = request.user_prompt.lower()
        for term in self.denied_terms:
            if term and term in lowered:
                logger.warning("[%s] Prompt contains blocked term '%s'", self.channel, term)
                if self.mode == "abort":
                    raise ValueError(f"Prompt contains blocked term '{term}'")
                if self.mode == "mask":
                    masked = request.user_prompt.replace(term, self.mask)
                    return request.clone(user_prompt=masked)
                break
        return request


register_middleware(
    "prompt_shield",
    lambda options, context: PromptShieldMiddleware(
        denied_terms=options.get("denied_terms", []),
        mask=options.get("mask", "[REDACTED]"),
        on_violation=options.get("on_violation", "abort"),
        channel=options.get("channel"),
    ),
    schema=_PROMPT_SHIELD_SCHEMA,
)


__all__ = ["PromptShieldMiddleware"]
