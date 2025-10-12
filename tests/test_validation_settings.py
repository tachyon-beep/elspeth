from pathlib import Path

from elspeth.core.validation import validate_settings, validate_suite


def write_settings(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_validate_settings_missing_required_fields(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          llm:
            plugin: mock
            security_level: official
          sinks: []
        """,
    )
    report = validate_settings(config_path)
    assert report.has_errors()


def test_validate_settings_unknown_prompt_pack(tmp_path):
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: official
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: official
          sinks:
            - plugin: csv
              security_level: official
              options:
                path: outputs/latest.csv
          prompt_pack: imaginary
        """,
        encoding="utf-8",
    )

    report = validate_settings(config_path)
    assert report.has_errors()
    messages = [msg.format() for msg in report.errors]
    assert any("Unknown prompt pack 'imaginary'" in msg for msg in messages)


def test_validate_settings_unknown_middleware(tmp_path):
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: official
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: official
          sinks:
            - plugin: csv
              security_level: official
              options:
                path: outputs/latest.csv
          llm_middlewares:
            - name: not_real
              security_level: official
        """,
        encoding="utf-8",
    )

    report = validate_settings(config_path)
    assert report.has_errors()
    messages = [msg.format() for msg in report.errors]
    assert any("Unknown LLM middleware 'not_real'" in msg for msg in messages)


def test_validate_settings_valid_configuration(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            security_level: official
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: official
          sinks:
            - plugin: csv
              security_level: official
              options:
                path: outputs/latest.csv
        """,
    )
    report = validate_settings(config_path)
    report.raise_if_errors()


def test_validate_settings_requires_sink_security_level(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            security_level: official
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: official
          sinks:
            - plugin: csv
              options:
                path: outputs/latest.csv
        """,
    )
    report = validate_settings(config_path)
    assert report.has_errors()
    messages = [msg.format() for msg in report.errors]
    assert any("security_level" in message for message in messages)


def test_validate_suite_detects_missing_prompts(tmp_path):
    suite_root = tmp_path / "suite"
    exp = suite_root / "experiment"
    exp.mkdir(parents=True)
    (exp / "config.json").write_text('{"name": "experiment", "temperature": 0.0, "max_tokens": 10}', encoding="utf-8")
    result = validate_suite(suite_root)
    assert result.report.has_errors()


def test_validate_suite_success(tmp_path):
    suite_root = tmp_path / "suite"
    exp = suite_root / "baseline"
    exp.mkdir(parents=True)
    (exp / "config.json").write_text(
        '{"name": "baseline", "temperature": 0.0, "max_tokens": 10, "is_baseline": true}',
        encoding="utf-8",
    )
    (exp / "system_prompt.md").write_text("System", encoding="utf-8")
    (exp / "user_prompt.md").write_text("Prompt {APPID}", encoding="utf-8")
    result = validate_suite(suite_root)
    result.report.raise_if_errors()
    assert result.preflight["experiment_count"] == 1


def test_validate_suite_records_warnings(tmp_path):
    suite_root = tmp_path / "suite"
    baseline = suite_root / "baseline"
    variant = suite_root / "variant"
    baseline.mkdir(parents=True)
    variant.mkdir(parents=True)

    (baseline / "config.json").write_text(
        '{"name": "baseline", "temperature": 0.5, "max_tokens": 100, "is_baseline": true}',
        encoding="utf-8",
    )
    (baseline / "system_prompt.md").write_text("System", encoding="utf-8")
    (baseline / "user_prompt.md").write_text("Prompt", encoding="utf-8")

    (variant / "config.json").write_text(
        '{"name": "variant", "temperature": 2.2, "max_tokens": 5000}',
        encoding="utf-8",
    )
    (variant / "system_prompt.md").write_text("System", encoding="utf-8")
    (variant / "user_prompt.md").write_text("Prompt", encoding="utf-8")

    report = validate_suite(suite_root)

    assert not report.report.has_errors()
    warning_messages = [msg.format() for msg in report.report.warnings]
    assert any("High temperature" in message for message in warning_messages)
    assert any("High max_tokens" in message for message in warning_messages)
    assert report.preflight["warnings"]


def test_validate_suite_duplicate_name_detected(tmp_path):
    suite_root = tmp_path / "suite"
    first = suite_root / "exp_a"
    second = suite_root / "exp_b"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    (first / "config.json").write_text(
        '{"name": "exp", "temperature": 0.1, "max_tokens": 20, "is_baseline": true}',
        encoding="utf-8",
    )
    (first / "system_prompt.md").write_text("System", encoding="utf-8")
    (first / "user_prompt.md").write_text("Prompt", encoding="utf-8")

    (second / "config.json").write_text(
        '{"name": "exp", "temperature": 0.1, "max_tokens": 20}',
        encoding="utf-8",
    )
    (second / "system_prompt.md").write_text("System", encoding="utf-8")
    (second / "user_prompt.md").write_text("Prompt", encoding="utf-8")

    result = validate_suite(suite_root)

    messages = [msg.format() for msg in result.report.errors]
    assert any("Duplicate experiment name" in message for message in messages)


def test_validate_settings_requires_sink_list(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            plugin: csv
        """,
    )
    report = validate_settings(config_path)
    messages = [msg.format() for msg in report.errors]
    assert any("sinks" in message for message in messages)


def test_validate_settings_prompt_pack_requires_user_prompt(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
              options:
                path: outputs/results.csv
          prompt_packs:
            bad:
              prompts:
                system: System prompt
        """,
    )
    report = validate_settings(config_path)
    messages = [msg.format() for msg in report.errors]
    assert any("Prompt pack prompts must include" in message for message in messages)


def test_validate_settings_prompt_pack_sinks_must_be_list(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
              options:
                path: outputs/results.csv
          prompt_packs:
            bad:
              prompts:
                system: Sys
                user: User
              sinks:
                plugin: csv
        """,
    )
    report = validate_settings(config_path)
    messages = [msg.format() for msg in report.errors]
    assert any("prompt_pack:bad.sink" in message and "Expected a list" in message for message in messages)


def test_validate_settings_suite_defaults_invalid_sink(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
              options:
                path: outputs/results.csv
          suite_defaults:
            sinks:
              - plugin: csv
                options: {}
        """,
    )
    report = validate_settings(config_path)
    messages = [msg.format() for msg in report.errors]
    assert any("suite_defaults.sink" in message for message in messages)


def test_validate_settings_suite_defaults_rate_limiter_error(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
              options:
                path: outputs/results.csv
          suite_defaults:
            rate_limiter:
              plugin: missing
        """,
    )
    report = validate_settings(config_path)
    messages = [msg.format() for msg in report.errors]
    assert any("suite_defaults.rate_limiter" in message for message in messages)


def test_validate_settings_prompt_pack_invalid_sink_list(tmp_path):
    config_path = tmp_path / "settings.yaml"
    write_settings(
        config_path,
        """
        default:
          datasource:
            plugin: local_csv
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
              options:
                path: outputs/results.csv
          prompt_packs:
            invalid_pack:
              prompts:
                system: Sys
                user: User
              sinks:
                plugin: csv
        """,
    )
    report = validate_settings(config_path)
    messages = [msg.format() for msg in report.errors]
    assert any("prompt_pack:invalid_pack.sink" in message and "Expected a list" in message for message in messages)
