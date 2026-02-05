# Analysis: src/elspeth/plugins/azure/blob_sink.py

**Lines:** 637
**Role:** Azure Blob Storage sink plugin -- serializes pipeline output (CSV, JSON, JSONL) and uploads to Azure Blob containers. Handles Jinja2 path templating, overwrite policy, display header restoration, and audit trail recording. This is the pipeline's external output boundary -- data loss here means emergency dispatch results never reach their destination.
**Key dependencies:** Imports `AzureAuthConfig` (auth.py), `BaseSink` (base.py), `DataPluginConfig` (config_base.py), `PluginContext` (context.py), `ArtifactDescriptor`/`CallStatus`/`CallType`/`PluginSchema` (contracts), `create_schema_from_config` (schema_factory.py), `jinja2.Environment`/`StrictUndefined`. Imported by engine orchestrator (core.py) and test_blob_sink.py.
**Analysis depth:** FULL

## Summary
The sink is well-structured with correct trust model application (no coercion, external calls wrapped). The most significant issue is a Server-Side Template Injection (SSTI) surface via Jinja2 templating of the blob path, though the current template context is limited. The exception re-raise pattern has the same constructor mismatch risk as the source. The overwrite check has a TOCTOU race condition. The file is generally sound but needs attention on these specific issues.

## Critical Findings

### [350-355] Jinja2 SSTI surface via blob_path template
**What:** `_render_blob_path()` creates a Jinja2 `Environment` and renders the `blob_path` config value as a template with `StrictUndefined`. The template context is limited to `run_id` and `timestamp`, and the blob_path comes from YAML configuration (not user data). However, the Jinja2 environment is created with default settings, which means a malicious or misconfigured `blob_path` value could access Python internals via Jinja2's attribute access.
**Why it matters:** If an attacker can influence the pipeline YAML configuration (e.g., through a CI/CD compromise or config injection), they could craft a blob_path like `{{ ''.__class__.__mro__[1].__subclasses__() }}` to enumerate Python classes or potentially achieve remote code execution. While the threat model assumes config is trusted (system-owned code), defense-in-depth recommends using a `SandboxedEnvironment` instead of plain `Environment`.
**Evidence:**
```python
env = Environment(undefined=StrictUndefined)
template = env.from_string(self._blob_path_template)
return template.render(
    run_id=ctx.run_id,
    timestamp=datetime.now(tz=UTC).isoformat(),
)
```
A `SandboxedEnvironment` would restrict attribute access and prevent exploitation even if the template string is compromised.

### [598] Exception re-raise pattern may mangle Azure SDK exception constructors
**What:** Same pattern as blob_source.py -- `raise type(e)(f"Failed to upload blob...") from e`.
**Why it matters:** Azure SDK exceptions (e.g., `ResourceExistsError`, `HttpResponseError`) have multi-parameter constructors. Calling `type(e)(string)` may fail with `TypeError`, hiding the original upload failure. For a sink, this is especially dangerous because a failed upload that masks its error could leave the operator unable to determine whether data was written or not.
**Evidence:**
```python
raise type(e)(f"Failed to upload blob '{rendered_path}' to container '{self._container}': {e}") from e
```

## Warnings

### [548] TOCTOU race on overwrite check
**What:** When `overwrite=False`, the code calls `blob_client.exists()` and then `blob_client.upload_blob()` as separate operations. Between these two calls, another process could create the blob.
**Why it matters:** In a concurrent environment (multiple pipeline instances, or external processes writing to the same container), the exists-check can succeed (blob does not exist) but the upload can then overwrite a blob that was created between the check and the upload. The Azure SDK's `upload_blob(overwrite=False)` would handle this atomically by using conditional headers -- but the code explicitly passes `overwrite=self._overwrite`, which is `False` here, so Azure SDK will reject the upload. However, the custom `ValueError` on line 549 is raised before the SDK gets a chance to enforce its own conditional write, and the SDK's error message would be different/more informative.
**Evidence:**
```python
if not self._overwrite and blob_client.exists():
    raise ValueError(f"Blob '{rendered_path}' already exists and overwrite=False")

# Upload the content
blob_client.upload_blob(content, overwrite=self._overwrite)
```
The `exists()` call is redundant since `upload_blob(overwrite=False)` will raise `ResourceExistsError` if the blob exists. The manual check adds latency (extra HTTP round-trip) and the TOCTOU window.

### [420] _serialize_csv crashes on empty rows list
**What:** `_serialize_csv` accesses `rows[0]` on line 420 without checking if `rows` is empty. The caller `write()` checks for empty rows on line 514, but `_serialize_rows()` is also called directly from `write()` after the empty check -- so this is safe in the current flow. However, if `_serialize_csv` is ever called directly or the flow changes, it will crash with `IndexError`.
**Why it matters:** Fragile implicit contract between `write()` and `_serialize_csv()`. Per the codebase policy, this would be "our code, let it crash" -- which is correct -- but the crash would be an inscrutable `IndexError` rather than a clear message.
**Evidence:**
```python
def _serialize_csv(self, rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    data_fields, display_fields = self._get_field_names_and_display(rows[0])
```

