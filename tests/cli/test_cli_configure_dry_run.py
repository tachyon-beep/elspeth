from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elspeth import cli


@dataclass
class _Cfg:
    sink_defs: list[dict[str, Any]]


class _Settings:
    def __init__(self) -> None:
        self.sinks = []
        self.orchestrator_config = _Cfg(sink_defs=[
            {"plugin": "github_repo", "options": {}},
            {"plugin": "other", "options": {"dry_run": True}, "security_level": "OFFICIAL"},
        ])
        self.suite_defaults = {"sinks": [
            {"plugin": "azure_devops_repo", "options": {}},
        ]}
        self.prompt_packs = {
            "p": {"sinks": [{"plugin": "github_repo", "options": {}}]},
        }


class _DummySink:
    def __init__(self) -> None:
        self.dry_run = True


def test_configure_sink_dry_run_toggles_everywhere():
    settings = _Settings()
    s = _DummySink()
    settings.sinks = [s]

    # Enable live outputs -> dry_run False
    cli._configure_sink_dry_run(settings, enable_live=True)
    assert s.dry_run is False
    # Inlined defs updated
    for defs in (
        settings.orchestrator_config.sink_defs,
        settings.suite_defaults["sinks"],
        settings.prompt_packs["p"]["sinks"],
    ):
        for entry in defs:
            assert entry["options"]["dry_run"] is False
            # security_level/other fields preserved when present
            if entry.get("plugin") == "other":
                assert entry.get("security_level") == "OFFICIAL"

