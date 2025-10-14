# Configuration Migration Cheat Sheet

| Legacy Key | New Key | Notes |
|------------|---------|-------|
| `promptPack` | `prompt_pack` | Single prompt pack selection on settings or experiments |
| `promptPacks` | `prompt_packs` | Mapping of named packs with prompts/plugins |
| `middlewares` | `llm_middlewares` | Explicit LLM middleware definitions |
| `plugins` (suite defaults) | `row_plugins` / `aggregator_plugins` / `baseline_plugins` | Break out plugin families explicitly |
| `runner.retry` | `retry` | Retry configuration moved under top-level settings/experiment block |
| `runner.checkpoint` | `checkpoint` | Checkpoint configuration promoted to top-level |
| `runner.earlyStop` | `early_stop` | Configure early-stop heuristics at settings/experiment level |
| `runner.concurrency` | `concurrency` | Enable threaded execution and backlog thresholds |
| `runner.checkpoint.path` | `checkpoint.path` | Persist processed identifiers to resume runs |
| `runner.checkpoint.field` | `checkpoint.field` | Field used to track processed IDs |

When modernising older configs:

1. Rename keys per the table above.
2. Ensure any prompt pack referenced via `prompt_pack` is defined in `prompt_packs`.
3. If legacy middleware names were used, verify a matching plugin exists (run `elspeth list middlewares` or check `src/elspeth/plugins/llms/`).
4. Run `elspeth validate --settings <file>` to surface actionable error messages.
<!-- UPDATE 2025-10-12: Legacy `earlyStop` arrays map to `early_stop_plugins` with `threshold` plugin definitions; helper `normalize_early_stop_definitions` handles migration in code. -->

## Update History
- 2025-10-12 – Added concurrency and checkpoint key mappings plus guidance on early-stop normalisation.
