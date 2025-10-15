# External Service Integration Documentation

**Document Version:** 1.0
**Last Updated:** 2025-10-15
**ATO Requirement:** MF-4 External Service Approval & Endpoint Lockdown

## Overview

Elspeth integrates with external services to provide LLM capabilities and cloud storage. This document catalogs all external service integrations, their data flows, security classifications, and approved endpoints.

**Security Principle:** All external service endpoints must be explicitly approved and validated before use. This prevents data exfiltration to unauthorized services.

## External Service Inventory

### 1. Azure OpenAI Service

**Plugin:** `azure_openai`
**Location:** `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py`
**Purpose:** Managed OpenAI API access through Azure infrastructure

**Data Flow:**
```
Experiment Data → PluginContext (security_level) → Prompt Rendering
→ Middleware Chain → Azure OpenAI API → Response → Middleware Chain
→ Result Processing → Sinks
```

**Data Sent:**
- User prompts (templated with experiment data)
- System messages
- LLM configuration (temperature, max_tokens, etc.)
- API authentication (via api_key)

**Data Received:**
- LLM-generated responses
- Token usage metadata
- Response timing information

**Classification Levels:**
- Supports: `public`, `internal`, `OFFICIAL`, `confidential`, `restricted`
- Requires: `security_level` parameter in configuration
- Enforcement: PluginContext propagation, artifact pipeline clearance checks

**Configuration Parameters:**
- `azure_endpoint` (REQUIRED): Azure OpenAI resource endpoint
- `api_version` (REQUIRED): Azure API version
- `deployment_name` (REQUIRED): Model deployment name
- `api_key_env` (REQUIRED): Environment variable containing API key
- `temperature`, `max_tokens`: LLM parameters

**Approved Endpoints:**
- Pattern: `https://*.openai.azure.com`
- Validation: Must be Azure OpenAI resource endpoint
- Rationale: Azure OpenAI provides enterprise-grade security, data residency, and compliance guarantees

**Security Controls:**
- API key stored in environment variables (not in config files)
- TLS encryption for all communications
- Audit logging via `audit_logger` middleware (recommended)
- Security level propagation via PluginContext
- Artifact pipeline clearance enforcement

**Compliance Notes:**
- Azure OpenAI supports data residency requirements
- Supports Azure Private Link for network isolation
- Compliant with government cloud requirements (Azure Government)
- Audit trails available via Azure Monitor

---

### 2. OpenAI-Compatible HTTP APIs

**Plugin:** `http_openai`
**Location:** `src/elspeth/plugins/nodes/transforms/llm/openai_http.py`
**Purpose:** Generic OpenAI-compatible API client (OpenAI, LocalAI, Ollama, etc.)

**Data Flow:**
```
Experiment Data → PluginContext (security_level) → Prompt Rendering
→ Middleware Chain → HTTP API → Response → Middleware Chain
→ Result Processing → Sinks
```

**Data Sent:**
- User prompts (templated with experiment data)
- System messages
- LLM configuration (model, temperature, max_tokens, etc.)
- API authentication (via api_key, if required)

**Data Received:**
- LLM-generated responses
- Token usage metadata (if supported by API)
- Response timing information

**Classification Levels:**
- Supports: `public`, `internal`, `OFFICIAL`, `confidential`, `restricted`
- Requires: `security_level` parameter in configuration
- Enforcement: PluginContext propagation, artifact pipeline clearance checks

**Configuration Parameters:**
- `api_base` (REQUIRED): Base URL for API endpoint
- `model` (REQUIRED): Model identifier
- `api_key_env` (OPTIONAL): Environment variable containing API key
- `api_key` (OPTIONAL): Direct API key (use api_key_env instead)
- `temperature`, `max_tokens`: LLM parameters
- `timeout`: Request timeout in seconds

**Approved Endpoints:**

| Endpoint Pattern | Use Case | Data Classification | Status |
|------------------|----------|---------------------|--------|
| `https://api.openai.com` | OpenAI production | `public`, `internal` only | Approved |
| `http://localhost:*` | Local testing (LocalAI, Ollama) | Any (data never leaves host) | Approved |
| `http://127.0.0.1:*` | Local testing (LocalAI, Ollama) | Any (data never leaves host) | Approved |
| `https://*.internal.company.com` | Internal LLM services | `internal`, `OFFICIAL`, `confidential`, `restricted` | Requires approval |

