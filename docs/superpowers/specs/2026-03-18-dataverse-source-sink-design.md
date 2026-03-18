# Dataverse Source and Sink Plugins — Design Spec

**Date:** 2026-03-18
**Status:** Draft
**Scope:** New `dataverse` source plugin, new `dataverse` sink plugin, shared `DataverseClient` infrastructure

## Overview

Add Microsoft Dataverse integration to ELSPETH via a source plugin (read entities) and sink plugin (write/upsert/update entities). Dataverse exposes data through an OData v4 REST API secured by Azure Entra ID. Both plugins share a `DataverseClient` that wraps `AuditedHTTPClient` for protocol-level concerns (auth, pagination, batching, rate limiting).

## Motivation

Dataverse is the data platform underlying Microsoft Dynamics 365, Power Platform, and many enterprise systems. Pipelines that sense from or act upon Dataverse data need first-class support — not ad-hoc HTTP transforms that would bypass audit recording, schema contracts, and field normalization.

## Architecture

### File Layout

```
src/elspeth/plugins/
├── infrastructure/
│   └── clients/
│       └── dataverse.py          # DataverseClient
├── sources/
│   └── dataverse.py              # DataverseSource + DataverseSourceConfig
└── sinks/
    └── dataverse.py              # DataverseSink + DataverseSinkConfig
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| `DataverseClient` | OData protocol, auth, pagination, batching, rate limiting, error classification |
| `DataverseSource` | Entity query config, row streaming, field normalization, schema contracts |
| `DataverseSink` | Write mode dispatch, field mapping, lookup binding, batch accumulation |

### Layer Placement

All three components live at L3 (plugins). `DataverseClient` sits in `plugins/infrastructure/clients/` alongside the existing `AuditedHTTPClient` and `AuditedLLMClient`. No new cross-layer dependencies are introduced.

## DataverseClient

### Wraps AuditedHTTPClient

The client does NOT make raw HTTP calls. It delegates to `AuditedHTTPClient`, which provides:
- Automatic Landscape audit recording for every API call
- Telemetry emission (`ExternalCallCompleted` events)
- SSRF protection (not strictly needed for Dataverse URLs, but defense-in-depth)
- Secret fingerprinting in audit records

`DataverseClient` adds the OData-specific protocol layer on top.

### Authentication

Two methods, both producing OAuth2 bearer tokens against the Dataverse environment URL:

**Service Principal (client credentials flow):**
```yaml
auth:
  method: service_principal
  tenant_id: "${AZURE_TENANT_ID}"
  client_id: "${AZURE_CLIENT_ID}"
  client_secret: "${AZURE_CLIENT_SECRET}"
```

**Managed Identity:**
```yaml
auth:
  method: managed_identity
```

Implementation uses `azure-identity`:
- Service principal: `ClientSecretCredential(tenant_id, client_id, client_secret)`
- Managed identity: `DefaultAzureCredential()` (or `ManagedIdentityCredential()` for explicit selection)

Token scope: `https://<environment_url>/.default`

Token caching and refresh are handled by `azure-identity` internally. The client acquires a token before each request batch and reuses it within its validity window.

No interactive/device code auth — incompatible with headless automated pipelines.

### Authentication Config Model

```python
class DataverseAuthConfig(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    method: Literal["service_principal", "managed_identity"]

    # Service principal fields (required when method=service_principal)
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None

    @model_validator(mode="after")
    def validate_auth_fields(self) -> Self:
        if self.method == "service_principal":
            missing = []
            if self.tenant_id is None:
                missing.append("tenant_id")
            if self.client_id is None:
                missing.append("client_id")
            if self.client_secret is None:
                missing.append("client_secret")
            if missing:
                raise ValueError(f"service_principal auth requires: {', '.join(missing)}")
        return self
```

### OData Query Execution

Two query paths:

**Structured OData queries:**
```
GET /api/data/v9.2/<entity>?$select=field1,field2&$filter=statecode eq 0&$orderby=createdon desc&$top=5000
```

**FetchXML queries:**
```
GET /api/data/v9.2/<entity>?fetchXml=<url-encoded-xml>
```

