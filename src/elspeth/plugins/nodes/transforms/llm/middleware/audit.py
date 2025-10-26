"""AuditMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
from typing import Any

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMMiddleware, LLMRequest
from elspeth.core.base.types import SecurityLevel
from elspeth.core.registries.middleware import register_middleware

logger = logging.getLogger(__name__)

_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "include_prompts": {"type": "boolean"},
        "channel": {"type": "string"},
    },
    "additionalProperties": True,
}


class AuditMiddleware(BasePlugin, LLMMiddleware):
    """Structured audit logger for LLM requests and responses.

    Args:
        include_prompts: Whether to include full prompts in audit logs (default: False).
        channel: Logger channel name (default: 'elspeth.audit').

    - Emits request metadata (and optionally prompts) before dispatch.
    - Emits response metrics (and optionally content) after completion.
    - Channel name is configurable via options or defaults to 'elspeth.audit'.
    """

    name = "audit_logger"

    def __init__(
        self,
        *,
        include_prompts: bool = False,
        channel: str | None = None,
    ):
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True,  # ADR-002-B: Immutable policy
        )
        self.include_prompts = include_prompts
        self.channel = channel or "elspeth.audit"

    def before_request(self, request: LLMRequest) -> LLMRequest:
        payload: dict[str, Any] = {"metadata": request.metadata}
        if self.include_prompts:
            payload.update({"system": request.system_prompt, "user": request.user_prompt})
        logger.info("[%s] LLM request metadata=%s", self.channel, payload)
        return request

    def after_response(self, request: LLMRequest, response: dict[str, Any]) -> dict[str, Any]:
        logger.info("[%s] LLM response metrics=%s", self.channel, response.get("metrics"))
        if self.include_prompts:
            logger.debug("[%s] LLM response content=%s", self.channel, response.get("content"))
        return response


def _create_audit_middleware(options: dict[str, Any], context: PluginContext) -> AuditMiddleware:
    """Factory for audit middleware (ADR-002-B: security policy is immutable)."""
    opts = dict(options)
    # ADR-002-B: security_level is hard-coded in plugin, not passed as parameter
    return AuditMiddleware(
        include_prompts=bool(opts.get("include_prompts", False)),
        channel=opts.get("channel"),
    )


register_middleware(
    "audit_logger",
    _create_audit_middleware,
    schema=_AUDIT_SCHEMA,
)


__all__ = ["AuditMiddleware"]
