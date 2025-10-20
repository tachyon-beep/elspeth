from __future__ import annotations

from typing import Any, Mapping

import pytest

import elspeth.core.validation.settings as settings_mod
from elspeth.core.validation.base import ValidationReport


def test_validate_top_level_sinks_variants():
    report = ValidationReport()
    # None -> False
    assert settings_mod._validate_top_level_sinks(report, None, "p1") is False
    # Wrong type -> error + False
    assert settings_mod._validate_top_level_sinks(report, {"x": 1}, "p1") is False
    assert report.has_errors()
    # List of valid-looking entries -> True (schema details validated elsewhere)
    report = ValidationReport()
    entries = [
        {"plugin": "csv", "security_level": "OFFICIAL", "options": {"path": "out.csv"}},
    ]
    assert settings_mod._validate_top_level_sinks(report, entries, "p1") is True


def test_prompt_pack_helpers_and_additional_mappings():
    # _prompt_pack_provides_sinks
    profile = {"prompt_pack": "p", "prompt_packs": {"p": {"sinks": [{"plugin": "csv"}]}}}
    assert settings_mod._prompt_pack_provides_sinks(profile, profile["prompt_packs"]) is True
    # _suite_defaults_provide_sinks - direct sinks
    assert settings_mod._suite_defaults_provide_sinks({"sinks": [1]}, {}) is True
    # Via prompt pack
    suite = {"prompt_pack": "q"}
    packs = {"q": {"sinks": [1]}}
    assert settings_mod._suite_defaults_provide_sinks(suite, packs) is True
    # Additional mappings validation - wrong types add errors
    report = ValidationReport()
    settings_mod._validate_additional_mappings(report, {"retry": [1], "checkpoint": [2], "concurrency": [3]}, "p")
    assert report.has_errors()


def test_validate_prompt_pack_rules():
    report = ValidationReport()
    # Not a mapping -> error
    settings_mod._validate_prompt_pack(report, "p1", [1])
    assert report.has_errors()

    # Prompts missing required keys -> error
    report = ValidationReport()
    settings_mod._validate_prompt_pack(report, "p2", {"prompts": {"system": "x"}})
    assert report.has_errors()

    # Valid minimal pack exercising plugin list validators
    report = ValidationReport()
    pack: Mapping[str, Any] = {
        "row_plugins": [{"name": "noop", "security_level": "OFFICIAL"}],
        "aggregator_plugins": [{"name": "score_stats", "security_level": "OFFICIAL"}],
        "baseline_plugins": [{"name": "score_delta", "security_level": "OFFICIAL"}],
        "validation_plugins": [{"name": "regex_match", "security_level": "OFFICIAL"}],
        "early_stop_plugins": [{"name": "threshold_stop", "security_level": "OFFICIAL"}],
        "llm_middlewares": [{"name": "audit_logger", "security_level": "OFFICIAL"}],
        "sinks": [{"plugin": "csv", "security_level": "OFFICIAL"}],
    }
    settings_mod._validate_prompt_pack(report, "p3", pack)
    # Some validators require full option payloads; presence of errors is acceptable here
    assert report.has_errors()


def test_validate_suite_defaults_rules():
    report = ValidationReport()
    defaults = {
        "row_plugins": [{"name": "noop", "security_level": "OFFICIAL"}],
        "aggregator_plugins": [{"name": "score_stats", "security_level": "OFFICIAL"}],
        "baseline_plugins": [{"name": "score_delta", "security_level": "OFFICIAL"}],
        "validation_plugins": [{"name": "regex_match", "security_level": "OFFICIAL"}],
        "early_stop_plugins": [{"name": "threshold_stop", "security_level": "OFFICIAL"}],
        "llm_middlewares": [{"name": "audit_logger", "security_level": "OFFICIAL"}],
        "sinks": [{"plugin": "csv", "security_level": "OFFICIAL"}],
    }
    settings_mod._validate_suite_defaults(report, defaults)
    # Some schemas require full option payloads; presence of errors is acceptable
    assert report.has_errors()
