import pandas as pd
import pytest

from elspeth.plugins.orchestrators.experiment.protocols import ValidationError
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.plugins.experiments.validation import JsonValidationPlugin, LLMGuardValidationPlugin, RegexValidationPlugin


class DummyValidatorLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, *, system_prompt, user_prompt, metadata=None):
        self.calls += 1
        content = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return {"content": content}


def test_regex_validation_plugin_passes_and_fails():
    plugin = RegexValidationPlugin(pattern=r"^[A-Z][a-z]+$")
    plugin.validate({"content": "Valid"})
    with pytest.raises(ValidationError):
        plugin.validate({"content": "invalid value"})


def test_json_validation_plugin():
    plugin = JsonValidationPlugin(ensure_object=True)
    plugin.validate({"content": '{"foo": 1}'})
    with pytest.raises(ValidationError):
        plugin.validate({"content": "not json"})
    with pytest.raises(ValidationError):
        plugin.validate({"content": "[1,2,3]"})


def test_llm_guard_validation_plugin_accepts():
    validator = DummyValidatorLLM(["VALID"])
    plugin = LLMGuardValidationPlugin(
        validator_llm=validator,
        system_prompt="Decide validity",
        user_prompt_template="Content: {{ content }}",
        valid_token="VALID",
        invalid_token="INVALID",
    )
    plugin.validate({"content": "Some text"}, context={"colour": "blue"})
    assert validator.calls == 1


def test_llm_guard_validation_plugin_rejects():
    validator = DummyValidatorLLM(["INVALID"])
    plugin = LLMGuardValidationPlugin(
        validator_llm=validator,
        user_prompt_template="{{ content }}",
    )
    with pytest.raises(ValidationError):
        plugin.validate({"content": "Value"})
    assert validator.calls == 1


def test_runner_retries_on_validation_failure():
    call_history = []

    class FlakyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            call_history.append(user_prompt)
            if len(call_history) == 1:
                return {"content": "invalid output"}
            return {"content": "Valid"}

    class DummySink:
        def __init__(self):
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            """No-op sink used to satisfy the interface during retry tests."""
            _ = (results, metadata)

    runner = ExperimentRunner(
        llm_client=FlakyLLM(),
        sinks=[DummySink()],
        prompt_system="sys",
        prompt_template="Prompt {{ colour }}",
        prompt_fields=["colour"],
        validation_plugins=[RegexValidationPlugin(pattern=r"^[A-Z][a-z]+$")],
        retry_config={"max_attempts": 2},
    )

    df = pd.DataFrame({"colour": ["blue"]})
    payload = runner.run(df)

    assert len(call_history) == 2
    assert payload["results"][0]["response"]["content"] == "Valid"
    retry_info = payload["results"][0]["retry"]
    assert retry_info["attempts"] == 2
