# Secure Azure Workflow Guide

Updated October 2025 — this walkthrough shows how to run a fully secured Elspeth suite
that ingests data from Azure Blob Storage, filters requests through the hardened
middleware stack, evaluates with Azure OpenAI, and publishes signed evidence to Azure
DevOps. It builds on the same conventions used by the master example profile.

```
Azure Blob CSV → Schema Validation → Security Middleware → Azure OpenAI
   → JSON validation → Aggregators → Analytics & Signed Bundle → Azure DevOps repo
```

---

## 1. Prerequisites

**Azure resources**

- Storage account + container holding the CSV you want to evaluate.
- Azure OpenAI resource (GPT-4/gpt‑4o or GPT‑3.5 deployment).
- Azure Content Safety resource in the same tenant/region.
- Azure DevOps organisation + repository for evidence drop-off.

**Local tooling**

```bash
make bootstrap
source .venv/bin/activate
pip install -e .[dev]
```

**Credential files & environment variables**

1. Blob store profile (`config/blob_store.yaml`) — populate from `blob_store.yaml.template`.
   ```yaml
   production:
     account_name: "mystorageaccount"
     container_name: "experiments"
     blob_path: "secure/input_data.csv"
     sas_token: "?sv=2025..."   # or omit to use DefaultAzureCredential
   ```

2. Azure OpenAI profile (`~/.elspeth/azure_openai.json`).
   ```json
   {
     "azure_endpoint": "https://your-resource.openai.azure.com",
     "api_key": "<AZURE_OPENAI_KEY>",
     "api_version": "2024-07-01-preview"
   }
   ```

3. Export runtime secrets:
   ```bash
   export AZURE_CONTENT_SAFETY_KEY="<content-safety-key>"
   export AZURE_DEVOPS_PAT="<devops PAT with Code (Read & Write)>"
   export ELSPETH_SIGNING_KEY_HMAC=$(openssl rand -hex 32)   # For signed bundle sink
   ```

---

## 2. Suite profile

Use `config/sample_suite/secure_azure_workflow.yaml` as a starting point or create a new
profile overlay (e.g. `config/sample_suite/profiles/secure-azure.yaml`). Below is the
Phase‑2 schema layout; adjust paths and deployments for your environment.

```yaml
defaults:
  datasource:
    plugin: azure_blob
    security_level: PROTECTED
    determinism_level: guaranteed
    options:
      config_path: config/blob_store.yaml
      profile: production
      retain_local: false

  llm:
    plugin: azure_openai
    security_level: PROTECTED
    determinism_level: high
    options:
      config: azure_openai_config   # ~/.elspeth/azure_openai.json
      deployment: gpt-4o
      temperature: 0.0
      max_tokens: 600
    middleware:
      - plugin: azure_content_safety
        security_level: PROTECTED
        determinism_level: guaranteed
        options:
          endpoint: "https://my-content-safety.cognitiveservices.azure.com"
          key_env: AZURE_CONTENT_SAFETY_KEY
          categories: ["Hate", "Violence", "SelfHarm", "Sexual"]
          severity_threshold: 4
          on_violation: abort
          on_error: skip
      - plugin: classified_material
        security_level: PROTECTED
        determinism_level: guaranteed
        options:
          include_defaults: true
          severity_scoring: true
          min_severity: HIGH
          check_code_fences: true
          on_violation: abort
      - plugin: pii_shield
        security_level: PROTECTED
        determinism_level: guaranteed
        options:
          include_defaults: true
          severity_scoring: true
          min_severity: MEDIUM
          checksum_validation: true
          context_boosting: true
          context_suppression: true
          blind_review_mode: false
          redaction_salt_env: ELSPETH_SIGNING_KEY_HMAC
          on_violation: abort
      - plugin: audit_logger
        security_level: PROTECTED
        determinism_level: guaranteed
        options:
          include_prompts: true
          channel: elspeth.secure.audit
      - plugin: azure_environment   # Optional, logs metrics when running inside Azure ML
        security_level: PROTECTED
        determinism_level: guaranteed

  prompt:
    system: |
      You are a helpful assistant analysing customer feedback.
      Always respond with valid JSON containing sentiment, key themes, priority,
      and a recommended action.
    template: |
      Customer ID: {{ customer_id }}
      Feedback: {{ feedback_text }}
      Category: {{ category }}

  plugins:
    row:
      - plugin: score_extractor
        options:
          key: sentiment_score
          parse_json_content: true
          allow_missing: false
    validation:
      - plugin: json
        options:
          ensure_object: true
    aggregators:
      - plugin: score_stats
      - plugin: score_recommendation
      - plugin: cost_summary
      - plugin: latency_summary

  sinks:
    - plugin: csv
      security_level: PROTECTED
      determinism_level: guaranteed
      options:
        path: outputs/secure_azure/results.csv
        sanitize_formulas: true
        overwrite: true
    - plugin: analytics_report
      security_level: PROTECTED
      determinism_level: guaranteed
      options:
        base_path: outputs/secure_azure/analytics
        formats: ["json", "markdown"]
    - plugin: visual_report
      security_level: PROTECTED
      determinism_level: guaranteed
      options:
        output_dir: outputs/secure_azure/visuals
        formats: ["png", "html"]
    - plugin: signed_artifact
      security_level: PROTECTED
      determinism_level: guaranteed
      options:
        algorithm: hmac-sha256
        key_env: ELSPETH_SIGNING_KEY_HMAC
        output_dir: outputs/secure_azure/signed_bundle
    - plugin: azure_devops_repo
      security_level: PROTECTED
      determinism_level: guaranteed
      options:
        organization: myorg
        project: llm-experiments
        repo: experiment-results
        branch: main
        path_template: workflows/{{ suite_name }}/{{ experiment_name }}/{{ timestamp }}
        token_env: AZURE_DEVOPS_PAT
        dry_run: false
```

