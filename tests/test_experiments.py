import json
import threading
import time

import pandas as pd
import pytest

from elspeth.core.controls.cost_tracker import FixedPriceCostTracker
from elspeth.core.controls.rate_limit import NoopRateLimiter
from elspeth.core.experiments import plugin_registry as exp_plugin_registry
from elspeth.core.experiments.config import ExperimentSuite
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner


def _secure_sink(sink, level: str = "official"):
    setattr(sink, "_elspeth_security_level", level)
    return sink


def test_experiment_suite_load(tmp_path):
    exp_root = tmp_path / "experiments"
    (exp_root / "exp1").mkdir(parents=True)
    (exp_root / "exp2").mkdir(parents=True)
    (exp_root / "exp1" / "config.json").write_text(
        json.dumps(
            {
                "name": "exp1",
                "temperature": 0.5,
                "max_tokens": 128,
                "enabled": True,
                "is_baseline": True,
                "prompt_fields": ["APPID"],
                "criteria": [{"name": "crit", "template": "Crit {APPID}"}],
            }
        ),
        encoding="utf-8",
    )
    (exp_root / "exp1" / "system_prompt.md").write_text("Sys", encoding="utf-8")
    (exp_root / "exp1" / "user_prompt.md").write_text("User {APPID}", encoding="utf-8")
    (exp_root / "exp2" / "config.json").write_text(
        json.dumps(
            {
                "name": "exp2",
                "temperature": 0.7,
                "max_tokens": 256,
                "enabled": True,
            }
        ),
        encoding="utf-8",
    )

    suite = ExperimentSuite.load(exp_root)
    assert len(suite.experiments) == 2
    assert suite.baseline.name == "exp1"
    assert suite.baseline.prompt_system == "Sys"
    assert suite.baseline.prompt_template == "User {APPID}"
    assert suite.baseline.prompt_fields == ["APPID"]
    assert suite.baseline.criteria[0]["name"] == "crit"


def test_experiment_runner(monkeypatch):
    captured = {"calls": 0}

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            captured["calls"] += 1
            captured["prompt"] = user_prompt
            return {"content": "ok"}

    class DummySink:
        def __init__(self):
            self.payloads = []
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            self.payloads.append((results, metadata))

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="Test {APPID}",
        prompt_fields=["APPID"],
    )

    df = pd.DataFrame({"APPID": ["1", "2"]})

    payload = runner.run(df)
    assert captured["calls"] == 2
    assert "Test" in captured["prompt"]
    assert len(payload["results"]) == 2


def test_experiment_runner_with_criteria():
    calls = []

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            calls.append(metadata["criteria"])
            return {"content": f"resp-{metadata['criteria']}"}

    class DummySink:
        def __init__(self):
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="unused",
        prompt_fields=["APPID"],
        criteria=[
            {"name": "crit1", "template": "Crit1 {{ APPID }}"},
            {"name": "crit2", "template": "Crit2 {{ APPID }}"},
        ],
    )

    df = pd.DataFrame({"APPID": ["1"]})
    payload = runner.run(df)

    assert calls == ["crit1", "crit2"]
    assert "responses" in payload["results"][0]
    assert "crit1" in payload["results"][0]["responses"]


def test_experiment_runner_plugins():
    class DummyRowPlugin:
        name = "row"

        def process_row(self, row, responses):
            return {"length": len(responses)}

    class DummyAggPlugin:
        name = "agg"

        def finalize(self, records):
            return {"count": len(records)}

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": "resp"}

    class DummySink:
        def __init__(self):
            self.meta = None
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            self.meta = metadata

    sink = _secure_sink(DummySink())
    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[sink],
        prompt_system="sys",
        prompt_template="Row {APPID}",
        prompt_fields=["APPID"],
        row_plugins=[DummyRowPlugin()],
        aggregator_plugins=[DummyAggPlugin()],
    )

    df = pd.DataFrame({"APPID": ["1", "2"]})
    payload = runner.run(df)

    assert payload["results"][0]["metrics"]["length"] == 1
    assert payload["aggregates"]["agg"]["count"] == 2
    assert sink.meta["aggregates"]["agg"]["count"] == 2


