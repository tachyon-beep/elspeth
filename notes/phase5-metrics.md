# Phase 5 – Metrics & Statistical Plugins Recon

## Legacy Feature Inventory
- `old/experiment_stats.py` pulls in `numpy`, `pandas`, `scipy.stats`, optional `sklearn`, `pingouin`, and `matplotlib`.
- Core behaviours to preserve initially:
  - Extract per-row scores from `result['metrics']` or free-text rubric fields.
  - Compute aggregate statistics: mean/median, pass-rate thresholds, simple significance checks (t-test/Cliff's delta present in legacy but can be deferred).
  - Generate textual recommendations comparing variants against baseline.
- Heavy dependencies (`matplotlib`, `pingouin`, `sklearn`) were used for advanced charts/kappas; plan to gate them behind optional extras, not needed for first pass.

## Dependency Strategy
- Baseline implementation relies on `pandas`/`numpy` (already mandatory).
- Add optional extras group `stats` in `pyproject` to host `scipy`, `pingouin`, etc., but guard imports so plugins degrade gracefully.
- Unit tests for statistical plugins will stick to deterministic `numpy`/`scipy` paths; skip advanced checks if extras unmet.

## Test Fixtures
- Create synthetic experiment payload fixtures in `tests/fixtures/` representing:
  - Numeric score responses with metrics per criteria (e.g., `{"score": "4"}` or JSON payloads).
  - Mixed pass/fail flags to test thresholding.
  - Baseline vs variant datasets for aggregate comparisons.
- Integration test: run suite with mock row plugin & aggregator to ensure wiring.

## Plugin Output Contract
- Row plugins emit flattened metrics under `metrics` dict using snake_case keys (e.g., `score_summary`, `flag_missing`).
- Aggregation plugins return dictionaries keyed by metric name; will be nested under `payload['aggregates'][plugin.name]`.
- Recommendation plugin yields `{"recommendation": str, "rationale": {...}}` to support sinks.

## Open Questions
- Do we need percentile/rank outputs now or leave for later extras? (Tentatively Phase 6/7.)
- Exact schema for CLI surfacing of recommendations – likely via sink summary table.

## Implementation Notes
- Row plugin `score_extractor` emits `metrics['scores']` and optional `metrics['score_flags']` entries (threshold configurable per settings). Missing values default to `NaN` unless `allow_missing=True`.
- Aggregation plugins `score_stats` and `score_recommendation` aggregate statistics and craft summary messaging; baseline deltas supplied via `score_delta` plugin during suite comparisons.
- Defaults activated through `config/settings.yaml` prompt pack + suite defaults; CLI flag `--disable-metrics` strips the stack when experiments require raw outputs only.