Both return the same JSON response shape:
```json
{
  "value": [{"field1": "...", "field2": "..."}, ...],
  "@odata.nextLink": "https://...?$skiptoken=..."
}
```

### Pagination

Two pagination mechanisms, depending on query mode:

**Structured OData queries:** Server-driven pagination via `@odata.nextLink`. The client follows next-link URLs automatically, yielding pages to the caller.

**FetchXML queries:** Paging cookie mechanism. Dataverse returns a `@Microsoft.Dynamics.CRM.fetchxmlpagingcookie` in the response. The client URL-decodes the cookie, injects it as a `paging-cookie` attribute on the `<fetch>` element, increments the `page` attribute, and re-issues the query. Pagination ends when the response contains `@Microsoft.Dynamics.CRM.morerecords: false`.

Both mechanisms provide:
- Memory-efficient streaming (one page in memory at a time)
- No client-side offset tracking
- Respects Dataverse's preferred page size

The client yields `list[dict]` per page, not individual rows. The source plugin handles row-level iteration.

### Batch Requests

For sink write operations, the client supports `POST /$batch` with OData batch format:
- Up to 1000 operations per batch (Dataverse limit)
- Change sets for transactional grouping
- Individual operation error reporting (partial success is possible)

Batch format uses multipart/mixed content type per OData batch protocol.

### Rate Limiting

Two layers:
1. **Hard ceiling** — configured at the settings level via `RateLimitSettings` and injected through the `RateLimitRegistry`. The `DataverseClient` accepts an optional `RateLimiter` instance (same pattern as `AuditedHTTPClient` and `AuditedLLMClient`). This is the IP-ban prevention guard — never exceeded regardless of adaptive behavior.
2. **Adaptive backoff** — when a 429 response arrives with `Retry-After` header, the client pauses requests for the specified duration. This is Dataverse-specific logic in the client, layered under the hard ceiling.

```yaml
# Settings-level rate limiting (not per-plugin config)
rate_limit:
  max_requests_per_second: 15   # Hard ceiling
```

The `DataverseClient` constructor accepts `limiter: RateLimiter | None` and calls `_acquire_rate_limit()` before each request, matching the existing `AuditedClientBase` pattern.

### Error Classification

| HTTP Status | Classification | Engine Action |
|-------------|---------------|---------------|
| 200-299 | Success | Process response |
| 400 | Non-retryable | Config/data error — quarantine row (sink) or fail run (source) |
| 401, 403 | Non-retryable | Auth failure — fail run |
| 404 | Non-retryable | Entity/record not found — quarantine row (sink) or fail run (source) |
| 409 | Non-retryable | Conflict (duplicate on create) — quarantine row |
| 412 | Non-retryable | Precondition failed (optimistic concurrency) — quarantine row |
| 429 | Retryable | Rate limited — respect Retry-After, retry |
| 500-599 | Retryable | Transient server error — retry |
| Network error | Retryable | Timeout, connection reset — retry |

### Tier 3 Boundary

Every response from Dataverse is Tier 3 (external data). The client validates immediately:
- JSON parse (reject malformed responses)
- Response structure (`value` array present for queries, error object for failures)
- Type validation of OData metadata fields (`@odata.nextLink` is string or absent)

Once validated, the parsed data is Tier 2 — trusted by the source/sink plugins.

## DataverseSource

### Extends BaseSource

```python
class DataverseSource(BaseSource):
    name = "dataverse"
    determinism = Determinism.EXTERNAL_CALL  # Live REST API, not static file read
```

### Configuration

