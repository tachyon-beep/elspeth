from pathlib import Path

from elspeth.core.validation import validate_settings, validate_suite, ValidationReport
from elspeth.core import validation


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
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
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
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
              options:
                path: outputs/latest.csv
          llm_middlewares:
            - name: not_real
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
            options:
              path: data.csv
          llm:
            plugin: mock
          sinks:
            - plugin: csv
              options:
                path: outputs/latest.csv
        """,
    )
    report = validate_settings(config_path)
    report.raise_if_errors()


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
