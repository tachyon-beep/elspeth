# Phase 6 – Output & Archival Sinks Recon

## Target Surfaces
- **Azure Blob Storage** sink (existing) requires resumable uploads, metadata tagging, and manifest schema upgrades; expose options for container/blob path templates, credential overrides, `on_error`, and metadata.
- **Azure DevOps Git sink** should support creating/updating files via REST, branch selection, commit messages, optional PR creation (later), and dry-run logging. Options include organization, project, repository, branch, path template, token env, `on_error`.
- **Excel/ZIP archival sinks** produce `.xlsx` workbooks and zipped bundles including results, manifest, and optional CSV. Options: base path, bundle name, timestamp toggle, sheet names, `on_error`. ✅ Implemented via `excel_workbook` and `zip_bundle` sinks with validation and tests.
- **Telemetry middleware** for Azure ML should log configuration diffs, experiment metrics, preflight summaries, leveraging `Run.log_row/log_table` with option schema (enable flags, prompt logging, severity threshold). ✅ Extended `azure_environment` middleware with config toggles, severity threshold, and graceful `on_error` handling.
- **Composable artifacts** introduce two parent types:
  - **file** – a complete dataset encoded as a standard file (CSV, XLSX, ZIP, PNG, etc.) with MIME/type metadata, suitable for chaining sinks (e.g., CSV ➜ ZIP ➜ Blob).
  - **data** – structured rows/frames that conform to a declared schema (same schema used by sources). Sinks or middleware consuming `data` can operate without first serialising to a file.
  - Each sink will declare produced artifact types and optional inputs so the orchestrator can resolve dependencies; default behaviour remains single-sink execution when no chaining is configured.
  - Artifact metadata must include: `type` (e.g. `file/csv`, `file/xlsx`, `data/application/json`), `schema_id` (for `data` artifacts), `path` (absolute or relative) or in-memory payload reference, and originating sink ID for traceability.
  - Temp storage policy: file artifacts default to temp directory managed by orchestrator; sinks can opt-in to `persist` flag when they own the lifecycle.
  - Error handling: upstream sinks must expose cleanup hooks so downstream failures can remove orphaned artifacts when `on_error=abort`.
- **Artifact pipeline**: Suite/runner now resolves sink dependency DAGs using declared `artifacts.produces/consumes` (with optional `@alias` matching) and executes them via the new `ArtifactPipeline`/`ArtifactStore` scaffolding. Legacy sinks still run sequentially when no artifacts are declared.
- **File copy sink**: introduced `file_copy` sink that consumes a file artifact (via alias or type) and persists it to a specified path, providing a generic hand-off point for downstream integrations or packaging steps.
- **Multi-artifact support**: `artifacts.consumes` entries accept objects with `mode` (`single`/`all`). Pipeline passes all requested artifacts to `prepare_artifacts`, and sinks now either process lists (e.g. blob uploads, zip bundling) or surface clear errors when only single inputs are supported. Artifact metadata now carries `security_level` so downstream sinks preserve classification (e.g., `official`, `official-sensitive`).
- **Security flow**: Datasources, experiments, and sinks now accept `security_level`. During execution, the runner resolves the strictest level from datasource attrs, experiment config, and sink overrides. The pipeline only allows a sink to consume artifacts at or below its clearance, respecting `on_error=skip` when levels mismatch. Produced artifacts inherit the highest applicable level, enabling downstream enforcement and audit.
- **Existing sinks** (GitHub, signed artifacts, local bundles) need schema validation and documented options; add `on_error` to all.
- **Optional targets** (SharePoint, S3) remain future work once core surfaces are stable.
<!-- UPDATE 2025-10-12: Implementations for analytics report sink, file copy sink, artifact chaining, and Azure telemetry middleware are complete; optional targets remain backlog. -->

## Dependencies & Packaging
- `azure-storage-blob` already present; continue using raw REST via SDK. Add optional extra `sinks-azure-devops` for any future SDK integration.
- Repo sinks rely on `requests` (already vendored); ensure optional extras document PAT env vars.
- Excel sink requires `openpyxl>=3.1`; add optional extra `sinks-excel`.
- Zip sink uses stdlib `zipfile`; no extra dependency.
- Telemetry middleware relies on `azureml-core` (provided by `[azure]` extra).

## Auth & Config Considerations
- Azure Blob sink options: `account_url`, `container_name`, `path_template`, `content_type`, `metadata`, `credential_env`, `on_error`.
- Azure DevOps sink options: `organization`, `project`, `repository`, `branch`, `path_template`, `token_env`, `commit_message_template`, `dry_run`, `on_error`.
- Excel/ZIP sinks options: `base_path`, `bundle_name`, `timestamped`, `include_manifest`, `include_csv`, `sheet_name`, `on_error`.
- Telemetry middleware options: `enable_run_logging`, `log_prompts`, `log_config_diffs`, `log_metrics`, `on_error`.
- Document PAT/key expectations; use env vars for secrets (`AZDO_TOKEN`, etc.).

## Testing Strategy
- Blob sink: monkeypatch `BlobClient.upload_blob`, assert payload bytes/metadata without hitting network.
- Azure DevOps sink: use `responses`/`requests_mock` or manual monkeypatch to capture REST payloads, verifying branch/path behaviour and dry-run logging.
- Excel sink: write to tmpdir, open with `openpyxl.load_workbook` to verify sheet contents and manifest.
- ZIP sink: inspect archive contents with `zipfile.ZipFile`.
- Telemetry middleware: monkeypatch `Run` to collect `log_row/log_table` calls, ensure errors respect `on_error`.
- Validation tests: ensure schemas reject missing required options, unknown sink names, or invalid `on_error`.

## Risks & Mitigations
- Credential leakage -> ensure config uses env vars; no secrets in repo.
- Large payloads -> chunk uploads for blob; confirm repo sink handles binary data (use base64 via API).
- Signing key management -> document operator responsibilities, consider Key Vault integration later.

## Implementation Notes
- Azure Blob sink: add resumable upload (chunked via `StageBlock`/`CommitBlockList`), path templating improvements, manifest schema enforcement, `on_error` handling, metadata support.
- Azure DevOps sink: support branch creation detection, path templating, commit batching, optional new-file manifest; ensure `dry_run` logs payload.
- Excel sink: generate workbook with metadata sheet + per-criterion data, save alongside manifest.
- ZIP sink: bundle selected assets (results, manifest, optional CSV/Excel) with timestamped naming.
- Telemetry middleware: extend to log config diffs, metric summaries, and preflight info; ensure fail-fast if Azure ML context missing unless `on_error=skip`.
- Update validators/registries with option schemas for new/extended sinks.
- Persist `security_level` and other derived metadata in downstream artifacts:
  - Blob uploads tag manifest/results blobs via metadata/headers.
  - ZIP manifests include a `security_level` entry and per-file listing when needed.
  - Future `data/*` artifacts should preserve row-level classification.
  - Visual analytics sink emits inline base64 PNGs to prevent mixed content and inherits pipeline security levels.

## Update History
- 2025-10-12 – Documented completion status for Phase 6 sinks/telemetry and highlighted remaining optional targets.