> ℹ️ For an in-depth look at the security middleware options refer to
> [`SECURITY_MIDDLEWARE_DEMOS.md`](SECURITY_MIDDLEWARE_DEMOS.md).

---

## 3. Validate schemas

Validate the datasource ↔ plugin compatibility before running the suite:

```bash
python -m elspeth.cli validate-schemas \
  --settings config/sample_suite/secure_azure_workflow.yaml \
  --suite-root config/sample_suite \
  --profile secure-azure
```

The command fails fast if required columns are missing or schema types drift.

---

## 4. Run the suite

```bash
python -m elspeth.cli \
  --settings config/sample_suite/secure_azure_workflow.yaml \
  --suite-root config/sample_suite \
  --profile secure-azure \
  --reports-dir outputs/secure_azure/reports \
  --signed-bundle outputs/secure_azure/signed_bundle \
  --artifacts-dir outputs/secure_azure/artifacts \
  --head 0
```

- `--reports-dir` stores consolidated analytics (JSON + Markdown + Excel).
- `--signed-bundle` collects manifest + signature JSON for accreditation.
- `--artifacts-dir` keeps per-experiment payloads and middleware decision logs.
- `--head 0` processes the full dataset instead of sampling.

The CLI output lists each middleware decision, sink write, and Azure DevOps commit.

---

## 5. Review outputs

```bash
tree -L 2 outputs/secure_azure
```

- `reports/` – consolidated analytics, Markdown summary, Excel workbook.
- `visuals/` – PNG + HTML charts (self-contained, safe for evidence bundles).
- `signed_bundle/` – `manifest.json`, `payload.tar`, and `signature.json`.
- `artifacts/` – raw experiment payloads for debugging.

Verify the signed bundle before handing it to auditors:

```bash
python -m elspeth.tools.verify_signature \
  outputs/secure_azure/signed_bundle/signature.json \
  --key "$ELSPETH_SIGNING_KEY_HMAC"
```

Push confirmation appears in Azure DevOps under the path template defined in the sink.

---

## 6. Integrate with CI/CD

- Run the suite inside the container build job as a smoke test (use `--head 1`).
- Publish PR preview images so reviewers can test the profile without merging
  (see the upcoming `docs/operations/ci-preview-images.md`).
- Gate releases on signature verification: add a job that runs `verify_signature` against
  the produced bundle before publishing artefacts.

---

## 7. Troubleshooting

| Symptom | Root cause | Fix |
| --- | --- | --- |
| `Azure Blob datasource endpoint validation failed` | Blob URL outside approved domain or missing `retain_local` flag | Update `config/blob_store.yaml` with the correct account URL and set `retain_local: false` if you don’t need a local copy. |
| `azure_content_safety` timeouts | Region mismatch or throttling | Align the Content Safety region with your OpenAI deployment and consider `on_error: skip` for transient failures. |
| `azure_devops_repo` returns 401 | Token missing Code (Read & Write) scope | Regenerate the PAT with repository write permissions and re-export `AZURE_DEVOPS_PAT`. |
| `Signed bundle verification failed` | Forgot to set `ELSPETH_SIGNING_KEY_HMAC` in run & verify steps | Ensure the same key is present when running the suite and verifying the signature; store it securely in CI secrets. |

---

## Next steps

- Extend the profile with additional sinks (e.g., Azure Blob, SharePoint) once approved.
- Use the master example as a template for other environments and keep middleware tuning in
  sync with [`SECURITY_MIDDLEWARE_DEMOS.md`](SECURITY_MIDDLEWARE_DEMOS.md).
- Document runbooks for operations teams so they can reproduce evidence on demand.

