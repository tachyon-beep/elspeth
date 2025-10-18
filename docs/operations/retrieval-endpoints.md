# Retrieval Endpoint Validation

## Overview

Retrieval components now enforce endpoint allowlists at runtime:

- Azure OpenAI embedders validate the `endpoint` against the certified regex
  pattern for the Australian/public Azure cloud (`*.openai.azure.com`).
  Validation failures raise `ValueError` in STANDARD/STRICT secure modes.
- Azure Cognitive Search clients validate the `endpoint` before instantiating
  `SearchClient`. Only public Azure domains (`*.search.windows.net`) are
  accepted. Rejections are surfaced as `ConfigurationError` with guidance to
  use an approved domain.
- Legacy HTTP/OpenAI clients continue to rely on the central `http_api`
  allowlist (unchanged).

## Extending the Allowlist

If a deployment requires additional Azure endpoints:

1. Submit a change to `src/elspeth/core/security/approved_endpoints.py` adding
   the new regex pattern under the relevant service type (`azure_openai`,
   `azure_search`, or `azure_blob`).
2. Update `tests/test_security_approved_endpoints.py` with approved + rejection
   cases for the new pattern.
3. Run the targeted suite:
   ```bash
   python -m pytest tests/test_security_approved_endpoints.py \
                   tests/test_retrieval_service.py \
                   tests/test_retrieval_providers.py
   ```
4. Document the change in this note and in the release record.

For temporary overrides (e.g., pre-production sandboxes), set the
`ELSPETH_APPROVED_ENDPOINTS` environment variable with a comma-separated list of
regex patterns. This should only be used in DEVELOPMENT secure mode and must
not be promoted to STANDARD/STRICT without formal approval.

## Operator Playbook

| Symptom | Likely Cause | Remediation |
| ------- | ------------ | ----------- |
| `ConfigurationError: azure_search retriever endpoint validation failed` | Endpoint outside approved domains | Verify Azure Search resource URL (should end with `.search.windows.net`, `.search.azure.us`, or `.search.azure.cn`). Update config or submit allowlist change. |
| `ValueError: Endpoint '...' is not approved for service type 'azure_openai'` | Azure OpenAI endpoint mismatch | Ensure Azure portal shows matching host; update config or submit allowlist change. |
| Validation passes in DEVELOPMENT but fails in STANDARD | Custom endpoint added via `ELSPETH_APPROVED_ENDPOINTS` env var | Promote the regex to the codebase before switching to STANDARD/STRICT modes. |

## Timeouts and Retries

Retrieval components support bounded operations to avoid hangs during incidents:

- pgvector (PostgreSQL):
  - `connect_timeout` can be supplied to `PgVectorQueryClient` (either as a DSN parameter or via the new `connect_timeout` option). Example DSN: `postgresql://host/db?connect_timeout=5`.
  - Impact: prevents long connection stalls; recommended 3–10s in production.

- Azure Cognitive Search:
  - `request_timeout` (alias `timeout`) can be provided in the retriever options; it is passed to `SearchClient.search(timeout=...)`.
  - Impact: bounds per-query latency; recommended initial value 10–30s depending on index size.

Note: The generic HTTP/OpenAI client already applies a per-request `timeout` and bounded retries (429/5xx) with exponential backoff.

## Audit Evidence

- Tests: `tests/test_retrieval_service.py::test_create_embedder_validates_azure_endpoint`,
  `tests/test_retrieval_providers.py::test_create_query_client_validates_azure_endpoint`,
  `tests/test_security_approved_endpoints.py::test_azure_search_approved_endpoints`.
- Implementation: `src/elspeth/retrieval/service.py`, `src/elspeth/retrieval/providers.py`,
  `src/elspeth/core/security/approved_endpoints.py`.
