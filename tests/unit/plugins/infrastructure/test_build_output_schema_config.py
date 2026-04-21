"""Tests for BaseTransform._build_output_schema_config helper."""

from elspeth.contracts.schema import FieldDefinition, SchemaConfig
from elspeth.plugins.transforms.keyword_filter import KeywordFilter


def _make_minimal_transform(declared_fields: frozenset[str] | None = None):
    """Create a minimal transform to test the base class helper.

    Uses KeywordFilter as a concrete BaseTransform subclass
    (simplest available — no external deps, no adds_fields).
    """
    transform = KeywordFilter(
        {
            "fields": "text",
            "blocked_patterns": ["test"],
            "schema": {"mode": "observed"},
        }
    )
    if declared_fields is not None:
        transform.declared_output_fields = declared_fields
    return transform


class TestBuildOutputSchemaConfig:
    def test_merges_base_guaranteed_and_declared_output_fields(self):
        transform = _make_minimal_transform(frozenset({"new_field_a", "new_field_b"}))
        base = SchemaConfig(
            mode="observed",
            fields=None,
            guaranteed_fields=("existing_field",),
        )
        result = transform._build_output_schema_config(base)
        assert frozenset(result.guaranteed_fields) == frozenset({"existing_field", "new_field_a", "new_field_b"})

    def test_empty_declared_output_fields_returns_base_only(self):
        transform = _make_minimal_transform(frozenset())
        base = SchemaConfig(
            mode="observed",
            fields=None,
            guaranteed_fields=("base_field",),
        )
        result = transform._build_output_schema_config(base)
        assert frozenset(result.guaranteed_fields) == frozenset({"base_field"})

    def test_none_base_guaranteed_fields_returns_declared_only(self):
        transform = _make_minimal_transform(frozenset({"output_x"}))
        base = SchemaConfig(mode="observed", fields=None, guaranteed_fields=None)
        result = transform._build_output_schema_config(base)
        assert frozenset(result.guaranteed_fields) == frozenset({"output_x"})

    def test_preserves_mode_and_fields(self):
        fields = (FieldDefinition(name="id", field_type="int", required=True),)
        transform = _make_minimal_transform(frozenset({"extra"}))
        base = SchemaConfig(mode="fixed", fields=fields, guaranteed_fields=None)
        result = transform._build_output_schema_config(base)
        assert result.mode == "fixed"
        assert result.fields == fields

    def test_preserves_audit_fields(self):
        transform = _make_minimal_transform(frozenset({"x"}))
        base = SchemaConfig(
            mode="observed",
            fields=None,
            audit_fields=("audit_a", "audit_b"),
        )
        result = transform._build_output_schema_config(base)
        assert result.audit_fields == ("audit_a", "audit_b")

    def test_preserves_required_fields(self):
        transform = _make_minimal_transform(frozenset({"x"}))
        base = SchemaConfig(
            mode="observed",
            fields=None,
            required_fields=("req_field",),
        )
        result = transform._build_output_schema_config(base)
        assert result.required_fields == ("req_field",)

    def test_keyword_filter_initializes_output_schema_config(self):
        transform = _make_minimal_transform()
        assert transform._output_schema_config is not None
