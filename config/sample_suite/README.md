# Sample Experiment Suite

This suite demonstrates the full plugin stack without external dependencies.
It uses the local CSV datasource and the mock LLM client to produce deterministic
outputs that flow through the metrics and CSV sinks.

## Contents
- `data/sample_input.csv` – input dataset with three example applications.
- `baseline/`, `variant_prompt/` – experiments sharing the `sample` prompt pack
  while varying prompts and baseline comparisons.
- `slow_rate_limit_demo/` – variant with an intentionally slow fixed-window rate
  limiter and disabled concurrency to highlight throttling behaviour.
- `early_stop_threshold/` – stops after two rows once the analysis criteria
  reaches 0.63 (`metric: scores.analysis`) and a guardrail on overall score
  kicks in, demonstrating multi-plugin early-stop configurations.
- `early_stop_fast_exit/` – exits immediately when the first row crosses 0.55
  showcase aggressive cost saving.
- `prompt_shield_demo/` – demonstrates prompt shield middleware masking terms
  such as "classified" before the request reaches the LLM.
- `azure_content_safety_demo/` – stub showing how to configure the
  `azure_content_safety` middleware (disabled until you supply a real
  endpoint and key).
- Analytics plugins such as `score_cliffs_delta`, `score_assumptions`, and
  `score_practical` can be enabled per experiment to inspect effect sizes,
  diagnostic checks, and practical impact. Pair with the `analytics_report`
  sink to capture JSON/Markdown summaries of each run.
- `azure_telemetry/` – disabled example showing how to opt an experiment into
  the Azure environment middleware; enable it only when running inside Azure ML.
- `settings.yaml` – CLI profile wiring the local datasource, mock LLM, metrics,
  and sinks.

## Running the Suite
1. Activate the project virtual environment
   ```bash
   source .venv/bin/activate
   pip install -e .[dev]
   ```
2. Execute the suite via the CLI
   ```bash
   python -m elspeth.cli \
     --settings config/sample_suite/settings.yaml \
     --suite-root config/sample_suite \
     --head 0 \
     --live-outputs
   ```
3. Results are written to `outputs/sample_suite/<experiment>_latest_results.csv`
   alongside aggregates and baseline comparisons in the payload metadata.

The mock LLM echoes the prompt content and generates deterministic `score`
values so you can inspect metrics without calling a live endpoint. Swap the
`llm` plugin in `settings.yaml` with `azure_openai`, enable the example
`azure_telemetry` experiment (and install `.[azure]`) to exercise Azure ML
telemetry end-to-end.
