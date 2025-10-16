"""AuditMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
from typing import Any

from elspeth.core.protocols import LLMMiddleware, LLMRequest
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


class AuditMiddleware(LLMMiddleware):
    name = "audit_logger"

    def __init__(self, *, include_prompts: bool = False, channel: str | None = None):
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


register_middleware(
    "audit_logger",
    lambda options, context: AuditMiddleware(
        include_prompts=bool(options.get("include_prompts", False)),
        channel=options.get("channel"),
    ),
    schema=_AUDIT_SCHEMA,
)


__all__ = ["AuditMiddleware"]
