"""PromptShieldMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMMiddleware, LLMRequest
from elspeth.core.base.types import SecurityLevel
from elspeth.core.registries.middleware import register_middleware

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


class PromptShieldMiddleware(BasePlugin, LLMMiddleware):
    """Basic middleware that masks or blocks unsafe prompts before sending to the LLM.

    Args:
        security_level: Security clearance for this middleware (MANDATORY per ADR-004).
        denied_terms: List of terms to detect and block/mask.
        mask: Replacement text for masked terms (default: '[REDACTED]').
        on_violation: Action to take ('abort', 'mask', or 'log', default: 'abort').
        channel: Logger channel name (default: 'elspeth.prompt_shield').
    """

    name = "prompt_shield"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        denied_terms: Sequence[str] | None = None,
        mask: str = "[REDACTED]",
        on_violation: str = "abort",
        channel: str | None = None,
    ):
        super().__init__(security_level=security_level, allow_downgrade=True)  # ADR-005: Middleware trusted to downgrade
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


def _create_prompt_shield_middleware(options: dict[str, Any], context: PluginContext) -> PromptShieldMiddleware:
    """Factory for prompt shield middleware with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    return PromptShieldMiddleware(
        security_level=opts["security_level"],
        denied_terms=opts.get("denied_terms", []),
        mask=opts.get("mask", "[REDACTED]"),
        on_violation=opts.get("on_violation", "abort"),
        channel=opts.get("channel"),
    )


register_middleware(
    "prompt_shield",
    _create_prompt_shield_middleware,
    schema=_PROMPT_SHIELD_SCHEMA,
)


__all__ = ["PromptShieldMiddleware"]
