from __future__ import annotations

import json

from elspeth.cli import _result_to_row


def test_result_to_row_flattens_responses_and_metrics():
    record = {
        "row": {"id": 1},
        "response": {"content": "primary", "metrics": {"latency_ms": 123, "nested": {"p": 1}}},
        "responses": {
            "foo": {"content": "X", "metrics": {"acc": 0.9}},
            "bar": {"content": "Y", "metrics": {"acc": 0.8}},
        },
        "metrics": {"overall": 0.95, "sub": {"a": 1, "b": 2}},
        "retry": {"attempts": 2, "max_attempts": 3, "history": [{"e": "boom"}]},
        "security_level": "OFFICIAL",
    }

    row = _result_to_row(record)

    # Top-level content and nested metrics
    assert row["llm_content"] == "primary"
    assert row["llm_content_metric_latency_ms"] == 123
    assert row["llm_content_metric_nested_p"] == 1

    # Named responses
    assert row["llm_foo"] == "X"
    assert row["llm_foo_metric_acc"] == 0.9
    assert row["llm_bar"] == "Y"
    assert row["llm_bar_metric_acc"] == 0.8

    # Aggregate metrics
    assert row["metric_overall"] == 0.95
    assert row["metric_sub_a"] == 1
    assert row["metric_sub_b"] == 2

    # Retry info and security
    assert row["retry_attempts"] == 2
    assert row["retry_max_attempts"] == 3
    assert json.loads(row["retry_history"]) == [{"e": "boom"}]
    assert row["security_level"] == "OFFICIAL"
