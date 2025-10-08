from pathlib import Path

import pandas as pd
import pytest
import requests

from dmp.core.llm.middleware import LLMRequest
from dmp.core.llm.registry import create_middlewares
from dmp.core.experiments.runner import ExperimentRunner
from dmp.core.experiments.config import ExperimentSuite, ExperimentConfig
from dmp.core.experiments.suite_runner import ExperimentSuiteRunner
from dmp.plugins.llms.middleware_azure import AzureEnvironmentMiddleware


class DummyLLM:
    def __init__(self):
        self.calls = []

    def generate(self, *, system_prompt, user_prompt, metadata=None):
        self.calls.append((system_prompt, user_prompt, metadata))
        return {"content": user_prompt, "metrics": {}}


class CollectingMiddleware:
    name = "collect"

    def __init__(self, box):
        self.box = box

    def before_request(self, request: LLMRequest):
        self.box.append(("before", request.user_prompt))
        return request

    def after_response(self, request: LLMRequest, response):
        self.box.append(("after", response.get("content")))
        return response


def test_middleware_chain(monkeypatch):
    from dmp.core.llm import registry as mw_registry

    box = []
    mw_registry.register_middleware("collect", lambda options: CollectingMiddleware(box))
    middlewares = create_middlewares([{"name": "collect"}])

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[],
        prompt_system="sys",
        prompt_template="Hello {{ APPID }}",
        llm_middlewares=middlewares,
    )

    import pandas as pd

    df = pd.DataFrame({"APPID": ["1"]})
    runner.run(df)

    assert ("before", "Hello 1") in box
    assert ("after", "Hello 1") in box


def test_prompt_shield_blocks():
    middlewares = create_middlewares(
        [{"name": "prompt_shield", "options": {"denied_terms": ["forbidden"], "on_violation": "abort"}}]
    )

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[],
        prompt_system="sys",
        prompt_template="{{ text }}",
        llm_middlewares=middlewares,
    )

    import pandas as pd

    df = pd.DataFrame({"text": ["forbidden data"]})
    payload = runner.run(df)

    assert "failures" in payload
    assert payload["failures"][0]["error"]


def test_prompt_shield_masks(caplog):
    middlewares = create_middlewares(
        [
            {
                "name": "prompt_shield",
                "options": {"denied_terms": ["top secret"], "on_violation": "mask", "mask": "***"},
            }
        ]
    )

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[],
        prompt_system="sys",
        prompt_template="{{ text }}",
        llm_middlewares=middlewares,
    )

    import pandas as pd

    df = pd.DataFrame({"text": ["this is top secret info"]})
    with caplog.at_level("WARNING"):
        payload = runner.run(df)

    assert payload["results"]
    assert any("blocked term" in message for message in caplog.messages)


def test_prompt_shield_logs_warning(caplog):
    middlewares = create_middlewares(
        [
            {
                "name": "prompt_shield",
                "options": {
                    "denied_terms": ["restricted"],
                    "on_violation": "mask",
                    "mask": "***",
                    "channel": "test.prompt_shield",
                },
            }
        ]
    )

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[],
        prompt_system="sys",
        prompt_template="{{ text }}",
        llm_middlewares=middlewares,
    )

    df = pd.DataFrame({"text": ["restricted disclosure"]})
    with caplog.at_level("WARNING"):
        runner.run(df)

    assert any("blocked term" in record.message for record in caplog.records)


def test_azure_content_safety_blocks(monkeypatch):
    from dmp.plugins.llms.middleware import AzureContentSafetyMiddleware

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(url, headers, json, timeout):
        assert "api-version" in url
        return DummyResponse({"results": [{"category": "Hate", "severity": 6}]})

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("AZURE_CS_KEY", "secret")

    middleware = AzureContentSafetyMiddleware(
        endpoint="https://example.cognitiveservices.azure.com",
        key_env="AZURE_CS_KEY",
        severity_threshold=4,
        on_violation="abort",
    )

    with pytest.raises(ValueError):
        middleware.before_request(LLMRequest(system_prompt="sys", user_prompt="bad content", metadata={}))

    monkeypatch.delenv("AZURE_CS_KEY", raising=False)