### [514-522] Empty rows returns misleading ArtifactDescriptor
**What:** When `rows` is empty, the method returns an `ArtifactDescriptor` with `content_hash=sha256(b"").hexdigest()` and `size_bytes=0`, and importantly, no blob is uploaded. The `path_or_uri` still claims a location (`azure://container/path`), but no blob exists at that location.
**Why it matters:** The audit trail records an artifact at a specific URI with a specific hash, but that URI does not point to anything in Azure. If an auditor tries to verify the artifact, they will find nothing. The correct behavior for zero rows might be to either skip writing entirely (returning a sentinel) or upload an empty blob.
**Evidence:**
```python
if not rows:
    rendered_path = self._render_blob_path(ctx)
    return ArtifactDescriptor(
        artifact_type="file",
        path_or_uri=f"azure://{self._container}/{rendered_path}",
        content_hash=hashlib.sha256(b"").hexdigest(),
        size_bytes=0,
    )
```

### [350] New Jinja2 Environment created on every write call
**What:** `_render_blob_path()` creates a new `Environment(undefined=StrictUndefined)` instance every time it is called. The `write()` method calls `_render_blob_path()` on every batch.
**Why it matters:** Jinja2 `Environment` creation involves compiling the template, which is non-trivial overhead. For a sink that may receive thousands of batches, this is unnecessary repeated work. The environment and compiled template should be cached at `__init__` time.
**Evidence:**
```python
def _render_blob_path(self, ctx: PluginContext) -> str:
    env = Environment(undefined=StrictUndefined)
    template = env.from_string(self._blob_path_template)
    return template.render(...)
```

### [253] Same plugin name "azure_blob" for both source and sink
**What:** Both `AzureBlobSource.name` and `AzureBlobSink.name` are `"azure_blob"`.
**Why it matters:** While the plugin discovery system differentiates sources and sinks by type, having the same `name` for both could cause confusion in the audit trail, error messages, and MCP analysis tools when diagnosing issues with "azure_blob" plugin. The `nodes` table records plugin names, and a human reading the audit trail would need to cross-reference `node_type` to disambiguate.
**Evidence:**
```python
class AzureBlobSink(BaseSink):
    name = "azure_blob"
```
```python
class AzureBlobSource(BaseSource):
    name = "azure_blob"
```

## Observations

### [258] supports_resume correctly set to False
**What:** The sink correctly declares `supports_resume: bool = False` with a clear rationale about Azure Blob immutability. The `configure_for_resume()` override provides a helpful error message with alternative approaches.
**Why it matters:** Good -- this prevents silent data loss from attempted resume on an immutable storage backend.

### [527-528] Display header application only for JSON/JSONL, not CSV
**What:** `_apply_display_headers()` is only called for JSON and JSONL formats (line 527-528). CSV display headers are handled differently via `_get_field_names_and_display()` which maps header names but keeps data keys unchanged.
**Why it matters:** This is correct behavior (CSV separates header display from data field access), but the asymmetry is not documented. A reader might expect `_apply_display_headers()` to be used for all formats.

### Config field duplication with AzureBlobSourceConfig
**What:** `AzureBlobSinkConfig` duplicates all auth-related fields and validators from `AzureBlobSourceConfig`. Both configs independently define `connection_string`, `sas_token`, `use_managed_identity`, `account_url`, `tenant_id`, `client_id`, `client_secret`, `container`, `blob_path`, and their validators.
**Why it matters:** Six identical field definitions and two identical validators (`validate_auth_config`, `validate_container_not_empty`, `validate_blob_path_not_empty`). Changes to auth handling must be made in both places. Consider extracting an `AzureBlobConfigMixin` or shared base class.

### [607-623] flush() documented correctly as no-op
**What:** `flush()` is a well-documented no-op with clear rationale about Azure Blob's synchronous upload semantics.
**Why it matters:** Good documentation practice -- prevents future engineers from adding flush logic that would be redundant.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** Replace `Environment` with `SandboxedEnvironment` for blob path rendering (defense-in-depth against SSTI). Fix the exception re-raise pattern to use a consistent, safe exception wrapper. Remove the redundant `exists()` check and rely on Azure SDK's conditional write semantics. Consider caching the Jinja2 environment/template. Address the phantom ArtifactDescriptor for empty rows.
**Confidence:** HIGH -- All findings are based on direct code reading. The SSTI concern is a well-known Jinja2 pattern. The TOCTOU race is a textbook concurrency issue. The exception constructor problem is verified against Azure SDK source.