def test_experiment_runner_jinja_prompts():
    class DummyLLM:
        def __init__(self):
            self.prompts = []

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.prompts.append((system_prompt, user_prompt))
            return {"content": user_prompt}

    class DummySink:
        def __init__(self):
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="System {{ APPID }}",
        prompt_template="Hello {{ APPID }}{% if FLAG %} {{ FLAG }}{% endif %}",
        prompt_defaults={"FLAG": ""},
    )

    df = pd.DataFrame({"APPID": ["007"], "FLAG": [""]})
    payload = runner.run(df)

    assert payload["results"][0]["response"]["content"].strip() == "Hello 007"


def test_experiment_runner_concurrency(monkeypatch):
    class SlowLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.calls += 1
            time.sleep(0.05)
            return {"content": user_prompt, "metrics": {}}

    class DummySink:
        def __init__(self):
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentRunner(
        llm_client=SlowLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="Hello {{ APPID }}",
        rate_limiter=NoopRateLimiter(),
        concurrency_config={
            "enabled": True,
            "max_workers": 4,
            "backlog_threshold": 1,
            "utilization_pause": 0.95,
            "pause_interval": 0.01,
        },
    )

    df = pd.DataFrame({"APPID": ["1", "2", "3", "4"]})
    start = time.perf_counter()
    payload = runner.run(df)
    elapsed = time.perf_counter() - start

    assert len(payload["results"]) == 4
    assert elapsed < 0.2  # parallel execution should be faster than sequential ~0.2s


def test_experiment_suite_runner(tmp_path):
    exp_root = tmp_path / "suite"
    (exp_root / "expA").mkdir(parents=True)
    (exp_root / "expB").mkdir(parents=True)
    (exp_root / "expA" / "config.json").write_text(
        '{"name": "expA", "enabled": true, "temperature": 0.6, "max_tokens": 128}',
        encoding="utf-8",
    )
    (exp_root / "expA" / "user_prompt.md").write_text("A {APPID}", encoding="utf-8")
    (exp_root / "expB" / "config.json").write_text(
        '{"name": "expB", "enabled": true, "temperature": 0.7, "max_tokens": 256}',
        encoding="utf-8",
    )
    (exp_root / "expB" / "user_prompt.md").write_text("B {APPID}", encoding="utf-8")

    suite = ExperimentSuite.load(exp_root)

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=DummyLLM(),
        sinks=[_secure_sink(DummySink())],
    )

    df = pd.DataFrame({"APPID": ["1"]})
    results = runner.run(
        df,
        defaults={
            "prompt_system": "sys",
            "prompt_fields": ["APPID"],
            "prompt_packs": {},
        },
        sink_factory=lambda exp: [_secure_sink(DummySink())],
    )

    assert set(results.keys()) == {"expA", "expB"}
    assert results["expA"]["payload"]["results"][0]["response"]["content"] == "A 1"


def test_experiment_runner_cost_tracker():
    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": "ok", "raw": {"usage": {"prompt_tokens": 3, "completion_tokens": 2}}}

    class DummySink:
        def write(self, results, *, metadata=None):
            self.meta = metadata

    sink = _secure_sink(DummySink())
    tracker = FixedPriceCostTracker(prompt_token_price=0.01, completion_token_price=0.02)
    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[sink],
        prompt_system="sys",
        prompt_template="Hello {APPID}",
        prompt_fields=["APPID"],
        cost_tracker=tracker,
    )

    df = pd.DataFrame({"APPID": ["1"]})
    payload = runner.run(df)

    assert payload["cost_summary"]["total_cost"] == pytest.approx(3 * 0.01 + 2 * 0.02)


def test_suite_runner_prompt_pack(tmp_path):
    exp_root = tmp_path / "suite"
    (exp_root / "exp").mkdir(parents=True)
    (exp_root / "exp" / "config.json").write_text(
        '{"name": "exp", "enabled": true, "prompt_pack": "pack", "temperature": 0.5, "max_tokens": 128}',
        encoding="utf-8",
    )

    suite = ExperimentSuite.load(exp_root)

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=DummyLLM(),
        sinks=[_secure_sink(DummySink())],
    )

    df = pd.DataFrame({"APPID": ["1"]})
    pack = {
        "prompts": {"system": "pack-sys", "user": "Pack {APPID}"},
        "prompt_fields": ["APPID"],
    }
    results = runner.run(
        df,
        defaults={
            "prompt_packs": {"pack": pack},
            "prompt_pack": "pack",
        },
    )

    payload = results["exp"]["payload"]
    assert payload["results"][0]["response"]["content"] == "Pack 1"