def test_azure_content_safety_masks(monkeypatch):
    from dmp.plugins.llms.middleware import AzureContentSafetyMiddleware

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"category": "Hate", "severity": 5}]}

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: DummyResponse())

    middleware = AzureContentSafetyMiddleware(
        endpoint="https://example.cognitiveservices.azure.com",
        key="secret",
        severity_threshold=4,
        on_violation="mask",
        mask="***",
    )

    request = LLMRequest(system_prompt="sys", user_prompt="bad prompt", metadata={})
    updated = middleware.before_request(request)
    assert updated.user_prompt == "***"


def test_azure_content_safety_skip_on_error(monkeypatch, caplog):
    from dmp.plugins.llms.middleware import AzureContentSafetyMiddleware

    def fake_post(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr("requests.post", fake_post)

    middleware = AzureContentSafetyMiddleware(
        endpoint="https://example.cognitiveservices.azure.com",
        key="secret",
        on_violation="abort",
        on_error="skip",
    )

    request = LLMRequest(system_prompt="sys", user_prompt="ok prompt", metadata={})
    with caplog.at_level("WARNING"):
        middleware.before_request(request)
    assert any("Content Safety call failed" in message for message in caplog.messages)


class DummyAzureRun:
    def __init__(self):
        self.rows = []
        self.logs = []
        self.tables = {}

    def log_row(self, name, **payload):
        self.rows.append((name, payload))

    def log(self, name, value):
        self.logs.append((name, value))

    def log_table(self, name, payload):
        self.tables[name] = payload


def test_azure_environment_middleware_logs(monkeypatch):
    run = DummyAzureRun()
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: run,
    )

    middleware = AzureEnvironmentMiddleware()
    request = LLMRequest(
        system_prompt="sys",
        user_prompt="hello",
        metadata={"row_id": "123", "attempt": 1},
    )

    updated_request = middleware.before_request(request)
    assert updated_request.metadata.get("azure_sequence")

    response = {"metrics": {"prompt_tokens": 5, "completion_tokens": 7}}
    middleware.after_response(updated_request, response)

    assert run.rows
    names = [entry[0] for entry in run.rows]
    assert "llm_request" in names
    assert "llm_response" in names
    request_payload = next(payload for name, payload in run.rows if name == "llm_request")
    response_payload = next(payload for name, payload in run.rows if name == "llm_response")
    assert request_payload["row_id"] == "123"
    assert response_payload.get("metric_prompt_tokens") == 5


def test_azure_environment_middleware_log_metrics_toggle(monkeypatch):
    run = DummyAzureRun()
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: run,
    )

    middleware = AzureEnvironmentMiddleware(log_metrics=False)
    request = LLMRequest(system_prompt="sys", user_prompt="hello", metadata={})
    updated_request = middleware.before_request(request)
    middleware.after_response(updated_request, {"metrics": {"prompt_tokens": 5}})

    response_payload = next(payload for name, payload in run.rows if name == "llm_response")
    assert "metric_prompt_tokens" not in response_payload


def test_azure_environment_middleware_defaults_to_skip_when_no_run(monkeypatch, caplog):
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: None,
    )

    with caplog.at_level("INFO"):
        middleware = AzureEnvironmentMiddleware()

    assert middleware is not None
    assert any("telemetry logging will be disabled" in msg for msg in caplog.messages)


def test_azure_environment_middleware_on_error_skip(monkeypatch, caplog):
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: None,
    )
    monkeypatch.setenv("AZUREML_RUN_ID", "run-123")

    with caplog.at_level("WARNING"):
        middleware = AzureEnvironmentMiddleware(on_error="skip")

    assert middleware is not None
    assert any("Continuing without run context" in msg for msg in caplog.messages)
    monkeypatch.delenv("AZUREML_RUN_ID", raising=False)


def test_azure_environment_middleware_on_error_abort(monkeypatch):
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: None,
    )
    with pytest.raises(RuntimeError):
        AzureEnvironmentMiddleware(on_error="abort")


