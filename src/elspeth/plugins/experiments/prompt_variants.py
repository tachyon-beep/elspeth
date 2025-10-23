"""Prompt variant generation plugins."""

from __future__ import annotations

from typing import Any

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMClientProtocol
from elspeth.core.experiments.plugin_registry import register_aggregation_plugin
from elspeth.core.prompts.engine import PromptEngine
from elspeth.core.registries.llm import create_llm_from_definition
from elspeth.plugins.orchestrators.experiment.protocols import AggregationExperimentPlugin


class PromptVariantsAggregator(AggregationExperimentPlugin):
    """Generate alternative prompt phrasings using a secondary LLM."""

    name = "prompt_variants"

    def __init__(
        self,
        *,
        variant_llm: LLMClientProtocol,
        prompt_template: str,
        count: int = 5,
        strip: bool = True,
        metadata_key: str = "prompt_variants",
        max_attempts: int = 3,
        variant_system_prompt: str | None = None,
    ) -> None:
        self.variant_llm = variant_llm
        self.prompt_template = prompt_template
        self.count = max(int(count or 1), 1)
        self.strip = strip
        self.metadata_key = metadata_key
        self.max_attempts = max(int(max_attempts or 1), 1)
        self.variant_system_prompt = variant_system_prompt or "You generate prompt variations that preserve placeholders."
        self.engine = PromptEngine()

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}

        first = records[0]
        metadata = first.get("metadata") or {}
        response = first.get("response") or {}
        system_prompt = metadata.get("prompt_system") or response.get("system_prompt") or ""
        user_prompt = metadata.get("prompt_user") or response.get("user_prompt") or ""
        user_prompt_template = metadata.get("prompt_user_template") or user_prompt
        system_prompt_template = metadata.get("prompt_system_template") or system_prompt

        placeholder_fields: list[str] = []
        metadata_fields = metadata.get("prompt_user_fields")
        if isinstance(metadata_fields, list):
            placeholder_fields = [str(field) for field in metadata_fields]
        if not placeholder_fields and user_prompt_template:
            compiled_template = self.engine.compile(
                user_prompt_template,
                name="prompt_variants:user_template",
            )
            placeholder_fields = list(compiled_template.required_fields)
        placeholder_tokens = [f"{{{{ {field} }}}}" for field in placeholder_fields]

        template = self.engine.compile(self.prompt_template, name="prompt_variants")
        render_ctx = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "system_prompt_template": system_prompt_template,
            "user_prompt_template": user_prompt_template,
            "placeholder_fields": placeholder_fields,
            "placeholder_tokens": placeholder_tokens,
            "metadata": metadata,
            "response": response,
            "count": self.count,
        }

        generated: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for index in range(self.count):
            last_result: dict[str, Any] | None = None
            missing_tokens: list[str] = []
            attempts = 0
            while attempts < self.max_attempts:
                attempts += 1
                rendered = self.engine.render(
                    template,
                    {
                        **render_ctx,
                        "index": index,
                        "attempt": attempts,
                        "max_attempts": self.max_attempts,
                        "previous_response": last_result,
                        "missing_tokens": missing_tokens,
                    },
                )
                result = self.variant_llm.generate(
                    system_prompt=self.variant_system_prompt,
                    user_prompt=rendered,
                    metadata={
                        "variant_index": index,
                        "attempt": attempts,
                        "placeholder_tokens": placeholder_tokens,
                        "placeholder_fields": placeholder_fields,
                    },
                )
                last_result = result or {}
                text = last_result.get("content") or ""
                if self.strip:
                    text = text.strip()
                missing_tokens = [token for token in placeholder_tokens if token not in text]
                if text and not missing_tokens:
                    generated.append(
                        {
                            "index": index,
                            "prompt": text,
                            "attempts": attempts,
                            "response": last_result,
                        }
                    )
                    break
            else:
                failures.append(
                    {
                        "index": index,
                        "attempts": attempts,
                        "missing_placeholders": missing_tokens,
                        "last_response": last_result,
                    }
                )

        payload = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "system_prompt_template": system_prompt_template,
            "user_prompt_template": user_prompt_template,
            "placeholder_fields": placeholder_fields,
            "placeholder_tokens": placeholder_tokens,
            "variants": generated,
        }
        # Intentionally include an explicit failures key even when empty.
        # Downstream consumers and reports rely on a stable schema
        # (failures: list) to simplify validation and rendering.
        payload["failures"] = failures
        return payload


def _build_prompt_variants(options: dict[str, Any], context: PluginContext) -> PromptVariantsAggregator:
    spec = options.get("variant_llm") or options.get("llm")
    if spec is None:
        raise ValueError("prompt_variants plugin requires 'variant_llm'")
    llm = create_llm_from_definition(
        spec,
        parent_context=context,
        provenance=("variant_llm",),
    )

    template = options.get("prompt_template")
    if not template:
        raise ValueError("prompt_variants plugin requires 'prompt_template'")

    return PromptVariantsAggregator(
        variant_llm=llm,
        prompt_template=template,
        count=options.get("count", 5),
        strip=options.get("strip", True),
        metadata_key=options.get("metadata_key", "prompt_variants"),
        max_attempts=options.get("max_attempts", 3),
        variant_system_prompt=options.get("variant_system_prompt"),
    )


register_aggregation_plugin(
    "prompt_variants",
    _build_prompt_variants,
    schema={
        "type": "object",
        "properties": {
            "prompt_template": {"type": "string"},
            "variant_llm": {"type": "object"},
            "llm": {"type": "object"},
            "count": {"type": "integer", "minimum": 1},
            "strip": {"type": "boolean"},
            "metadata_key": {"type": "string"},
            "max_attempts": {"type": "integer", "minimum": 1},
            "variant_system_prompt": {"type": "string"},
        },
        "required": ["prompt_template"],
        "additionalProperties": True,
    },
)


__all__ = ["PromptVariantsAggregator"]
