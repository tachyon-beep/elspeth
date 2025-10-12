import json

import pandas as pd

import elspeth.cli as cli


def test_cli_single_run_executes_real_config(tmp_path):
    data_path = tmp_path / "colours.csv"
    data_path.write_text("colour\nred\nblue\n", encoding="utf-8")

    bundle_root = tmp_path / "bundles"
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        f"""
integration:
  datasource:
    plugin: local_csv
    security_level: official
    options:
      path: "{data_path.as_posix()}"
  llm:
    plugin: mock
    security_level: official
    options:
      seed: 101
  sinks:
    - plugin: local_bundle
      security_level: official
      options:
        base_path: "{bundle_root.as_posix()}"
        bundle_name: "cli_run"
        timestamped: false
        write_json: true
        write_csv: true
  prompts:
    system: "You speak for the test harness."
    user: "Describe {{ colour }} in one word."
  prompt_fields:
    - colour
  aggregator_plugins:
    - name: prompt_variants
      security_level: official
      options:
        prompt_template: |
          Rewrite the original prompt while keeping tokens {{ placeholder_tokens | join(', ') }}.
          Base:
          {{ user_prompt_template }}
        count: 2
        max_attempts: 1
        variant_llm:
          plugin: mock
          security_level: official
          options:
            seed: 202
""",
        encoding="utf-8",
    )

    cli.main(
        [
            "--settings",
            str(settings_path),
            "--profile",
            "integration",
            "--single-run",
            "--head",
            "0",
        ]
    )

    manifest_path = bundle_root / "cli_run" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["rows"] == 2
    assert "aggregates" in manifest
    variants = manifest["aggregates"]["prompt_variants"]["variants"]
    assert len(variants) == 2

    csv_path = bundle_root / "cli_run" / "results.csv"
    df = pd.read_csv(csv_path)
    assert list(df["colour"]) == ["red", "blue"]
    assert df["llm_content"].str.contains("Describe").all()
