"""Dataverse source plugin for ELSPETH.

Loads rows from Microsoft Dataverse entities via OData v4 REST API.
Supports structured OData queries and FetchXML queries with pagination.

IMPORTANT: Sources use allow_coercion=True to normalize external data.
This is the ONLY place in the pipeline where coercion is allowed.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Self

import structlog
from pydantic import Field, ValidationError, field_validator, model_validator

from elspeth.contracts import CallStatus, CallType, Determinism, PluginSchema, SourceRow
from elspeth.contracts.call_data import RawCallPayload
from elspeth.contracts.contexts import LifecycleContext, SourceContext
from elspeth.contracts.errors import AuditIntegrityError, FrameworkBugError
from elspeth.contracts.events import ExternalCallCompleted
from elspeth.core.canonical import stable_hash
from elspeth.plugins.infrastructure.base import BaseSource
from elspeth.plugins.infrastructure.clients.dataverse import (
    DataverseAuthConfig,
    DataverseClient,
    DataverseClientError,
    DataversePageResponse,
    validate_additional_domain,
)
from elspeth.plugins.infrastructure.clients.fingerprinting import fingerprint_headers
from elspeth.plugins.infrastructure.config_base import DataPluginConfig
from elspeth.plugins.infrastructure.schema_factory import create_schema_from_config
from elspeth.plugins.sources.field_normalization import (
    NORMALIZATION_ALGORITHM_VERSION,
    FieldResolution,
    normalize_field_name,
    resolve_field_names,
)

if TYPE_CHECKING:
    from elspeth.contracts.contract_builder import ContractBuilder

logger = structlog.get_logger(__name__)

# OData annotation prefixes to strip from row data
_ODATA_ANNOTATION_PATTERN = re.compile(r"^@odata\.|@Microsoft\.Dynamics\.CRM\.")
_FORMATTED_VALUE_SUFFIX = "@OData.Community.Display.V1.FormattedValue"


class DataverseSourceConfig(DataPluginConfig):
    """Configuration for Dataverse source plugin.

    Extends DataPluginConfig which requires schema configuration.
    Unlike file-based sources, does not extend PathConfig (no local file path).
    """

    environment_url: str = Field(
        ...,
        description="Dataverse environment URL (e.g., https://myorg.crm.dynamics.com)",
    )
    auth: DataverseAuthConfig = Field(
        ...,
        description="Authentication configuration",
    )
    api_version: str = Field(
        default="v9.2",
        description="Dataverse Web API version",
    )
    on_validation_failure: str = Field(
        ...,
        description="Sink name for non-conformant rows, or 'discard' for explicit drop",
    )

    # Structured query mode
    entity: str | None = Field(
        default=None,
        description="Entity logical name (e.g., 'contact')",
    )
    select: list[str] | None = Field(
        default=None,
        description="$select fields (None = all)",
    )
    filter: str | None = Field(
        default=None,
        description="$filter expression (static OData only)",
    )
    orderby: str | None = Field(
        default=None,
        description="$orderby expression",
    )
    top: int | None = Field(
        default=None,
        description="$top limit (None = all records)",
    )

    # FetchXML query mode
    fetch_xml: str | None = Field(
        default=None,
        description="Raw FetchXML string",
    )

    # Field handling
    normalize_fields: bool = Field(
        default=True,
        description="Normalize Dataverse logical names to Python identifiers",
    )
    field_mapping: dict[str, str] | None = Field(
        default=None,
        description="Manual field name overrides",
    )
    include_formatted_values: bool = Field(
        default=False,
        description="Preserve Dataverse formatted value annotations",
    )

    # Additional SSRF domain patterns (deployment-level)
    additional_domains: list[str] | None = Field(
        default=None,
        description="Additional Dataverse domain patterns for SSRF allowlist",
    )

    @field_validator("environment_url")
    @classmethod
    def validate_environment_url_https(cls, v: str) -> str:
        """HTTPS required. Bearer tokens sent over plain HTTP would be unencrypted."""
        parsed = urllib.parse.urlparse(v)
        if parsed.scheme != "https":
            raise ValueError(
                f"environment_url must use HTTPS scheme, got {parsed.scheme!r}. "
                f"Bearer tokens are sent in Authorization headers — HTTP would expose them in transit."
            )
        return v

    @field_validator("additional_domains")
    @classmethod
    def validate_additional_domains(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for pattern in v:
                validate_additional_domain(pattern)
        return v

    @model_validator(mode="after")
    def validate_query_mode(self) -> Self:
        has_structured = self.entity is not None
        has_fetchxml = self.fetch_xml is not None
        if has_structured == has_fetchxml:
            raise ValueError("Specify exactly one of: entity (structured query) or fetch_xml")
        if not has_structured and any(f is not None for f in (self.select, self.filter, self.orderby, self.top)):
            raise ValueError("select/filter/orderby/top require entity (structured query mode)")
        return self

    @field_validator("on_validation_failure")
    @classmethod
    def validate_on_validation_failure(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("on_validation_failure must be a sink name or 'discard'")
        return v.strip()

    @field_validator("fetch_xml")
    @classmethod
    def validate_fetch_xml_syntax(cls, v: str | None) -> str | None:
        """Validate FetchXML is parseable XML at config time.

        Structural validation only — broken FetchXML can never produce valid
        results for any row. Analogous to TemplateSyntaxError for Jinja2.
        """
        if v is not None:
            try:
                root = ET.fromstring(v)
            except ET.ParseError as exc:
                raise ValueError(
                    f"fetch_xml contains invalid XML syntax: {exc}. A broken FetchXML query can never produce valid results."
                ) from exc
            if root.tag != "fetch":
                raise ValueError(f"FetchXML root element must be <fetch>, got <{root.tag}>.")
        return v


# Rebuild model to resolve forward references for dynamic module loading
DataverseSourceConfig.model_rebuild()


class DataverseSource(BaseSource):
    """Load rows from Microsoft Dataverse via OData v4 REST API.

    Supports structured OData queries ($select, $filter, $orderby, $top)
    and FetchXML queries with automatic pagination. All responses are
    validated at the Tier 3 boundary (JSON parse, NaN/Infinity rejection).
    """

    name = "dataverse"
    determinism = Determinism.EXTERNAL_CALL  # Live REST API, not static file read

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = DataverseSourceConfig.from_dict(config)

        # Store config
        self._environment_url = cfg.environment_url
        self._auth_config = cfg.auth
        self._api_version = cfg.api_version
        self._entity = cfg.entity
        self._select = cfg.select
        self._filter = cfg.filter
        self._orderby = cfg.orderby
        self._top = cfg.top
        self._fetch_xml = cfg.fetch_xml
        self._normalize_fields = cfg.normalize_fields
        self._field_mapping = cfg.field_mapping
        self._include_formatted_values = cfg.include_formatted_values
        self._additional_domains = tuple(cfg.additional_domains) if cfg.additional_domains else ()
        self._on_validation_failure = cfg.on_validation_failure

        # Store schema config
        self._schema_config = cfg.schema_config

        # CRITICAL: allow_coercion=True for sources (external data boundary)
        self._schema_class: type[PluginSchema] = create_schema_from_config(
            self._schema_config,
            "DataverseRowSchema",
            allow_coercion=True,
        )
        self.output_schema = self._schema_class

        # Contract setup — Dataverse responses are JSON (no CSV header resolution needed)
        from elspeth.contracts.contract_builder import ContractBuilder
        from elspeth.contracts.schema_contract_factory import create_contract_from_config

        initial_contract = create_contract_from_config(self._schema_config)
        if initial_contract.locked:
            self.set_schema_contract(initial_contract)
            self._contract_builder: ContractBuilder | None = None
        else:
            self._contract_builder = ContractBuilder(initial_contract)

        # Field resolution (populated during load)
        self._field_resolution: FieldResolution | None = None

        # Lazy-constructed client (needs lifecycle context)
        self._client: DataverseClient | None = None
        self._telemetry_emit: Any = None
        self._run_id: str | None = None

    def on_start(self, ctx: LifecycleContext) -> None:
        """Construct credential and DataverseClient.

        Called before load() — acquires resources from lifecycle context.
        """
        self._run_id = ctx.run_id
        self._telemetry_emit = ctx.telemetry_emit

        # Construct credential (azure-identity) — validates early
        from azure.identity import ClientSecretCredential, ManagedIdentityCredential

        credential: ClientSecretCredential | ManagedIdentityCredential
        if self._auth_config.method == "service_principal":
            # Pydantic validator guarantees these are non-None for service_principal
            assert self._auth_config.tenant_id is not None
            assert self._auth_config.client_id is not None
            assert self._auth_config.client_secret is not None
            credential = ClientSecretCredential(
                tenant_id=self._auth_config.tenant_id,
                client_id=self._auth_config.client_id,
                client_secret=self._auth_config.client_secret,
            )
        else:
            credential = ManagedIdentityCredential()

        # Obtain rate limiter (with null guard per spec)
        limiter = ctx.rate_limit_registry.get_limiter("dataverse_source") if ctx.rate_limit_registry is not None else None

        # Construct DataverseClient
        self._client = DataverseClient(
            environment_url=self._environment_url,
            credential=credential,
            api_version=self._api_version,
            limiter=limiter,
            additional_domains=self._additional_domains,
        )

        # Validate entity exists via metadata query (structured mode only).
        # Catches typos in entity names at pipeline startup rather than on
        # first page fetch. FetchXML mode skips this — the entity name is
        # embedded in the XML and validated by Dataverse on first query.
        if self._entity is not None:
            self._validate_entity_exists()

    def _validate_entity_exists(self) -> None:
        """Validate that the configured entity exists in Dataverse metadata.

        Issues a lightweight metadata request to check entity availability.
        Failures are non-fatal — the entity may exist but the metadata
        endpoint may be restricted. Logs a warning and continues.
        """
        assert self._client is not None
        metadata_url = (
            f"{self._environment_url.rstrip('/')}/api/data/{self._api_version}"
            f"/EntityDefinitions(LogicalName='{self._entity}')?$select=LogicalName"
        )
        try:
            self._client.get_page(metadata_url)
        except DataverseClientError as e:
            if e.status_code == 404:
                raise DataverseClientError(
                    f"Entity '{self._entity}' not found in Dataverse. Check the entity logical name in your pipeline config.",
                    retryable=False,
                    status_code=404,
                ) from e
            if e.status_code == 403:
                # 403 is non-fatal — entity may exist but metadata access
                # is restricted. Log and continue.
                logger.warning(
                    "entity_metadata_check_forbidden",
                    entity=self._entity,
                    error=str(e),
                    status_code=403,
                )
            else:
                # 5xx, network errors, etc. — re-raise. Silently continuing
                # after a server error means the pipeline proceeds with
                # potentially invalid entity config.
                raise

    def _build_query_url(self) -> str:
        """Build the initial OData query URL for structured queries."""
        url = f"{self._environment_url.rstrip('/')}/api/data/{self._api_version}/{self._entity}"

        params: list[str] = []
        if self._select:
            params.append(f"$select={','.join(self._select)}")
        if self._filter:
            params.append(f"$filter={self._filter}")
        if self._orderby:
            params.append(f"$orderby={self._orderby}")
        if self._top is not None:
            params.append(f"$top={self._top}")

        if params:
            url += "?" + "&".join(params)

        return url

    def _strip_odata_metadata(self, row: dict[str, Any]) -> dict[str, Any]:
        """Strip OData annotations from row data.

        Optionally preserves formatted values as additional fields.

        Args:
            row: Raw row from Dataverse response

        Returns:
            Cleaned row with OData metadata removed
        """
        cleaned: dict[str, Any] = {}
        formatted_values: dict[str, str] = {}

        for key, value in row.items():
            # Preserve formatted values if requested
            if self._include_formatted_values and key.endswith(_FORMATTED_VALUE_SUFFIX):
                # Extract field name: "statecode@OData.Community.Display.V1.FormattedValue" → "statecode"
                field_name = key[: -len(_FORMATTED_VALUE_SUFFIX)]
                formatted_values[field_name] = value
                continue

            # Strip OData annotations
            if _ODATA_ANNOTATION_PATTERN.match(key):
                continue

            cleaned[key] = value

        # Merge formatted values with __formatted suffix
        if self._include_formatted_values:
            for field_name, formatted in formatted_values.items():
                formatted_key = f"{field_name}__formatted"
                # Collision detection
                if formatted_key in cleaned:
                    raise ValueError(
                        f"Formatted value field name collision: both '{formatted_key}' and "
                        f"'{field_name}' with formatted value annotation exist in the entity. "
                        f"Disable include_formatted_values or rename the conflicting field."
                    )
                cleaned[formatted_key] = formatted

        return cleaned

    def _normalize_row_fields(
        self,
        row: dict[str, Any],
        is_first_row: bool,
    ) -> dict[str, Any]:
        """Normalize field names and apply field mapping.

        On first row, creates the field resolution mapping.

        Args:
            row: Row with original field names
            is_first_row: Whether this is the first row being processed

        Returns:
            Row with normalized field names
        """
        if is_first_row or self._field_resolution is None:
            raw_headers = list(row.keys())
            self._field_resolution = resolve_field_names(
                raw_headers=raw_headers,
                normalize_fields=self._normalize_fields,
                field_mapping=self._field_mapping,
                columns=None,
            )

        # Apply resolution mapping.
        # Tier 3: Dataverse responses may include fields not in the first row
        # (sparse entities, dynamic attributes). Normalize new fields using the
        # same algorithm rather than passing them through raw — inconsistent
        # normalization would break downstream template references.
        # Schema validation (lines below) quarantines rows with unexpected fields.
        mapping = self._field_resolution.resolution_mapping
        result: dict[str, Any] = {}
        for k, v in row.items():
            normalized_name = mapping.get(k)
            if normalized_name is None:
                # Field not in initial mapping — normalize individually
                normalized_name = normalize_field_name(k) if self._normalize_fields else k
            result[normalized_name] = v
        return result

    def _emit_telemetry(
        self,
        *,
        ctx: SourceContext,
        status: CallStatus,
        latency_ms: float,
        request_data: dict[str, Any],
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Emit ExternalCallCompleted telemetry after successful audit recording.

        Telemetry fires AFTER audit (primacy rule). Failures are logged,
        not propagated — telemetry must never corrupt the audit trail.
        """
        if self._telemetry_emit is None:
            return
        try:
            assert self._run_id is not None, "run_id is None during telemetry emission — on_start() must set _run_id before load()"
            req_payload = RawCallPayload(request_data)
            resp_payload = RawCallPayload(response_data) if response_data else None
            self._telemetry_emit(
                ExternalCallCompleted(
                    timestamp=datetime.now(UTC),
                    run_id=self._run_id,
                    call_type=CallType.HTTP,
                    provider="dataverse",
                    status=status,
                    latency_ms=latency_ms,
                    operation_id=ctx.operation_id,
                    request_hash=stable_hash(request_data),
                    response_hash=stable_hash(response_data) if response_data else None,
                    request_payload=req_payload,
                    response_payload=resp_payload,
                )
            )
        except (FrameworkBugError, AuditIntegrityError):
            raise
        except Exception as tel_err:
            logger.warning(
                "telemetry_emit_failed",
                error=str(tel_err),
                error_type=type(tel_err).__name__,
                call_type="http",
                exc_info=True,
            )

    def _record_page_call(
        self,
        ctx: SourceContext,
        *,
        url: str,
        page: DataversePageResponse | None = None,
        error: DataverseClientError | None = None,
        error_reason: str | None = None,
    ) -> None:
        """Record a page fetch in the audit trail, then emit telemetry.

        Audit fires first (primacy), telemetry fires second (best-effort).

        Args:
            ctx: Source context for record_call
            url: URL that was requested
            page: Response page (for success)
            error: DataverseClientError (for errors)
            error_reason: Additional error context
        """
        if page is not None:
            request_data = {
                "method": "GET",
                "url": url,
                "headers": fingerprint_headers(page.request_headers),
            }
            response_data = {
                "status_code": page.status_code,
                "row_count": len(page.rows),
            }
            try:
                ctx.record_call(
                    call_type=CallType.HTTP,
                    status=CallStatus.SUCCESS,
                    request_data=request_data,
                    response_data=response_data,
                    latency_ms=page.latency_ms,
                    provider="dataverse",
                )
            except Exception as exc:
                raise AuditIntegrityError(
                    f"Failed to record successful page fetch to audit trail "
                    f"(url={url!r}). "
                    f"Page fetch completed but audit record is missing."
                ) from exc
            self._emit_telemetry(
                ctx=ctx,
                status=CallStatus.SUCCESS,
                latency_ms=page.latency_ms,
                request_data=request_data,
                response_data=response_data,
            )
        elif error is not None:
            request_data = {"method": "GET", "url": url}
            error_data = {
                "error_type": type(error).__name__,
                "message": str(error),
                "status_code": error.status_code,
                "reason": error_reason,
            }
            ctx.record_call(
                call_type=CallType.HTTP,
                status=CallStatus.ERROR,
                request_data=request_data,
                error=error_data,
                latency_ms=error.latency_ms,
                provider="dataverse",
            )
            if error.latency_ms is not None:
                self._emit_telemetry(
                    ctx=ctx,
                    status=CallStatus.ERROR,
                    latency_ms=error.latency_ms,
                    request_data=request_data,
                )

    def load(self, ctx: SourceContext) -> Iterator[SourceRow]:
        """Load rows from Dataverse via OData pagination.

        Yields SourceRow.valid() for validated rows and
        SourceRow.quarantined() for rows failing schema validation.
        """
        # Instance-level flag — NOT reset per page (spec: schema lock scoping)
        self._first_valid_row_processed = False
        is_first_row = True
        pages_fetched = 0
        rows_yielded = 0
        quarantine_count = 0

        # Client must be constructed by on_start() before load()
        assert self._client is not None, "on_start() must be called before load()"

        try:
            if self._entity is not None:
                # Structured OData query
                url = self._build_query_url()
                page_iterator = self._client.paginate_odata(url)
            else:
                # FetchXML query
                assert self._fetch_xml is not None, "config validator ensures entity or fetch_xml"
                # Extract entity name from FetchXML
                root = ET.fromstring(self._fetch_xml)
                entity_elem = root.find("entity")
                if entity_elem is None:
                    raise RuntimeError("FetchXML is missing <entity> element — cannot determine entity name for URL")
                entity_name = entity_elem.get("name")
                if entity_name is None:
                    raise RuntimeError("FetchXML <entity> element missing 'name' attribute")
                page_iterator = self._client.paginate_fetchxml(entity_name, self._fetch_xml)

            for page in page_iterator:
                pages_fetched += 1
                current_url = self._build_query_url() if self._entity else f"(FetchXML page {pages_fetched})"

                # Record successful page fetch
                self._record_page_call(ctx, url=current_url, page=page)

                # Process rows
                for raw_row in page.rows:
                    # Strip OData metadata
                    try:
                        cleaned_row = self._strip_odata_metadata(raw_row)
                    except ValueError as e:
                        # Formatted value collision — quarantine
                        quarantine_count += 1
                        ctx.record_validation_error(
                            row=raw_row,
                            error=str(e),
                            schema_mode="odata_strip",
                            destination=self._on_validation_failure,
                        )
                        if self._on_validation_failure != "discard":
                            yield SourceRow.quarantined(
                                row=raw_row,
                                error=str(e),
                                destination=self._on_validation_failure,
                            )
                        continue

                    # Normalize field names
                    normalized_row = self._normalize_row_fields(cleaned_row, is_first_row)
                    is_first_row = False

                    # Validate against schema
                    try:
                        validated = self._schema_class.model_validate(normalized_row)
                        validated_row = validated.to_row()
                    except ValidationError as e:
                        quarantine_count += 1
                        ctx.record_validation_error(
                            row=normalized_row,
                            error=str(e),
                            schema_mode="validation",
                            destination=self._on_validation_failure,
                        )
                        if self._on_validation_failure != "discard":
                            yield SourceRow.quarantined(
                                row=normalized_row,
                                error=str(e),
                                destination=self._on_validation_failure,
                            )
                        continue

                    # Lock contract on first valid row (FLEXIBLE/OBSERVED)
                    if not self._first_valid_row_processed and self._contract_builder is not None:
                        resolution_map: Mapping[str, str]
                        if self._field_resolution is not None:
                            resolution_map = self._field_resolution.resolution_mapping
                        else:
                            resolution_map = {k: k for k in validated_row}

                        self._contract_builder.process_first_row(validated_row, resolution_map)
                        self.set_schema_contract(self._contract_builder.contract)
                        self._first_valid_row_processed = True

                    rows_yielded += 1
                    contract = self._contract_builder.contract if self._contract_builder is not None else self.get_schema_contract()
                    yield SourceRow.valid(validated_row, contract=contract)

        except DataverseClientError as e:
            # Record the error in audit trail with the typed error_category
            # set at the raise site — no fragile string-matching on messages.
            current_url = self._build_query_url() if self._entity else "(FetchXML)"
            self._record_page_call(
                ctx,
                url=current_url,
                error=e,
                error_reason=e.error_category,
            )
            # 401 with retryable=True: reconstruct credential before engine retry
            if e.status_code == 401 and e.retryable:
                assert self._client is not None, "on_start() must be called before load()"
                self._client.reconstruct_credential(self._auth_config)
            raise

        # Force-lock contract if no valid rows were yielded across ALL pages
        if not self._first_valid_row_processed and self._contract_builder is not None:
            self.set_schema_contract(self._contract_builder.contract.with_locked())

        # Store counters for on_complete telemetry
        self._pages_fetched = pages_fetched
        self._rows_yielded = rows_yielded
        self._quarantine_count = quarantine_count

    def on_complete(self, ctx: LifecycleContext) -> None:
        """Source statistics available via stored counters.

        No SourceCompleted telemetry event type exists yet (AzureBlobSource
        has the same gap). Counters are stored as instance attributes by
        load() for diagnostic access. When a SourceCompleted event is added
        to contracts/events.py, emit here via ctx.telemetry_emit.
        """
        # Counters stored by load(): _pages_fetched, _rows_yielded, _quarantine_count

    def get_field_resolution(self) -> tuple[Mapping[str, str], str | None] | None:
        """Return field normalization mapping for audit trail recovery."""
        if self._field_resolution is None:
            return None
        return (
            self._field_resolution.resolution_mapping,
            NORMALIZATION_ALGORITHM_VERSION,
        )

    def close(self) -> None:
        """Release DataverseClient resources."""
        if self._client is not None:
            self._client.close()
            self._client = None