def test_middleware_retry_hook_invoked(monkeypatch):
    from dmp.core.llm import registry as mw_registry

    events = []

    class RetryMiddleware:
        name = "retry_tracker"

        def before_request(self, request):
            return request

        def after_response(self, request, response):
            return response

        def on_retry_exhausted(self, request, metadata, error):
            events.append({"metadata": metadata, "error": str(error)})

    mw_registry.register_middleware("retry_tracker", lambda options: RetryMiddleware())

    class FailingLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            raise RuntimeError("boom")

    runner = ExperimentRunner(
        llm_client=FailingLLM(),
        sinks=[],
        prompt_system="sys",
        prompt_template="Hello",
        prompt_fields=[],
        retry_config={"max_attempts": 2, "initial_delay": 0},
        llm_middlewares=create_middlewares([{"name": "retry_tracker"}]),
    )

    import pandas as pd

    df = pd.DataFrame({"APPID": ["1"]})
    payload = runner.run(df)

    assert payload["failures"]
    assert events


def test_health_monitor_middleware_logs(caplog):
    from dmp.plugins.llms.middleware import HealthMonitorMiddleware

    middleware = HealthMonitorMiddleware(heartbeat_interval=0.0, stats_window=5, channel="test.health")
    request = LLMRequest(system_prompt="sys", user_prompt="hello", metadata={})

    with caplog.at_level("INFO"):
        updated = middleware.before_request(request)
        middleware.after_response(updated, {"content": "ok", "metrics": {"score": 1}})

    assert any("health heartbeat" in message for message in caplog.messages)


def test_health_monitor_middleware_tracks_failures(caplog):
    from dmp.plugins.llms.middleware import HealthMonitorMiddleware

    middleware = HealthMonitorMiddleware(heartbeat_interval=0.0, stats_window=5, channel="test.health")
    request = LLMRequest(system_prompt="sys", user_prompt="hello", metadata={})

    middleware.before_request(request)
    middleware.after_response(request, {"error": "boom"})

    with caplog.at_level("INFO"):
        middleware.before_request(request)
        middleware.after_response(request, {"content": "ok"})

    assert any("'failures': 1" in message for message in caplog.messages)


def test_azure_environment_retry_logging(monkeypatch):
    run = DummyAzureRun()
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: run,
    )

    middleware = AzureEnvironmentMiddleware()
    request = LLMRequest(system_prompt="sys", user_prompt="prompt", metadata={"azure_sequence": "az-1"})
    metadata = {
        "attempts": 3,
        "max_attempts": 3,
        "error": "boom",
        "error_type": "RuntimeError",
        "history": [{"attempt": 1, "status": "error"}],
    }
    middleware.on_retry_exhausted(request, metadata, RuntimeError("boom"))

    names = [entry[0] for entry in run.rows]
    assert "llm_retry_exhausted" in names
    payload = next(data for name, data in run.rows if name == "llm_retry_exhausted")
    assert payload["attempts"] == 3
    assert "history" in payload


def test_suite_runner_applies_per_experiment_azure_middleware(monkeypatch):
    run = DummyAzureRun()
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: run,
    )

    baseline = ExperimentConfig(
        name="baseline",
        temperature=0.0,
        max_tokens=10,
        prompt_system="sys",
        prompt_template="{{ APPID }}",
        is_baseline=True,
        llm_middleware_defs=[{"name": "azure_environment"}],
    )
    variant = ExperimentConfig(
        name="variant",
        temperature=0.0,
        max_tokens=10,
        prompt_system="sys",
        prompt_template="{{ APPID }}",
        llm_middleware_defs=[{"name": "azure_environment"}],
        baseline_plugin_defs=[{"name": "row_count"}],
    )

    suite = ExperimentSuite(root=Path("."), experiments=[baseline, variant], baseline=baseline)
    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=DummyLLM(),
        sinks=[],
    )

    df = pd.DataFrame({"APPID": ["42"]})
    results = runner.run(
        df,
        defaults={
            "prompt_system": "sys",
            "prompt_template": "{{ APPID }}",
            "baseline_plugin_defs": [{"name": "row_count"}],
        },
    )

    assert "baseline" in results and "variant" in results
    names = [entry[0] for entry in run.rows]
    assert "experiments" in names
    assert "experiment_start" in names
    assert "experiment_complete" in names
    assert "suite_summary" in names
    assert any(name.startswith("baseline_variant") for name in run.tables)