**Security Controls:**
- API key stored in environment variables (not in config files)
- TLS encryption for production endpoints (HTTPS required for non-localhost)
- Audit logging via `audit_logger` middleware (recommended)
- Security level propagation via PluginContext
- Artifact pipeline clearance enforcement
- Endpoint validation against approved list

**Compliance Notes:**
- Public OpenAI endpoint should only be used for `public` or `internal` data
- For `OFFICIAL`, `confidential`, or `restricted` data, use:
  - Azure OpenAI (preferred for government/compliance)
  - On-premises LLM services (LocalAI, Ollama)
  - Approved internal LLM APIs

**Warnings:**
- ⚠️ Public OpenAI API sends data to OpenAI servers (US-based)
- ⚠️ Data retention policies differ from Azure OpenAI
- ⚠️ Not suitable for government or compliance-sensitive workloads

---

### 3. Azure Blob Storage

**Plugins:**
- `azure_blob` datasource: `src/elspeth/plugins/nodes/sources/blob.py`
- `csv_blob` datasource: `src/elspeth/plugins/nodes/sources/csv_blob.py`
- `blob_sink` sink: `src/elspeth/plugins/nodes/sinks/blob.py`

**Purpose:** Cloud storage for experiment input data and results

**Data Flow (Datasource):**
```
Azure Blob Container → Download → Local Cache (if retain_local=true)
→ DataFrame Loading → Experiment Processing
```

**Data Flow (Sink):**
```
Experiment Results → Artifact Production → Upload to Azure Blob
→ Artifact Metadata Recording
```

**Data Sent (Sink):**
- Experiment results (CSV, JSON, etc.)
- Artifact metadata
- Authentication (via SAS token or managed identity)

**Data Received (Datasource):**
- Input data files (CSV, JSON, etc.)
- Blob metadata

**Classification Levels:**
- Supports: `public`, `internal`, `OFFICIAL`, `confidential`, `restricted`
- Requires: `security_level` parameter in configuration
- Enforcement: PluginContext propagation, artifact pipeline clearance checks

**Configuration Parameters (Datasource):**
- `container` (REQUIRED): Azure Blob container name
- `blob_name` (REQUIRED): Blob path within container
- `profile` (OPTIONAL): Reference to `config/azure_blob_profiles.yaml`
- `account_url` (OPTIONAL): Storage account URL
- `sas_token_env` (OPTIONAL): Environment variable for SAS token
- `retain_local` (REQUIRED in STRICT mode): Cache downloaded data locally

**Configuration Parameters (Sink):**
- `container` (REQUIRED): Azure Blob container name
- `blob_prefix` (OPTIONAL): Prefix for uploaded blobs
- `profile` (OPTIONAL): Reference to `config/azure_blob_profiles.yaml`
- `account_url` (OPTIONAL): Storage account URL
- `sas_token_env` (OPTIONAL): Environment variable for SAS token

**Approved Endpoints:**
- Pattern: `https://*.blob.core.windows.net` (Azure Public Cloud)
- Pattern: `https://*.blob.core.usgovcloudapi.net` (Azure Government)
- Pattern: `https://*.blob.core.chinacloudapi.cn` (Azure China)
- Validation: Must be Azure Blob Storage endpoint
- Rationale: Azure Blob Storage provides enterprise-grade security, encryption at rest, and compliance

**Security Controls:**
- Authentication via SAS tokens or Azure Managed Identity
- TLS encryption for all communications
- Encryption at rest (Azure Storage Service Encryption)
- Network isolation via Azure Private Link (optional)
- Data retention enforcement (`retain_local=true` in STRICT mode)
- Security level propagation via PluginContext

