from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from elspeth.core.cli.suite import assemble_suite_defaults, maybe_write_artifacts_suite


def test_maybe_write_artifacts_suite_writes(tmp_path: Path):
    args = argparse.Namespace(artifacts_dir=tmp_path / "artifacts", signed_bundle=False, signing_key_env="ELSPETH_SIGNING_KEY")
    settings = argparse.Namespace(config_path=tmp_path / "settings.yaml")
    settings.config_path.write_text("key: value\n", encoding="utf-8")
    suite = object()
    results = {"exp": {"payload": {"results": []}}}

    maybe_write_artifacts_suite(args, settings, suite, results)

    out_dir = next((tmp_path / "artifacts").glob("*/"))
    assert (out_dir / "suite.json").exists()
    assert (out_dir / "settings.yaml").exists()


def test_assemble_suite_defaults_merges_optional_and_mappings(tmp_path: Path):
    orchestrator_config = argparse.Namespace(
        llm_prompt={"system": "S", "user": "U"},
        prompt_fields=["id"],
        criteria=[{"name": "c"}],
        row_plugin_defs=[{"name": "row"}],
        aggregator_plugin_defs=[{"name": "agg"}],
        baseline_plugin_defs=[{"name": "base"}],
        validation_plugin_defs=[{"name": "val"}],
        sink_defs=[{"plugin": "csv"}],
        llm_middleware_defs=[{"name": "mw"}],
        prompt_defaults={"k": "v"},
        concurrency_config={"max_workers": 2},
        early_stop_plugin_defs=[{"name": "early"}],
        early_stop_config={"enabled": True},
        prompt_pack="p1",
    )
    settings = argparse.Namespace(
        orchestrator_config=orchestrator_config,
        prompt_packs={"p1": {}},
        suite_defaults={
            "row_plugins": [{"name": "row_s"}],
            "aggregator_plugins": [{"name": "agg_s"}],
            "baseline_plugins": [{"name": "base_s"}],
            "validation_plugins": [{"name": "val_s"}],
            "llm_middlewares": [{"name": "mw_s"}],
            "sinks": [{"plugin": "csv"}],
            "prompt_pack": "p1",
            "rate_limiter": {"plugin": "rate"},
            "cost_tracker": {"plugin": "cost"},
        },
        rate_limiter=argparse.Namespace(tag="rate"),
        cost_tracker=argparse.Namespace(tag="cost"),
    )

    defaults = assemble_suite_defaults(settings)
    # Ensure keys present via optional overrides and mappings
    assert defaults["prompt_system"] == "S"
    assert defaults["prompt_template"] == "U"
    assert defaults["row_plugin_defs"]
    assert defaults["aggregator_plugin_defs"]
    assert defaults["baseline_plugin_defs"]
    assert defaults["validation_plugin_defs"]
    assert defaults["sink_defs"]
    assert defaults["llm_middleware_defs"]
    assert defaults["rate_limiter"]
    assert defaults["cost_tracker"]

