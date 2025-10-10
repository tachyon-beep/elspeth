# Metrics Data Model

This note documents the contract for row-level metrics emitted during experiment
execution. The goal is to keep orchestration, plugins, sinks, early-stop
heuristics, and middleware aligned on the structure we pass around.

## Record Structure

Each successful row produced by `ExperimentRunner` has the following shape:

```json
{
  "row": { /* prompt context */ },
  "response": { /* first criteria response */ },
  "responses": {
    "<criteria>": {
      "content": "...",
      "metrics": {
        "score": 0.71,
        "comment": "...",
        "...": "..."
      },
      "retry": { "...": "..." }
    }
  },
  "metrics": {
    "score": 0.82,          // scalar copied from the most recent response
    "scores": {             // per-criteria numeric values from score_extractor
      "<criteria>": 0.71
    },
    "score_flags": {        // optional booleans keyed by criteria
      "<criteria>": true
    },
    "...": "..."            // other plugin derived metrics
  },
  "retry": { "...": "..." },
  "security_level": "..."   // optional
}
```

### Scalar vs. Per-Criteria Values

- LLM providers can return arbitrary keys inside `response["metrics"]`. We copy
  those into `record["metrics"]` verbatim; they should be treated as scalar data
  that applies to the whole row.
- Row plugins such as `score_extractor` MUST place per-criteria values inside
  nested maps under `record["metrics"]` (`scores`, `score_flags`, etc.). Names
  should follow snake_case; values must be JSON-serialisable.
- Consumers that target a specific criterion must traverse the nested map:
  `scores.analysis`, `score_flags.prioritization`, etc. Avoid using the top-level
  `score` key for per-criteria logic—the value reflects the most recent LLM
  response and is only present for convenience / backwards compatibility.

### Aggregates

Aggregator plugins are written against this contract:

- `score_stats` and derivatives look for `metrics[scores_field]`, defaulting to
  `metrics["scores"]`.
- Baseline comparison plugins pull per-criteria series via
  `_collect_scores_by_criterion`, which scans `record["metrics"]["scores"]`.
- Early-stop heuristics should read per-criteria values using the same paths.

## Downstream Consumers

- **CLI flattening:** `src/elspeth/cli.py` prefixes all entries in `record["metrics"]`
  with `metric_`, recursing through nested maps. Per-criteria values therefore
  appear as `metric_scores_<criteria>` columns in CSV preview/output.
- **CSV sink:** The default sink mirrors the CLI behaviour, writing the flattened
  structure into local CSV files.
- **Azure telemetry middleware:** Copies top-level metric keys into logged rows.
  Nested structures (e.g., `scores`) are emitted as dictionaries; consuming side
  should handle serialisation accordingly.

## Validation

Automated tests assert this contract:

- `tests/test_metrics_structure.py` confirms runner output contains both scalar
  and nested metrics, and that early-stop plugins can resolve nested paths.
- Existing metrics plugin tests cover extraction/aggregation against the
  `scores` map.

When adding new metrics plugins or sinks, ensure nested data stays under the
`record["metrics"]` namespace and update this document if the contract evolves.
