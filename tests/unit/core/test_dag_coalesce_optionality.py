# tests/unit/core/test_dag_coalesce_optionality.py
"""Tests for field optionality preservation in coalesce union merge schema.

Fix: builder.py union merge was stripping optionality markers from branch
field specs, making all merged fields appear required. Now uses SchemaConfig
and FieldDefinition directly — optionality is a first-class boolean field.
"""

from __future__ import annotations

from elspeth.contracts.schema import FieldDefinition, SchemaConfig
from elspeth.core.dag.models import GraphValidationError


class TestUnionMergeOptionalityPreservation:
    """Tests for optionality in union merge using SchemaConfig objects.

    These simulate the builder's coalesce merge logic to verify that
    FieldDefinition.required flags survive the merge correctly.
    """

    def _merge_schemas(
        self,
        branch_schemas: dict[str, SchemaConfig],
    ) -> SchemaConfig:
        """Simulate the builder's union merge logic with SchemaConfig objects."""
        seen_types: dict[str, tuple[str, bool, str]] = {}
        all_observed = False
        for branch_name, schema_cfg in branch_schemas.items():
            if schema_cfg.is_observed:
                all_observed = True
                break
            if schema_cfg.fields is None:
                continue
            for fd in schema_cfg.fields:
                if fd.name in seen_types:
                    prior_type, _prior_req, prior_branch = seen_types[fd.name]
                    if prior_type != fd.field_type:
                        raise GraphValidationError(f"Type mismatch for {fd.name}")
                    if not fd.required:
                        seen_types[fd.name] = (prior_type, False, prior_branch)
                else:
                    seen_types[fd.name] = (fd.field_type, fd.required, branch_name)

        if all_observed or not seen_types:
            return SchemaConfig(mode="observed", fields=None)
        merged_fields = tuple(FieldDefinition(name=name, field_type=ftype, required=req) for name, (ftype, req, _) in seen_types.items())
        return SchemaConfig(mode="flexible", fields=merged_fields)

    def _get_field(self, schema: SchemaConfig, name: str) -> FieldDefinition:
        """Get a FieldDefinition by name from a SchemaConfig."""
        assert schema.fields is not None
        for fd in schema.fields:
            if fd.name == name:
                return fd
        raise AssertionError(f"Field {name!r} not found in schema")

    def test_optional_field_preserved(self) -> None:
        """Optional field in one branch should remain optional in merged output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"), FieldDefinition("score", "float", required=False)),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"), FieldDefinition("label", "str")),
                ),
            }
        )
        assert self._get_field(result, "score").required is False
        assert self._get_field(result, "id").required is True
        assert self._get_field(result, "label").required is True

    def test_mixed_required_and_optional_yields_optional(self) -> None:
        """Field required in branch A, optional in branch B → optional in output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=True),),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=False),),
                ),
            }
        )
        assert self._get_field(result, "score").required is False

    def test_all_required_stays_required(self) -> None:
        """Field required in ALL branches → required in output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"),),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"),),
                ),
            }
        )
        assert self._get_field(result, "id").required is True

    def test_all_optional_stays_optional(self) -> None:
        """Field optional in ALL branches → optional in output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=False),),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=False),),
                ),
            }
        )
        assert self._get_field(result, "score").required is False
