# Threat Traceability Diagram

```penguin
diagram "Threat ↔ Control Mapping" {
  direction: right

  group "Threats" {
    node injection "Prompt Injection\n(untrusted fields)"
    node dataset "Poisoned Dataset\n(CSV/Blob tampering)"
    node creds "Credential Exposure\n(SAS / PAT leaks)"
    node spreadsheet "Spreadsheet Formula Injection"
    node abuse "LLM Abuse / Cost Overrun"
  }

  group "Controls" {
    node promptShield "Prompt Shield + Content Safety\n(src/elspeth/plugins/llms/middleware.py:91,206)"
    node validation "Prompt Validation & StrictUndefined\n(src/elspeth/core/prompts/engine.py:33)"
    node datasource "Security-level Tagging + on_error policies\n(src/elspeth/plugins/datasources/csv_blob.py:35)"
    node signing "Signed Artifact Bundles\n(src/elspeth/plugins/outputs/signed.py:37)"
    node sanitize "CSV/Excel Sanitisation\n(src/elspeth/plugins/outputs/_sanitize.py:18)"
    node secrets "Environment-driven Secrets + DefaultAzureCredential\n(src/elspeth/plugins/outputs/repository.py:149)"
    node rate "Rate/Credit Controls\n(src/elspeth/core/controls/rate_limit.py:61,126)"
    node cost "Cost Tracker + Retry Logs\n(src/elspeth/core/controls/cost_tracker.py:36)"
  }

  injection -> promptShield
  injection -> validation
  dataset -> datasource
  dataset -> validation
  creds -> secrets
  creds -> signing
  spreadsheet -> sanitize
  abuse -> rate
  abuse -> cost
  dataset -> signing
}
```

- Each threat vector is mapped to concrete mitigations with code references, supporting accreditation traceability.
- For comprehensive evidence, pair this diagram with configuration snippets demonstrating that the relevant middleware/plugins are enabled for regulated suites (`config/sample_suite/prompt_shield_demo/config.json:8`, `config/sample_suite/slow_rate_limit_demo/config.json:17`).
