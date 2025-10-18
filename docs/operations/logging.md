# Logging and Retention

Elspeth plugins emit structured JSON Lines under `logs/` for each run (one file per run):

- Location: `logs/run_YYYYMMDDTHHMMSSZ.jsonl`
- Contents: plugin initialization, lifecycle events, metrics, and errors
- Format: one JSON object per line (newline-delimited JSON)

Retention and cleanup
- Short‑lived CLI runs will accumulate files over time; rotate or clean as appropriate for your environment.
- Local development: remove historical run logs with:
  - `make clean-logs` — deletes `logs/run_*.jsonl`
- CI: prefer job artifacts export and ephemeral runners; no explicit cleanup needed.

Notes
- Logs may include run metadata (plugin names, paths) — avoid placing sensitive content into plugin names or paths.
- For centralized aggregation, ship JSONL via your preferred log forwarder.
