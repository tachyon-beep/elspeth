import pandas as pd

from dmp.core.experiments.runner import ExperimentRunner
from dmp.plugins.experiments.prompt_variants import PromptVariantsAggregator


class SpyLLM:
    def __init__(self, prefix="Variant"):
        self.calls = []
        self.prefix = prefix

    def generate(self, *, system_prompt, user_prompt, metadata=None):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, "metadata": metadata})
        metadata = metadata or {}
        index = metadata.get("variant_index", len(self.calls) - 1)
        tokens = metadata.get("placeholder_tokens") or []
        token_block = " ".join(tokens)
        content = f"{self.prefix} {index}".strip()
        if token_block:
            content = f"{content} {token_block}".strip()
        return {"content": content}


class DummyLLM:
    def __init__(self):
        self.calls = []

    def generate(self, *, system_prompt, user_prompt, metadata=None):
        self.calls.append((system_prompt, user_prompt))
        return {
            "content": user_prompt,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "metadata": metadata or {},
        }


class DummySink:
    def __init__(self):
        self.last_metadata = None

    def write(self, results, *, metadata=None):
        self.last_metadata = metadata


def test_prompt_variants_aggregator_generates_variations():
    variant_llm = SpyLLM()
    aggregator = PromptVariantsAggregator(
        variant_llm=variant_llm,
        prompt_template=(
            "Rewrite the base prompt while preserving tokens {{ placeholder_tokens | join(', ') }}.\n"
            "Original:\n{{ user_prompt_template }}\n"
            "Return only the rewritten prompt."
        ),
        count=3,
        strip=True,
    )

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[DummySink()],
        prompt_system="Sys",
        prompt_template="Hello {{ colour }}",
        prompt_fields=["colour"],
        aggregator_plugins=[aggregator],
    )

    df = pd.DataFrame({"colour": ["blue", "green"]})
    payload = runner.run(df)

    aggregate_payload = payload["aggregates"]["prompt_variants"]
    variants = aggregate_payload["variants"]
    assert len(variants) == 3
    prompts = [item["prompt"] for item in variants]
    assert all(prompt.endswith("{{ colour }}") for prompt in prompts)
    assert aggregate_payload["placeholder_tokens"] == ["{{ colour }}"]
    assert "failures" not in aggregate_payload
    assert len(variant_llm.calls) == 3


def test_prompt_variants_handles_missing_prompt_fields():
    variant_llm = SpyLLM()
    aggregator = PromptVariantsAggregator(
        variant_llm=variant_llm,
        prompt_template="System={{ system_prompt }} User={{ user_prompt }}",
        count=2,
    )

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[DummySink()],
        prompt_system="",
        prompt_template="Test",
        aggregator_plugins=[aggregator],
    )

    df = pd.DataFrame({"colour": ["red"]})
    payload = runner.run(df)
    aggregate_payload = payload["aggregates"]["prompt_variants"]
    variants = aggregate_payload["variants"]
    assert variants
    assert variants[0]["prompt"].startswith("Variant 0")
    assert aggregate_payload["placeholder_tokens"] == []


class FickleLLM:
    def __init__(self, succeed_on_attempt=2):
        self.calls = []
        self.succeed_on_attempt = succeed_on_attempt

    def generate(self, *, system_prompt, user_prompt, metadata=None):
        metadata = metadata or {}
        self.calls.append(metadata)
        attempt = metadata.get("attempt", 1)
        tokens = metadata.get("placeholder_tokens") or []
        if attempt < self.succeed_on_attempt:
            return {"content": "Invalid prompt without placeholders"}
        content = f"Adjusted prompt containing {tokens[0]}" if tokens else "No tokens"
        return {"content": content}


def test_prompt_variants_plugin_retries_until_placeholders_preserved():
    variant_llm = FickleLLM()
    aggregator = PromptVariantsAggregator(
        variant_llm=variant_llm,
        prompt_template="Ensure placeholders {{ placeholder_tokens | join(', ') }}: {{ user_prompt_template }}",
        count=1,
        max_attempts=3,
    )

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[DummySink()],
        prompt_system="Sys",
        prompt_template="Hi {{ colour }}",
        prompt_fields=["colour"],
        aggregator_plugins=[aggregator],
    )

    df = pd.DataFrame({"colour": ["orange"]})
    payload = runner.run(df)
    aggregate_payload = payload["aggregates"]["prompt_variants"]
    variants = aggregate_payload["variants"]
    assert variants[0]["prompt"].endswith("{{ colour }}")
    assert len(variant_llm.calls) == 2