def test_suite_runner_deduplicates_shared_middleware(monkeypatch):
    events = []

    class SharedMiddleware:
        name = "shared"

        def on_suite_loaded(self, suite_metadata, preflight):
            events.append(("suite_loaded", tuple(exp["experiment"] for exp in suite_metadata)))

        def on_experiment_start(self, name, metadata):
            events.append(("start", name))

        def on_experiment_complete(self, name, payload, metadata):
            events.append(("complete", name))

        def on_suite_complete(self):
            events.append(("suite_complete", None))

        def before_request(self, request):
            return request

        def after_response(self, request, response):
            return response

    from dmp.core.llm import registry as mw_registry

    mw_registry.register_middleware("shared", lambda options: SharedMiddleware())

    exp_config = ExperimentConfig(
        name="exp",
        temperature=0.0,
        max_tokens=10,
        prompt_system="sys",
        prompt_template="{{ APPID }}",
        llm_middleware_defs=[{"name": "shared"}],
    )

    suite = ExperimentSuite(root=Path("."), experiments=[exp_config], baseline=exp_config)
    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=DummyLLM(),
        sinks=[],
    )

    df = pd.DataFrame({"APPID": ["1"]})
    runner.run(
        df,
        defaults={
            "prompt_system": "sys",
            "prompt_template": "{{ APPID }}",
            "llm_middleware_defs": [{"name": "shared"}],
        },
    )

    assert events.count(("suite_loaded", ("exp",))) == 1
    assert events.count(("suite_complete", None)) == 1


def test_azure_environment_middleware_log_config_diffs_toggle(monkeypatch):
    run = DummyAzureRun()
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: run,
    )

    middleware = AzureEnvironmentMiddleware(log_config_diffs=False)
    middleware.on_baseline_comparison("exp", {"plugin": {"a": 1}})

    assert run.tables == {}


def test_azure_environment_middleware_logs_aggregate_table(monkeypatch):
    run = DummyAzureRun()
    monkeypatch.setattr(
        "dmp.plugins.llms.middleware_azure._resolve_azure_run",
        lambda: run,
    )

    middleware = AzureEnvironmentMiddleware()
    middleware.on_experiment_complete(
        "exp",
        {"aggregates": {"score": {"mean": 0.5}}, "results": [{}]},
        metadata={"label": "demo"},
    )

    assert "experiment_exp_aggregates" in run.tables
def test_suite_runner_deduplicates_shared_middleware(monkeypatch):
    events = []

    class SharedMiddleware:
        name = "shared"

        def on_suite_loaded(self, suite_metadata, preflight):
            events.append(("suite_loaded", tuple(exp["experiment"] for exp in suite_metadata)))

        def on_experiment_start(self, name, metadata):
            events.append(("start", name))

        def on_experiment_complete(self, name, payload, metadata):
            events.append(("complete", name))

        def on_suite_complete(self):
            events.append(("suite_complete", None))

    from dmp.core.llm import registry as mw_registry

    mw_registry.register_middleware("shared", lambda options: SharedMiddleware())

    baseline_config = ExperimentConfig(
        name="baseline",
        temperature=0.0,
        max_tokens=10,
        prompt_system="sys",
        prompt_template="{{ APPID }}",
        is_baseline=True,
        llm_middleware_defs=[{"name": "shared"}],
    )

    variant_config = ExperimentConfig(
        name="variant",
        temperature=0.0,
        max_tokens=10,
        prompt_system="sys",
        prompt_template="{{ APPID }}",
        llm_middleware_defs=[{"name": "shared"}],
    )

    suite = ExperimentSuite(root=Path("."), experiments=[baseline_config, variant_config], baseline=baseline_config)
    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=DummyLLM(),
        sinks=[],
    )

    df = pd.DataFrame({"APPID": ["1"]})
    runner.run(
        df,
        defaults={
            "prompt_system": "sys",
            "prompt_template": "{{ APPID }}",
            "llm_middleware_defs": [{"name": "shared"}],
        },
    )

    assert events.count(("suite_loaded", ("baseline", "variant"))) == 1
    assert events.count(("suite_complete", None)) == 1
