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

When modernising older configs:

1. Rename keys per the table above.
2. Ensure any prompt pack referenced via `prompt_pack` is defined in `prompt_packs`.
3. If legacy middleware names were used, verify a matching plugin exists (run `dmp list middlewares` or check `dmp/plugins/llms/`).
4. Run `dmp validate --settings <file>` to surface actionable error messages.
