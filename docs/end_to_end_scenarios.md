# End-to-End Scenario Coverage

This document records the high-value integration scenarios covered by the non-Azure tests. Each scenario exercises a representative pipeline across prompts, datasources, plugins, and sinks so future contributors can reuse or extend the patterns.

## Scenario 1 – Local CSV Pipeline (`tests/test_scenarios.py::test_end_to_end_local_pipeline`)

- **Goal:** Validate a single-experiment `ExperimentRunner` flow that consumes tabular data, invokes the mock LLM, derives metrics, validates outputs, and persists artifacts locally.
- **Inputs:** In-memory `pandas.DataFrame` with `APPID` and `value` columns.
- **LLM:** `MockLLMClient(seed=7)` ensures deterministic scores and response text.
- **Plugins:**
  - Row plugin – `score_extractor` (scrapes numeric scores out of mock metrics).
  - Aggregator – `score_stats` (summaries of per-row scores).
  - Validation – `regex_match` with inline DOTALL pattern to ensure the mock response format was preserved.
- **Sinks:**
  - `LocalBundleSink` writes `manifest.json`, `results.json`, and CSV snapshots to `tmp_path / bundles`, recording sanitisation metadata.
  - `CsvResultSink` mirrors the run output to `tmp_path / results.csv` with sanitisation enabled.
- **Assertions:**
  - Runner returns per-row results and aggregates the expected number of records.
  - Output CSV exists, passes the `assert_sanitized_artifact` guard, and the local bundle manifest captures row counts, columns, and sanitisation metadata.

## Scenario 2 – Suite Runner with Prompt Packs (`tests/test_scenarios.py::test_suite_runner_end_to_end_without_azure`)

- **Goal:** Exercise the `ExperimentSuiteRunner` orchestration path where defaults, prompt packs, and plugin definitions are merged before execution.
- **Suite Layout:** Two experiments (`baseline`, `variant`) created dynamically with dedicated prompt packs (`base_pack` and `variant_pack`).
- **Defaults:** Provide shared prompts, plugin definitions, and a `LocalBundle` sink pointing to `tmp_path / suite_bundles`.
- **Plugins:** Same trio as Scenario 1, ensuring statistics and validation occur for both experiments.
- **Execution:** `MockLLMClient(seed=13)` processes two input rows; the runner produces payloads for baseline and variant, and the local bundle sink emits a manifest (timestamped directory).
- **Assertions:**
  - Both experiments return aggregated scores matching input size.
  - At least one manifest is written under `suite_bundles/**/manifest.json`, confirming the sink executed with the merged defaults and recorded sanitisation metadata.

## Usage Notes

- These scenarios avoid Azure-specific dependencies to keep CI fast and deterministic.
- The pattern for registration (`plugin_registry.create_*`) allows you to swap in custom plugins while reusing the same assertion scaffold.
- When extending scenarios, prefer verifying behavioural signals (e.g., manifest row counts, aggregated statistics) rather than brittle path names—bundle directories include timestamps by default.

Refer back to this file when adding new end-to-end regressions so we maintain a curated set of representative flows.
