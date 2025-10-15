"""Built-in validation plugins for experiment responses."""

from __future__ import annotations

import json
import re
from typing import Any

from jinja2 import Template

from elspeth.core.experiments.plugin_registry import register_validation_plugin
from elspeth.core.plugin_context import PluginContext
from elspeth.core.protocols import LLMClientProtocol
from elspeth.core.registry import create_llm_from_definition
from elspeth.plugins.orchestrators.experiment.protocols import ValidationError, ValidationPlugin


def _extract_content(response: dict[str, Any]) -> str:
    content = response.get("content")
    if content is None and "response" in response:
        content = response["response"].get("content")
    if isinstance(content, str):
        return content
    return ""


class RegexValidationPlugin(ValidationPlugin):
    name = "regex_match"

    def __init__(self, *, pattern: str, flags: str | None = None):
        self.pattern = pattern
        self.flags = self._parse_flags(flags)
        self._compiled = re.compile(pattern, self.flags)

    def _parse_flags(self, flags: str | None) -> int:
        if not flags:
            return 0
        value = 0
        for token in flags.split("|"):
            token = token.strip().upper()
            if not token:
                continue
            try:
                value |= getattr(re, token)
            except AttributeError as exc:
                raise ValueError(f"Unknown regex flag '{token}'") from exc
        return value

    def validate(
        self,
        response: dict[str, Any],
        *,
        context: dict[str, Any | None] | None = None,
        metadata: dict[str, Any | None] | None = None,
    ) -> None:
        text = _extract_content(response)
        if not self._compiled.fullmatch(text):
            raise ValidationError(f"Response did not match required pattern '{self.pattern}'")


class JsonValidationPlugin(ValidationPlugin):
    name = "json"

    def __init__(self, *, ensure_object: bool = False):
        self.ensure_object = ensure_object

    def validate(
        self,
        response: dict[str, Any],
        *,
        context: dict[str, Any | None] | None = None,
        metadata: dict[str, Any | None] | None = None,
    ) -> None:
        text = _extract_content(response)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Response is not valid JSON: {exc}") from exc
        if self.ensure_object and not isinstance(parsed, dict):
            raise ValidationError("JSON response must be an object")


class LLMGuardValidationPlugin(ValidationPlugin):
    name = "llm_guard"

    def __init__(
        self,
        *,
        validator_llm: LLMClientProtocol,
        user_prompt_template: str,
        system_prompt: str | None = None,
        valid_token: str = "VALID",
        invalid_token: str = "INVALID",
        strip_whitespace: bool = True,
    ):
        self.validator_llm = validator_llm
        self.system_prompt = system_prompt or "You evaluate whether a response meets the rules."
        self.template = Template(user_prompt_template)
        self.valid_token = valid_token.strip()
        self.invalid_token = invalid_token.strip()
        self.strip_whitespace = strip_whitespace

    def validate(
        self,
        response: dict[str, Any],
        *,
        context: dict[str, Any | None] | None = None,
        metadata: dict[str, Any | None] | None = None,
    ) -> None:
        text = _extract_content(response)
        render_ctx = {
            "response": response,
            "content": text,
            "context": context or {},
            "metadata": metadata or {},
        }
        user_prompt = self.template.render(**render_ctx)
        result = self.validator_llm.generate(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            metadata={"validator": self.name, **(metadata or {})},
        )
        verdict = _extract_content(result).strip()
        if self.strip_whitespace:
            verdict = verdict.splitlines()[0].strip()
        verdict_upper = verdict.upper()
        if self.invalid_token.upper() in verdict_upper:
            raise ValidationError("LLM guard marked response as invalid")
        if self.valid_token.upper() not in verdict_upper:
            raise ValidationError("LLM guard returned unexpected verdict")


def _build_regex_validator(options: dict[str, Any], context: PluginContext) -> RegexValidationPlugin:
    pattern = options.get("pattern")
    if not pattern:
        raise ValueError("regex_match validation plugin requires 'pattern' configuration")
    return RegexValidationPlugin(
        pattern=pattern,
        flags=options.get("flags"),
    )


register_validation_plugin(
    "regex_match",
    _build_regex_validator,
    schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "flags": {"type": "string"},
        },
        "required": ["pattern"],
        "additionalProperties": True,
    },
)

register_validation_plugin(
    "json",
    lambda options, context: JsonValidationPlugin(ensure_object=bool(options.get("ensure_object", False))),
    schema={
        "type": "object",
        "properties": {
            "ensure_object": {"type": "boolean"},
        },
        "additionalProperties": True,
    },
)


def _build_llm_guard(options: dict[str, Any], context: PluginContext) -> LLMGuardValidationPlugin:
    from elspeth.core.validation_base import ConfigurationError

    llm_spec = options.get("validator_llm") or options.get("llm")
    if llm_spec is None:
        raise ValueError("LLM guard validation plugin requires 'validator_llm'")
    validator_llm = create_llm_from_definition(
        llm_spec,
        parent_context=context,
        provenance=("validator_llm",),
    )

    template = options.get("user_prompt_template") or options.get("prompt_template")
    if not template:
        raise ValueError("LLM guard validation plugin requires 'user_prompt_template'")

    if "valid_token" not in options:
        raise ConfigurationError("valid_token is required for llm_guard validation plugin")
    if "invalid_token" not in options:
        raise ConfigurationError("invalid_token is required for llm_guard validation plugin")
    if "strip_whitespace" not in options:
        raise ConfigurationError("strip_whitespace is required for llm_guard validation plugin")

    return LLMGuardValidationPlugin(
        validator_llm=validator_llm,
        user_prompt_template=template,
        system_prompt=options.get("system_prompt"),
        valid_token=options["valid_token"],
        invalid_token=options["invalid_token"],
        strip_whitespace=options["strip_whitespace"],
    )


register_validation_plugin(
    "llm_guard",
    _build_llm_guard,
    schema={
        "type": "object",
        "properties": {
            "validator_llm": {"type": "object"},
            "llm": {"type": "object"},
            "system_prompt": {"type": "string"},
            "user_prompt_template": {"type": "string"},
            "prompt_template": {"type": "string"},
            "valid_token": {
                "type": "string",
                "description": "Token indicating valid response (required). LLM should return this token for passing validation.",
            },
            "invalid_token": {
                "type": "string",
                "description": "Token indicating invalid response (required). LLM should return this token for failing validation.",
            },
            "strip_whitespace": {
                "type": "boolean",
                "description": "Strip whitespace from validator response (required). Takes only first line of response.",
            },
        },
        "required": ["valid_token", "invalid_token", "strip_whitespace"],
        "additionalProperties": True,
    },
)


__all__ = [
    "RegexValidationPlugin",
    "JsonValidationPlugin",
    "LLMGuardValidationPlugin",
]
