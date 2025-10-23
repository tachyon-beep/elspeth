This directory holds local input files for file-based datasources (e.g., CSVs).

Guidelines
- Do not commit sensitive data. The folder is configured to ignore all files by default.
- Point CSV datasources to `inputs/` via `base_path` or set `ELSPETH_INPUTS_DIR`.
- Example config:

```yaml
job:
  datasource:
    plugin: local_csv
    security_level: OFFICIAL
    options:
      path: sample.csv            # resolved under base_path
      base_path: inputs           # optional; or set ELSPETH_INPUTS_DIR
      retain_local: true
```

