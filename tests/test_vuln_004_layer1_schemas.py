"""
VULN-004 Layer 1: Schema Enforcement Tests

SECURITY: Verify all plugin schemas reject forbidden security policy fields.

ADR-002-B mandates security policy (security_level, allow_downgrade, max_operating_level)
is declared in plugin code and immutable. YAML configuration must NOT be able to override.

Layer 1: Schema validation (additionalProperties: false) prevents YAML from containing
these fields at parse time.
"""

import pytest
import jsonschema

# Import plugin schemas from registries (where they're actually defined)
from elspeth.core.registries.datasource import (
    _CSV_DATASOURCE_SCHEMA as CSV_LOCAL_SCHEMA,
    _CSV_BLOB_DATASOURCE_SCHEMA as CSV_BLOB_SCHEMA,
    _BLOB_DATASOURCE_SCHEMA as BLOB_SCHEMA,
)
from elspeth.core.registries.llm import (
    _HTTP_OPENAI_SCHEMA as OPENAI_HTTP_SCHEMA,
    _AZURE_OPENAI_SCHEMA as AZURE_OPENAI_SCHEMA,
    _MOCK_LLM_SCHEMA as MOCK_LLM_SCHEMA,
)
from elspeth.core.registries.sink import (
    _CSV_SINK_SCHEMA as CSV_SINK_SCHEMA,
    _EXCEL_SINK_SCHEMA as EXCEL_SINK_SCHEMA,
)


class TestLayer1SchemaEnforcement:
    """VULN-004 Layer 1: Schema must reject security policy fields in YAML."""

    # Forbidden fields per ADR-002-B
    FORBIDDEN_FIELDS = ["security_level", "allow_downgrade", "max_operating_level"]

    # Test cases: (schema, plugin_name, minimal_valid_config)
    SCHEMA_TEST_CASES = [
        # Datasources (require 'retain_local' per schema)
        (CSV_LOCAL_SCHEMA, "csv_local", {"path": "/data/test.csv", "retain_local": False}),
        (CSV_BLOB_SCHEMA, "csv_blob", {"path": "/data/test.csv", "retain_local": False}),
        (BLOB_SCHEMA, "blob", {"config_path": "/config/blob.yaml", "retain_local": False}),
        # LLM clients
        (OPENAI_HTTP_SCHEMA, "openai_http", {
            "api_base": "https://api.openai.com/v1",  # Required field
            "api_key": "sk-test123",
            "model": "gpt-4"
        }),
        (AZURE_OPENAI_SCHEMA, "azure_openai", {
            "config": {  # Required nested config object
                "azure_endpoint": "https://test.openai.azure.com",
                "api_key": "test-key",
                "api_version": "2024-02-01",
                "deployment": "gpt-4",
            }
        }),
        (MOCK_LLM_SCHEMA, "mock_llm", {}),
        # Sinks
        (CSV_SINK_SCHEMA, "csv_sink", {"path": "/output/results.csv"}),
        (EXCEL_SINK_SCHEMA, "excel_sink", {"base_path": "/output"}),
    ]

    @pytest.mark.parametrize("schema,plugin_name,valid_config", SCHEMA_TEST_CASES)
    @pytest.mark.parametrize("forbidden_field", FORBIDDEN_FIELDS)
    def test_schema_rejects_forbidden_field(self, schema, plugin_name, valid_config, forbidden_field):
        """SECURITY: All plugin schemas must reject security policy fields (VULN-004 Layer 1).

        ADR-002-B: Security policy is immutable and declared in plugin code, not YAML.
        Schema validation is the first line of defense against configuration override attacks.
        """
        # Create invalid config with forbidden field
        invalid_config = {**valid_config, forbidden_field: "INVALID_VALUE"}

        # Schema should reject with additionalProperties error
        with pytest.raises(jsonschema.ValidationError, match="additionalProperties"):
            jsonschema.validate(invalid_config, schema)

    @pytest.mark.parametrize("schema,plugin_name,valid_config", SCHEMA_TEST_CASES)
    def test_schema_accepts_valid_config(self, schema, plugin_name, valid_config):
        """Verify legitimate configuration still validates after Layer 1 enforcement."""
        # Valid config should pass schema validation
        try:
            jsonschema.validate(valid_config, schema)
        except jsonschema.ValidationError as e:
            pytest.fail(f"Schema {plugin_name} rejected valid config: {e.message}")

    def test_csv_local_schema_specific(self):
        """Explicit test for CSV local datasource (most common)."""
        invalid_config = {
            "path": "/data/test.csv",
            "retain_local": False,
            "security_level": "SECRET",  # ⚠️ Attack attempt
        }

        with pytest.raises(jsonschema.ValidationError, match="additionalProperties"):
            jsonschema.validate(invalid_config, CSV_LOCAL_SCHEMA)

    def test_multiple_forbidden_fields_rejected(self):
        """Verify schema rejects config with multiple forbidden fields."""
        invalid_config = {
            "path": "/data/test.csv",
            "retain_local": False,
            "security_level": "SECRET",
            "allow_downgrade": True,
            "max_operating_level": "TOP_SECRET",
        }

        with pytest.raises(jsonschema.ValidationError, match="additionalProperties"):
            jsonschema.validate(invalid_config, CSV_LOCAL_SCHEMA)