```python
class DataverseSourceConfig(DataPluginConfig):
    environment_url: str              # https://<org>.crm.dynamics.com
    auth: DataverseAuthConfig
    api_version: str = "v9.2"         # Dataverse Web API version
    on_validation_failure: str = "quarantine"  # Route for invalid rows

    # Structured query mode
    entity: str | None = None         # Entity logical name (e.g., "contact")
    select: list[str] | None = None   # $select fields (None = all)
    filter: str | None = None         # $filter expression
    orderby: str | None = None        # $orderby expression
    top: int | None = None            # $top limit (None = all records)

    # FetchXML query mode
    fetch_xml: str | None = None      # Raw FetchXML string

    # Field handling
    normalize_fields: bool = True     # Normalize Dataverse logical names
    field_mapping: dict[str, str] | None = None  # Manual field name overrides
    include_formatted_values: bool = False  # Preserve Dataverse formatted value annotations

    @model_validator(mode="after")
    def validate_query_mode(self) -> Self:
        has_structured = self.entity is not None
        has_fetchxml = self.fetch_xml is not None
        if has_structured == has_fetchxml:
            raise ValueError("Specify exactly one of: entity (structured query) or fetch_xml")
        if not has_structured and any(f is not None for f in (self.select, self.filter, self.orderby, self.top)):
            raise ValueError("select/filter/orderby/top require entity (structured query mode)")
        return self
```

Note: Extends `DataPluginConfig` directly (not `SourceDataConfig`/`PathConfig`, which require a local file `path`). Follows the `AzureBlobSourceConfig` pattern for REST API sources. The `on_validation_failure` field is defined directly for quarantine routing. Rate limiting is NOT a per-plugin config field — it is configured at the settings level via `RateLimitSettings` and injected through the `RateLimitRegistry` at runtime (see Rate Limiting section).

### Load Lifecycle

```
__init__(config)
  → Validate config (Pydantic)
  → Store auth config and query parameters
  → Pre-compile FetchXML (if provided) — structural validation only
  → NOTE: DataverseClient is NOT constructed here (needs recorder/run_id from context)

on_start(ctx)
  → Construct DataverseClient with recorder, run_id, state_id, telemetry_emit from ctx
  → Construct AuditedHTTPClient (wrapped by DataverseClient)
  → Acquire initial auth token (validates credentials early)
  → Optionally validate entity exists via metadata query

load(ctx)
  → Execute query (structured or FetchXML)
  → Follow pagination:
    → Structured queries: @odata.nextLink URLs
    → FetchXML queries: paging cookie (<cookie> attribute in response)
  → Per page:
    → Per row:
      → Strip OData metadata (@odata.* fields)
      → Optionally preserve formatted values (include_formatted_values)
      → Normalize field names (if enabled)
      → Validate against schema
      → yield SourceRow.valid(row) or SourceRow.quarantined(row, error, destination)
  → Lock schema contract after first valid row

on_complete(ctx)
  → (Optional) Log source statistics (rows yielded, pages fetched, quarantine count)

close()
  → Release DataverseClient resources (HTTP connections, credential handles)
```

### OData Metadata Stripping

Dataverse responses include OData annotations (`@odata.etag`, `@odata.context`, `_field_value@OData.Community.Display.V1.FormattedValue`, etc.). The source strips these from row data before yielding. The raw annotations are available in the audit trail (recorded by `AuditedHTTPClient`) but don't pollute the pipeline row.

Option: `include_formatted_values: true` to preserve Dataverse's formatted value annotations as additional fields (e.g., `statecode` = 0, `statecode__formatted` = "Active"). Off by default.

### Schema Modes

All three schema modes (fixed, flexible, observed) are supported:
- **Observed** (default): Discover fields from first page response, lock after first valid row
- **Fixed**: User declares expected fields; extras rejected
- **Flexible**: User declares known fields; extras discovered from first page

### Config Examples

**Structured query:**
```yaml
source:
  plugin: dataverse
  options:
    environment_url: "https://myorg.crm.dynamics.com"
    auth:
      method: service_principal
      tenant_id: "${AZURE_TENANT_ID}"
      client_id: "${AZURE_CLIENT_ID}"
      client_secret: "${AZURE_CLIENT_SECRET}"
    entity: "contact"
    select: [fullname, emailaddress1, createdon, _parentcustomerid_value]
    filter: "statecode eq 0 and createdon gt 2024-01-01"
    orderby: "createdon desc"
    top: 5000
    schema:
      mode: observed
```

