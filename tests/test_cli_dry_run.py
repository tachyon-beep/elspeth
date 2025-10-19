from __future__ import annotations

import argparse
from types import SimpleNamespace

import elspeth.cli as cli


class _DummyValidation:
    warnings: list = []

    def raise_if_errors(self):
        return None


def _make_settings():
    # One sink object with a dry_run attribute we can toggle
    sink_obj = SimpleNamespace(dry_run=None)

    orchestrator_config = SimpleNamespace(
        sink_defs=[
            {
                "plugin": "github_repo",
                "options": {"owner": "o", "repo": "r"},
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
            }
        ]
    )
    suite_defaults = {
        "sinks": [
            {"plugin": "csv", "options": {"path": "out.csv", "dry_run": True}},
        ]
    }
    prompt_packs = {
        "pack": {
            "sinks": [
                {"plugin": "azure_devops_repo", "options": {"org": "x", "proj": "y"}},
            ]
        }
    }
    return SimpleNamespace(
        datasource=SimpleNamespace(),
        llm=SimpleNamespace(),
        sinks=[sink_obj],
        orchestrator_config=orchestrator_config,
        suite_defaults=suite_defaults,
        rate_limiter=None,
        cost_tracker=None,
        prompt_packs=prompt_packs,
        prompt_pack=None,
        suite_root=None,
        config_path=None,
    )


def _load_args(live_outputs: bool):
    return argparse.Namespace(
        settings="settings.yaml",
        profile="default",
        head=0,
        output_csv=None,
        log_level="ERROR",
        suite_root=None,
        single_run=True,
        live_outputs=live_outputs,
        disable_metrics=False,
    )


def test_configure_sink_dry_run_enables_and_disables(monkeypatch):
    settings = _make_settings()
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: _DummyValidation())
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)

    # Case 1: live_outputs=False -> dry_run True
    args = _load_args(live_outputs=False)
    out = cli._load_settings_from_args(args)
    assert out.sinks[0].dry_run is True
    # config.sink_defs gets dry_run injected for github_repo
    assert any(d.get("options", {}).get("dry_run") is True for d in out.orchestrator_config.sink_defs)
    # suite_defaults['sinks'] options updated
    assert out.suite_defaults["sinks"][0]["options"]["dry_run"] is True
    # prompt_packs sinks updated
    assert out.prompt_packs["pack"]["sinks"][0]["options"]["dry_run"] is True

    # Case 2: live_outputs=True -> dry_run False
    settings2 = _make_settings()
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings2)
    args2 = _load_args(live_outputs=True)
    out2 = cli._load_settings_from_args(args2)
    assert out2.sinks[0].dry_run is False
    assert any(d.get("options", {}).get("dry_run") is False for d in out2.orchestrator_config.sink_defs)
    assert out2.suite_defaults["sinks"][0]["options"]["dry_run"] is False
    assert out2.prompt_packs["pack"]["sinks"][0]["options"]["dry_run"] is False