**Compliance Notes:**
- Azure Blob Storage supports data residency requirements
- Supports customer-managed encryption keys (CMEK)
- Compliant with government cloud requirements (Azure Government)
- Audit trails available via Azure Monitor and Storage Analytics
- Immutable storage options available for compliance

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Elspeth Framework                            │
│                                                                      │
│  ┌──────────────┐                                                   │
│  │ Datasource   │  (1) Load Input Data                              │
│  │              │◄─────────────────────────────────────┐            │
│  │ - local_csv  │                                      │            │
│  │ - azure_blob │                                      │            │
│  │ - csv_blob   │                                      │            │
│  └──────┬───────┘                                      │            │
│         │                                              │            │
│         │ (2) DataFrame + security_level               │            │
│         ▼                                              │            │
│  ┌──────────────┐                                      │            │
│  │ Experiment   │                                      │            │
│  │ Runner       │                                      │            │
│  │              │                                      │            │
│  │ - Row plugins│                                      │            │
│  │ - Prompts    │                                      │            │
│  └──────┬───────┘                                      │            │
│         │                                              │            │
│         │ (3) Rendered prompts + context               │            │
│         ▼                                              │            │
│  ┌──────────────┐                                      │            │
│  │ LLM Client   │  (4) API Request                     │            │
│  │              ├──────────────────────────────┐       │            │
│  │ - azure_     │                              │       │            │
│  │   openai     │  (5) API Response            │       │            │
│  │ - http_      │◄─────────────────────────────┤       │            │
│  │   openai     │                              │       │            │
│  └──────┬───────┘                              │       │            │
│         │                                      │       │            │
│         │ (6) Responses + metadata             │       │            │
│         ▼                                      │       │            │
│  ┌──────────────┐                              │       │            │
│  │ Aggregation  │                              │       │            │
│  │ & Validation │                              │       │            │
│  └──────┬───────┘                              │       │            │
│         │                                      │       │            │
│         │ (7) Final results + artifacts        │       │            │
│         ▼                                      │       │            │
│  ┌──────────────┐                              │       │            │
│  │ Artifact     │                              │       │            │
│  │ Pipeline     │                              │       │            │
│  │              │                              │       │            │
│  │ - Dependency │                              │       │            │
│  │   resolution │                              │       │            │
│  │ - Security   │                              │       │            │
│  │   clearance  │                              │       │            │
│  └──────┬───────┘                              │       │            │
│         │                                      │       │            │
│         │ (8) Write outputs                    │       │            │
│         ▼                                      │       │            │
│  ┌──────────────┐                              │       │            │
│  │ Sinks        │  (9) Upload Results          │       │            │
│  │              ├──────────────────────────────┼───────┼───────┐    │
│  │ - csv        │                              │       │       │    │
│  │ - blob_sink  │                              │       │       │    │
│  │ - analytics  │                              │       │       │    │
│  └──────────────┘                              │       │       │    │
│                                                │       │       │    │
└────────────────────────────────────────────────┼───────┼───────┼────┘
                                                 │       │       │
                                                 ▼       ▼       ▼
                                          ┌──────────┐ ┌─────────┐
                                          │  Azure   │ │  Azure  │
                                          │  OpenAI  │ │  Blob   │
                                          │          │ │ Storage │
                                          └──────────┘ └─────────┘
                                          ┌──────────┐
                                          │  OpenAI  │
                                          │   HTTP   │
                                          │   APIs   │
                                          └──────────┘

Legend:
  ─────► Data flow
  ─────┐ External service boundary
        │
