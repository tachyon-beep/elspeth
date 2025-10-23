# Master Example – Secure Evaluation Suite

This walkthrough bundles the features most teams care about into a single, reproducible
suite run. It shows how to validate incoming data, apply defensive middleware, generate
analytics, and publish signed evidence bundles ready for accreditation.

## Objectives

The master example exercises:

- Schema enforcement for datasource ↔ plugin compatibility (WP002).
- Classification and PII middleware (`classified_material`, `pii_shield`).
- Score extraction + statistics aggregators feeding analytics and Excel sinks.
- Signed artifact bundles with HMAC verification.
- CLI flags for deterministic reproduction and evidence capture.

All commands assume you work from the repository root.

## 1. Prerequisites

```bash
make bootstrap              # or scripts/bootstrap.sh
source .venv/bin/activate
pip install -e .[dev]
```

Export a signing key for the bundle. Any 32‑byte value works for HMAC. Store it in a
temporary file or environment variable so you can verify the signature later.

```bash
export ELSPETH_SIGNING_KEY_HMAC=$(openssl rand -hex 32)
```

## 2. Create a profile overlay

Copy the sample suite profile into a new overlay that enables middleware, analytics,
and bundle sinks. Place this file at `config/sample_suite/profiles/master_example.yaml`:

```yaml
defaults:
  prompt_pack: sample
  datasource:
    inherit: true
  llm:
    inherit: true
    middleware:
      - plugin: classified_material
        security_level: OFFICIAL
        determinism_level: high
        options:
          include_defaults: true
          severity_threshold: HIGH
          on_violation: abort
      - plugin: pii_shield
        security_level: OFFICIAL
        determinism_level: high
        options:
          include_defaults: true
          severity_threshold: MEDIUM
          checksum_validation: true
          redaction_salt_env: ELSPETH_SIGNING_KEY_HMAC
          on_violation: redact
  sinks:
    - plugin: analytics_report
      security_level: OFFICIAL
      determinism_level: guaranteed
      options:
        path: outputs/master_example/analytics.json
    - plugin: excel_workbook
      security_level: OFFICIAL
      determinism_level: guaranteed
      options:
        path: outputs/master_example/analytics.xlsx
    - plugin: visual_report
      security_level: OFFICIAL
      determinism_level: guaranteed
      options:
        output_dir: outputs/master_example/visuals
    - plugin: signed_artifact
      security_level: OFFICIAL
      determinism_level: guaranteed
      options:
        algorithm: hmac-sha256
        key_env: ELSPETH_SIGNING_KEY_HMAC
        output_dir: outputs/master_example/signed_bundle
  aggregator_plugins:
    - name: score_stats
      security_level: OFFICIAL
      determinism_level: guaranteed
    - name: score_recommendation
      security_level: OFFICIAL
      determinism_level: guaranteed
    - name: score_delta
      security_level: OFFICIAL
      determinism_level: guaranteed
profiles:
  master-example:
    inherit: defaults
```

Key points:

- The overlay inherits the datasource, prompts, and row plugins from `settings.yaml`.
- Middleware guards content before the mock LLM executes.
- Sinks emit JSON, Excel, PNG/HTML, and a signed bundle.
- Aggregators mirror the analytics suite configuration so reports are populated.

## 3. Validate schemas

Fail fast on schema drift before you run anything:

```bash
python -m elspeth.cli validate-schemas \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --profile master-example
```

You should see `Schema validation succeeded` with no warnings. If a plugin requires
columns that are missing from the CSV, the command exits non‑zero and tells you which
field to repair.

## 4. Run the suite with security middleware

Execute the full suite with analytics and signed bundle outputs:

```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --profile master-example \
  --reports-dir outputs/master_example/reports \
  --signed-bundle outputs/master_example/signed_bundle \
  --artifacts-dir outputs/master_example/artifacts \
  --head 0
```

Flags in play:

- `--reports-dir` generates consolidated JSON/Markdown/Excel artefacts.
- `--signed-bundle` instructs the `signed_artifact` sink to package manifests and
  signature JSON under the specified directory.
- `--artifacts-dir` collects per-run payloads, making triage easier when middleware blocks.
- `--head 0` runs the entire dataset instead of truncating rows.

Review the CLI output: each middleware invocation is logged, and the suite summary shows
aggregators plus sink outcomes.

## 5. Inspect outputs

```bash
tree -L 2 outputs/master_example
```

Expect to see:

- `reports/` – consolidated analytics (JSON, Markdown) and Excel workbook.
- `visuals/` – PNG/HTML charts from the visual analytics sink.
- `signed_bundle/` – manifest, signature, and payload tarball.
- `artifacts/` – per-experiment JSON payloads including middleware decision logs.

Open `outputs/master_example/reports/consolidated/analysis.md` to review the score
statistics and recommendation tables sourced from the aggregator plugins.

## 6. Verify the signed bundle

Verification uses the same key that generated the signature. For HMAC, the helper script
ensures the manifest matches the payload tarball.

```bash
python -m elspeth.tools.verify_signature \
  outputs/master_example/signed_bundle/signature.json \
  --key "$ELSPETH_SIGNING_KEY_HMAC"
```

You should see `Signature verification succeeded`. Store `signature.json`,
`manifest.json`, and the payload tarball together for accreditation reviewers.

## 7. Optional: container smoke test

If you package the runtime container, reuse the same profile to verify the image in CI:

```bash
docker run --rm \
  -e ELSPETH_SIGNING_KEY_HMAC="$ELSPETH_SIGNING_KEY_HMAC" \
  -v "$PWD":/workspace \
  --workdir /workspace \
  ghcr.io/<OWNER>/<REPO>:devtest \
  python -m elspeth.cli \
    --settings config/sample_suite/settings.yaml \
    --suite-root config/sample_suite \
    --profile master-example \
    --reports-dir outputs/master_example/reports \
    --signed-bundle outputs/master_example/signed_bundle \
    --head 1
```

Limit to `--head 1` inside CI to keep runtime short; the profile still exercises middleware
and sink wiring.

## 8. Cleanup

```bash
rm -rf outputs/master_example
unset ELSPETH_SIGNING_KEY_HMAC
```

## Next steps

- Integrate the `master-example` profile into your CI pipeline so every PR exercises
  security middleware and reporting sinks.
- Copy this profile as a starting point for production suites—swap the datasource plugin,
  LLM provider, or sinks while keeping the defensive middleware and bundling workflow.
- Review [`SECURITY_MIDDLEWARE_DEMOS.md`](SECURITY_MIDDLEWARE_DEMOS.md) for detailed
  tuning guidance and test prompts for `classified_material` and `pii_shield`.
- Track progress in [docs/roadmap/FEATURE_ROADMAP.md](../roadmap/FEATURE_ROADMAP.md)
  where this walkthrough is listed as a 1.0 milestone.