def test_suite_runner_with_plugin_definitions(tmp_path, monkeypatch):
    exp_root = tmp_path / "suite"
    (exp_root / "baseline").mkdir(parents=True)
    (exp_root / "variant").mkdir(parents=True)
    (exp_root / "baseline" / "config.json").write_text(
        '{"name": "baseline", "enabled": true, "is_baseline": true, "temperature": 0.4, "max_tokens": 128}',
        encoding="utf-8",
    )
    (exp_root / "baseline" / "user_prompt.md").write_text("Base {APPID}", encoding="utf-8")
    (exp_root / "variant" / "config.json").write_text(
        json.dumps(
            {
                "name": "variant",
                "enabled": True,
                "temperature": 0.6,
                "max_tokens": 256,
                "row_plugins": [
                    {
                        "name": "test_row",
                        "security_level": "OFFICIAL",
                        "determinism_level": "guaranteed",  # Inherits security_level from parent
                        "options": {"value": 5},
                    }
                ],
                "aggregator_plugins": [
                    {
                        "name": "test_agg",
                        "security_level": "OFFICIAL",
                        "determinism_level": "guaranteed",  # Inherits security_level from parent
                        "options": {"key": "total"},
                    }
                ],
                "baseline_plugins": [
                    {
                        "name": "noop",
                        "security_level": "OFFICIAL",
                        "determinism_level": "guaranteed",  # Inherits security_level from parent
                        "options": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (exp_root / "variant" / "user_prompt.md").write_text("Var {APPID}", encoding="utf-8")

    suite = ExperimentSuite.load(exp_root)

    class CustomRowPlugin:
        def __init__(self, value):
            self.name = "custom_row"
            self._value = value

        def process_row(self, row, responses):
            return {"value": self._value}

    class CustomAggPlugin:
        def __init__(self, key):
            self.name = "test_agg"
            self._key = key

        def finalize(self, records):
            return {self._key: len(records)}

    exp_plugin_registry.register_row_plugin("test_row", lambda opts, context: CustomRowPlugin(opts.get("value", 0)))
    exp_plugin_registry.register_aggregation_plugin("test_agg", lambda opts, context: CustomAggPlugin(opts.get("key", "total")))

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=DummyLLM(),
        sinks=[_secure_sink(DummySink())],
    )

    df = pd.DataFrame({"APPID": ["1"]})
    results = runner.run(
        df,
        defaults={
            "prompt_system": "sys",
            "prompt_template": "Exp {APPID}",
            "prompt_fields": ["APPID"],
        },
    )

    variant_payload = results["variant"]["payload"]
    assert variant_payload["results"][0]["metrics"]["value"] == 5
    assert variant_payload["aggregates"]["test_agg"]["total"] == 1
    # Test passes - plugin definitions (row and aggregator) work correctly


def test_execute_llm_retry(monkeypatch):
    class FlakyLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.calls += 1
            if self.calls < 2:
                raise RuntimeError("fail")
            return {"content": "ok"}

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

    sleep_calls = []

    def track_sleep(x):
        sleep_calls.append(x)

    monkeypatch.setattr("elspeth.core.experiments.runner.time.sleep", track_sleep)

    runner = ExperimentRunner(
        llm_client=FlakyLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="Hello",
        prompt_fields=[],
        retry_config={"max_attempts": 3, "initial_delay": 0, "backoff_multiplier": 1},
    )

    df = pd.DataFrame({"APPID": ["1"]})
    payload = runner.run(df)
    assert payload["results"][0]["response"]["metrics"]["attempts_used"] == 2
    retry_info = payload["results"][0]["retry"]
    assert retry_info["attempts"] == 2
    assert len(retry_info["history"]) == 2
    assert retry_info["history"][0]["status"] == "error"
    assert payload["metadata"]["retry_summary"]["total_retries"] == 1


def test_runner_records_failures(tmp_path):
    class FailingLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            raise RuntimeError("boom")

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentRunner(
        llm_client=FailingLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="Hi",
        prompt_fields=[],
        retry_config={"max_attempts": 2, "initial_delay": 0},
    )

    df = pd.DataFrame({"APPID": ["1"]})
    payload = runner.run(df)
    assert "failures" in payload
    assert len(payload["failures"]) == 1
    failure_retry = payload["failures"][0]["retry"]
    assert failure_retry["attempts"] == 2
    assert failure_retry["history"][-1]["status"] == "error"
    assert payload["metadata"]["retry_summary"]["exhausted"] == 1


def test_checkpoint_skips_processed(tmp_path):
    checkpoint = tmp_path / "cp.txt"

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

        def collect_artifacts(self):
            return {}

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="Hello {APPID}",
        prompt_fields=["APPID"],
        checkpoint_config={"path": str(checkpoint), "field": "APPID"},
    )

    df1 = pd.DataFrame({"APPID": ["1", "2"]})
    runner.run(df1)

    df2 = pd.DataFrame({"APPID": ["1", "2", "3"]})
    payload = runner.run(df2)
    assert [r["row"]["APPID"] for r in payload["results"]] == ["3"]


def test_concurrent_rate_limiter_invocation(monkeypatch):
    class RecordingLimiter(NoopRateLimiter):
        def __init__(self):
            self.acquires = 0
            self.lock = threading.Lock()

        def acquire(self, metadata=None):
            with self.lock:
                self.acquires += 1
            return super().acquire(metadata)

    class CountingCostTracker(FixedPriceCostTracker):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def record(self, response, metadata=None):
            self.calls += 1
            return super().record(response, metadata)

    limiter = RecordingLimiter()
    tracker = CountingCostTracker()

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            time.sleep(0.01)
            return {"content": user_prompt}

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[],
        prompt_system="sys",
        prompt_template="Hi",
        prompt_fields=[],
        rate_limiter=limiter,
        cost_tracker=tracker,
        concurrency_config={"enabled": True, "max_workers": 2, "backlog_threshold": 1},
    )

    df = pd.DataFrame({"APPID": [str(i) for i in range(4)]})
    runner.run(df)
    assert limiter.acquires >= len(df)
    assert tracker.calls == len(df)


def test_experiment_runner_early_stop():
    class MetricsLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.calls += 1
            return {
                "content": user_prompt,
                "metrics": {"score": float(self.calls)},
            }

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

    runner = ExperimentRunner(
        llm_client=MetricsLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="Hello",
        prompt_fields=[],
        early_stop_config={
            "metric": "score",
            "threshold": 2,
            "comparison": "gte",
            "min_rows": 2,
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        },
    )

    df = pd.DataFrame({"APPID": ["1", "2", "3", "4"]})
    payload = runner.run(df)
    assert len(payload["results"]) == 2
    early = payload["metadata"].get("early_stop")
    assert early and early["value"] == 2.0 and early["plugin"] == "threshold"


def test_experiment_runner_early_stop_plugin_instance():
    class MetricsLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.calls += 1
            return {
                "content": user_prompt,
                "metrics": {"score": float(self.calls)},
            }

    class DummySink:
        def write(self, results, *, metadata=None):
            pass

    class ImmediateStopPlugin:
        name = "test_stop"

        def __init__(self):
            self.reset_called = 0
            self._triggered = False

        def reset(self):
            self.reset_called += 1
            self._triggered = False

        def check(self, record, *, metadata=None):
            if not self._triggered:
                self._triggered = True
                return {"reason": "manual"}
            return None

    plugin = ImmediateStopPlugin()
    setattr(plugin, "_elspeth_security_level", "official")

    runner = ExperimentRunner(
        llm_client=MetricsLLM(),
        sinks=[_secure_sink(DummySink())],
        prompt_system="sys",
        prompt_template="Hello",
        prompt_fields=[],
        early_stop_plugins=[plugin],
    )

    df = pd.DataFrame({"APPID": ["1", "2", "3"]})
    payload = runner.run(df)
    assert len(payload["results"]) == 1
    early = payload["metadata"].get("early_stop")
    assert early and early["plugin"] == "test_stop" and early["reason"] == "manual"
    assert plugin.reset_called == 1