**FetchXML query with joins:**
```yaml
source:
  plugin: dataverse
  options:
    environment_url: "https://myorg.crm.dynamics.com"
    auth:
      method: managed_identity
    fetch_xml: |
      <fetch top="5000">
        <entity name="contact">
          <attribute name="fullname"/>
          <attribute name="emailaddress1"/>
          <link-entity name="account" from="accountid" to="parentcustomerid">
            <attribute name="name" alias="company_name"/>
          </link-entity>
        </entity>
      </fetch>
    schema:
      mode: observed
```

## DataverseSink

### Extends BaseSink

```python
class DataverseSink(BaseSink):
    name = "dataverse"
    idempotent = False  # Only upsert mode is idempotent; create/update are not
    supports_resume = False  # Dataverse writes are not locally staged
```

Note: `idempotent` is False at the class level. In upsert mode the *operation* is idempotent (PATCH is naturally idempotent), but the sink class conservatively declares False since create and update modes are not.

### Configuration

```python
class DataverseSinkConfig(DataPluginConfig):
    environment_url: str
    auth: DataverseAuthConfig
    api_version: str = "v9.2"

    entity: str                       # Target entity logical name
    mode: Literal["create", "upsert", "update"]

    # Field mapping (mandatory — no passthrough)
    field_mapping: dict[str, str]     # pipeline_field → dataverse_column

    # Key fields (required for upsert/update)
    primary_key: str | None = None    # Dataverse primary key field (for update mode)
    alternate_key: str | None = None  # Business key field (for upsert mode)

    # Lookup field declarations
    lookups: dict[str, LookupConfig] | None = None

    @model_validator(mode="after")
    def validate_mode_keys(self) -> Self:
        if self.mode == "upsert" and self.alternate_key is None:
            raise ValueError("upsert mode requires alternate_key")
        if self.mode == "update" and self.primary_key is None:
            raise ValueError("update mode requires primary_key")
        return self
```

Note: `DataPluginConfig` provides `schema_config` for input validation. Rate limiting uses the settings-level `RateLimitRegistry`, not a per-plugin config field.

### Lookup Configuration

```python
class LookupConfig(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    target_entity: str    # Dataverse entity to bind to (e.g., "accounts")
    target_field: str     # Navigation property name (e.g., "parentcustomerid")
```

The sink translates lookup fields into OData bind syntax:
```python
# Pipeline row: {"parent_account_id": "abc-123-guid"}
# Config: lookups.parent_account_id = {target_entity: "accounts", target_field: "parentcustomerid"}
# OData payload: {"parentcustomerid@odata.bind": "/accounts(abc-123-guid)"}
```

### Write Modes

| Mode | HTTP Method | URL Pattern | Error on |
|------|-------------|-------------|----------|
| `create` | POST | `/api/data/v9.2/<entity>` | Duplicate key (409) |
| `upsert` | PATCH | `/api/data/v9.2/<entity>(<alternate_key>=<value>)` | — (creates or updates) |
| `update` | PATCH | `/api/data/v9.2/<entity>(<primary_key>)` | Not found (404) |

### Sink Lifecycle

```
__init__(config)
  → Validate config (Pydantic)
  → Store field mapping, lookup config, write mode
  → NOTE: DataverseClient is NOT constructed here (needs recorder/run_id from context)

on_start(ctx)
  → Construct DataverseClient with recorder, run_id, state_id, telemetry_emit from ctx
  → Acquire initial auth token (validates credentials early)
  → Optionally validate entity/alternate key exists via metadata query

write(rows, ctx)
  → For each row:
    → Apply field_mapping (pipeline names → Dataverse column names)
    → Format lookup fields (@odata.bind syntax)
    → Validate all mapped fields present (crash if missing — Tier 2 data)
  → Submit individual requests to DataverseClient (one per row)
  → Each request recorded individually by AuditedHTTPClient
  → Return ArtifactDescriptor with batch metadata (total rows, success count)

flush()
  → No-op (Dataverse writes are immediate, no local staging buffer)

close()
  → Release DataverseClient resources (HTTP connections, credential handles)
```

### Write Strategy: Individual Requests with Batching at Client Level

