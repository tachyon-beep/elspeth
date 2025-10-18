# Ad‑hoc Job Configs

Elspeth can run simple ad‑hoc jobs that assemble a datasource, optional LLM transform (with prompts and middlewares), and one or more sinks, without a full suite configuration.

## Minimal schema

```yaml
job:
  security_level: OFFICIAL
  determinism_level: high
  datasource:
    plugin: csv_local
    security_level: OFFICIAL
    options: { path: data.csv, retain_local: true }
  llm:
    plugin: mock
    security_level: OFFICIAL
    options: { seed: 42 }
  prompt:
    system: "..."
    user: "..."
    fields: [A, B, C]
  llm_middlewares:
    - name: prompt_shield
      options: {}
  sinks:
    - plugin: csv
      security_level: OFFICIAL
      options: { path: outputs/job_results.csv }
```

- `llm` and `prompt` are optional together. If `llm` is omitted, rows are written as-is to sinks.
- `security_level`/`determinism_level` propagate through the job context.

## Run

```bash
python -m elspeth.cli --job-config config/jobs/sample_job.yaml --head 5 \
  --artifacts-dir artifacts --signed-bundle
```

This produces results and optional signed bundle under `artifacts/<timestamp>/`.

## Notes

- Middlewares are supported via the existing registry (`llm_middlewares`).
- Sinks use the standard sink registry and may include local CSV/Excel/ZIP, repository, blob, etc.
- Use `ELSPETH_SIGNING_KEY` (or `--signing-key-env`) to sign bundles.