```

---

## Security Classification Guidance

### Data Classification Levels

Elspeth supports PSPF (Protective Security Policy Framework) classification levels:

| Level | Description | External Service Restrictions |
|-------|-------------|-------------------------------|
| `public` | Publicly available information | Any approved endpoint |
| `internal` | Internal use only | Azure OpenAI, internal APIs, local LLMs |
| `OFFICIAL` | Government/official information | Azure OpenAI (Azure Gov preferred), internal APIs, local LLMs |
| `confidential` | Confidential business data | Azure OpenAI (private link), internal APIs, local LLMs only |
| `restricted` | Highly sensitive data | Internal APIs, local LLMs only (air-gapped if possible) |

### Service Selection by Classification

**For `public` data:**
- ✅ Azure OpenAI
- ✅ OpenAI public API
- ✅ Local LLMs (LocalAI, Ollama)
- ✅ Internal LLM APIs

**For `internal` or `OFFICIAL` data:**
- ✅ Azure OpenAI (recommended)
- ✅ Local LLMs (LocalAI, Ollama)
- ✅ Approved internal LLM APIs
- ⚠️ OpenAI public API (requires risk acceptance)

**For `confidential` data:**
- ✅ Azure OpenAI with Private Link
- ✅ Local LLMs (air-gapped recommended)
- ✅ Approved internal LLM APIs with encryption
- ❌ OpenAI public API (not allowed)

**For `restricted` data:**
- ✅ Local LLMs only (air-gapped deployment)
- ✅ Approved internal LLM APIs with encryption and network isolation
- ❌ Any cloud-based LLM service (not allowed)

---

## Endpoint Validation

### Implementation

Endpoint validation is implemented in `src/elspeth/core/security/approved_endpoints.py` and enforced during plugin initialization.

**Validation Rules:**
1. All external endpoints must match an approved pattern
2. Localhost/loopback addresses are always allowed (local testing)
3. Azure service endpoints must use HTTPS
4. OpenAI public API requires explicit approval for data classification

**Validation Triggers:**
- LLM client initialization (`azure_openai`, `http_openai`)
- Azure Blob datasource/sink initialization
- Configuration validation (via `config_validation.py`)

**Configuration:**
Approved endpoints are defined in:
- Code: `src/elspeth/core/security/approved_endpoints.py`
- Config: `config/security/approved_endpoints.yaml` (organization-specific overrides)

### Bypass Mechanisms

**Development Mode:**
- `ELSPETH_SECURE_MODE=development` disables strict endpoint validation
- Logs warnings instead of raising errors
- **WARNING:** Never use development mode with production data

**Endpoint Override:**
- Environment variable: `ELSPETH_APPROVED_ENDPOINTS` (comma-separated patterns)
- Example: `export ELSPETH_APPROVED_ENDPOINTS="https://custom-llm.internal.company.com,https://*.private-ai.com"`
- Useful for testing new services before adding to code

---

## Compliance Checklist

Before deploying Elspeth in production:

### External Service Approval
- [ ] All external services documented in this file
- [ ] Data flow diagrams reviewed and approved
- [ ] Classification levels assigned to all datasources, LLMs, sinks
- [ ] Endpoint validation enabled (`ELSPETH_SECURE_MODE=strict` or `standard`)

### Azure OpenAI Deployment
- [ ] Azure OpenAI resource provisioned in approved region
- [ ] API keys stored in environment variables (not config files)
- [ ] Audit logging middleware enabled (`audit_logger`)
- [ ] Network isolation configured (Private Link recommended for confidential data)
- [ ] Data residency requirements verified

### OpenAI Public API (if used)
- [ ] Risk assessment completed for data classification
- [ ] Only used for `public` or `internal` data
- [ ] Data retention policy reviewed
- [ ] Alternative (Azure OpenAI, local LLM) considered

### Azure Blob Storage
- [ ] Storage account provisioned with encryption at rest
- [ ] SAS tokens or Managed Identity authentication configured
- [ ] `retain_local=true` for all datasources (STRICT mode requirement)
- [ ] Network isolation configured (Private Link recommended for confidential data)
- [ ] Data retention policy configured

### Configuration Validation
- [ ] All configurations include `security_level` parameters
- [ ] Templates updated with approved endpoints
- [ ] Daily verification script passes (`./scripts/daily-verification.sh`)

---

## Change Control

### Adding New External Services

To add a new external service integration:

1. **Security Review:**
   - Document service purpose, data flow, and classification support
   - Identify security controls (encryption, authentication, audit)
   - Complete risk assessment

2. **Code Implementation:**
   - Implement plugin with PluginContext support
   - Add endpoint validation during initialization
   - Add security_level parameter to schema

3. **Documentation:**
   - Add service to this document (External Service Inventory section)
   - Update data flow diagram
   - Update compliance checklist

4. **Testing:**
   - Write tests for endpoint validation
   - Test with all supported classification levels
   - Verify audit logging and security controls

5. **Approval:**
   - Security team review
   - ATO authority review (if applicable)
   - Add to approved endpoints configuration

### Modifying Endpoint Patterns

Changes to approved endpoint patterns require:

1. Security review and risk assessment
2. Update to `src/elspeth/core/security/approved_endpoints.py`
3. Update to this documentation
4. ATO authority notification (if applicable)

---

## References

- **ATO Work Program:** `/home/john/elspeth/docs/ATO_REMEDIATION_WORK_PROGRAM.md`
- **Security Controls:** `/home/john/elspeth/docs/architecture/security-controls.md`
- **Secure Mode Documentation:** `/home/john/elspeth/src/elspeth/core/security/secure_mode.py`
- **Configuration Validation:** `/home/john/elspeth/src/elspeth/core/config_validation.py`
- **Plugin Catalogue:** `/home/john/elspeth/docs/architecture/plugin-catalogue.md`

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-15 | Claude Code | Initial documentation for MF-4 ATO requirement |