The `write()` method receives a list of rows from the engine. Rather than submitting a `$batch` request (which returns per-operation results that the `write()` → `ArtifactDescriptor` contract can't represent per-row), the sink issues individual requests per row. This aligns with the existing sink contract where `write()` either succeeds (returns `ArtifactDescriptor`) or fails (raises an exception for the engine to handle).

For throughput, the `DataverseClient` can pipeline requests using `httpx`'s connection pooling and keep-alive, and the settings-level rate limiter prevents overloading the API. If Dataverse returns a row-level error (e.g., 409 conflict on create), the client raises a typed exception that the engine's retry/quarantine logic handles.

**Future optimization:** If per-row HTTP overhead becomes a bottleneck, a `$batch` mode can be added behind a config flag. This would require the sink to handle partial success internally (re-submitting failed rows individually) before returning a single `ArtifactDescriptor`. This is a performance optimization, not a correctness concern — the individual-request path is correct and auditable from day one.

### Config Example

```yaml
sinks:
  dataverse_output:
    plugin: dataverse
    options:
      environment_url: "https://myorg.crm.dynamics.com"
      auth:
        method: service_principal
        tenant_id: "${AZURE_TENANT_ID}"
        client_id: "${AZURE_CLIENT_ID}"
        client_secret: "${AZURE_CLIENT_SECRET}"
      entity: "contact"
      mode: upsert
      alternate_key: emailaddress1
      field_mapping:
        customer_email: emailaddress1
        customer_name: fullname
        sentiment_score: new_sentimentscore
      lookups:
        parent_account_id:
          target_entity: accounts
          target_field: parentcustomerid
```

## Dependencies

All Dataverse dependencies are already available via the existing `[azure]` extra or base dependencies:

| Dependency | Extra | Purpose |
|-----------|-------|---------|
| `httpx` | base | HTTP client (already used by `AuditedHTTPClient`) |
| `azure-identity` | `[azure]` | OAuth2 token acquisition |

No new dependencies required. The Dataverse Web API is a standard OData v4 REST endpoint — no dedicated SDK needed.

## Plugin Discovery

Both plugins must be discoverable by the plugin scanner. The scanner (`plugins/infrastructure/discovery.py`) uses `PLUGIN_SCAN_CONFIG` to determine which directories to scan. The source and sink directories are already scanned, so `dataverse.py` files placed there will be discovered automatically.

No changes to `PLUGIN_SCAN_CONFIG` are needed.

## Testing Strategy

### Unit Tests

- `DataverseAuthConfig` validation (service principal missing fields, managed identity, mutual exclusion)
- `DataverseSourceConfig` validation (structured vs FetchXML mutual exclusion, required fields)
- `DataverseSinkConfig` validation (mode/key requirements, field mapping, lookup config)
- OData metadata stripping (various annotation patterns)
- Field mapping and lookup binding syntax generation
- Batch request formatting
- Error classification (status code → retryable/non-retryable)
- Pagination link following (mock responses with `@odata.nextLink`)

### Integration Tests

- Source: structured query against mock Dataverse endpoint (httpx mock transport)
- Source: FetchXML query against mock endpoint
- Source: pagination across multiple pages
- Source: schema discovery and contract locking
- Sink: create, upsert, update modes against mock endpoint
- Sink: batch write with partial failures
- Sink: lookup field binding in batch payload
- End-to-end: source → transform → sink pipeline with mock Dataverse

### Tier Model Compliance

All tests exercise production code paths (no manual object construction that bypasses `from_dict()` or `instantiate_plugins_from_config()`). The `DataverseClient` is tested via mock HTTP transport on `AuditedHTTPClient`, not by mocking the client itself.

## Security Considerations

- **Secret handling:** Client secret and API keys are resolved via ELSPETH's secret management (`secrets:` section in settings.yaml or environment variables). Never logged or stored in audit trail — HMAC fingerprints only.
- **SSRF:** Dataverse URLs are validated. The `environment_url` must be a valid `https://*.crm.dynamics.com` or `https://*.dynamics.com` URL — reject arbitrary endpoints.
- **Token scope:** OAuth2 tokens are scoped to the specific Dataverse environment URL, not broad Azure scopes.
- **Batch atomicity:** No change sets by default — partial success is visible in the audit trail, not hidden by rollback.
