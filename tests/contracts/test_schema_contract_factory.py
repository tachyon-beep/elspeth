"""Tests for SchemaContract factory from SchemaConfig."""

from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract_factory import (
    create_contract_from_config,
    map_schema_mode,
)


class TestMapSchemaMode:
    """Test mapping SchemaConfig modes to SchemaContract modes."""

    def test_strict_maps_to_fixed(self) -> None:
        """strict mode maps to FIXED."""
        assert map_schema_mode("strict") == "FIXED"

    def test_free_maps_to_flexible(self) -> None:
        """free mode maps to FLEXIBLE."""
        assert map_schema_mode("free") == "FLEXIBLE"

    def test_none_maps_to_observed(self) -> None:
        """None (dynamic) maps to OBSERVED."""
        assert map_schema_mode(None) == "OBSERVED"


class TestCreateContractFromConfig:
    """Test creating SchemaContract from SchemaConfig."""

    def test_dynamic_schema_creates_observed_contract(self) -> None:
        """Dynamic schema creates unlocked OBSERVED contract."""
        config = SchemaConfig.from_dict({"fields": "dynamic"})
        contract = create_contract_from_config(config)

        assert contract.mode == "OBSERVED"
        assert contract.locked is False
        assert len(contract.fields) == 0

    def test_strict_schema_creates_fixed_contract(self) -> None:
        """Strict schema creates FIXED contract with declared fields."""
        config = SchemaConfig.from_dict(
            {
                "mode": "strict",
                "fields": ["id: int", "name: str"],
            }
        )
        contract = create_contract_from_config(config)

        assert contract.mode == "FIXED"
        assert len(contract.fields) == 2
        # Fields are declared and required
        id_field = next(f for f in contract.fields if f.normalized_name == "id")
        assert id_field.python_type is int
        assert id_field.required is True
        assert id_field.source == "declared"

    def test_free_schema_creates_flexible_contract(self) -> None:
        """Free schema creates FLEXIBLE contract."""
        config = SchemaConfig.from_dict(
            {
                "mode": "free",
                "fields": ["id: int"],
            }
        )
        contract = create_contract_from_config(config)

        assert contract.mode == "FLEXIBLE"

    def test_optional_field_not_required(self) -> None:
        """Optional field (?) has required=False."""
        config = SchemaConfig.from_dict(
            {
                "mode": "strict",
                "fields": ["id: int", "note: str?"],
            }
        )
        contract = create_contract_from_config(config)

        note_field = next(f for f in contract.fields if f.normalized_name == "note")
        assert note_field.required is False

    def test_field_type_mapping(self) -> None:
        """Field types map correctly to Python types."""
        config = SchemaConfig.from_dict(
            {
                "mode": "strict",
                "fields": [
                    "a: int",
                    "b: str",
                    "c: float",
                    "d: bool",
                    "e: any",
                ],
            }
        )
        contract = create_contract_from_config(config)

        type_map = {f.normalized_name: f.python_type for f in contract.fields}
        assert type_map["a"] is int
        assert type_map["b"] is str
        assert type_map["c"] is float
        assert type_map["d"] is bool
        # 'any' type maps to object (base type)
        assert type_map["e"] is object

    def test_explicit_contract_is_locked(self) -> None:
        """Explicit schemas (strict/free) start locked."""
        config = SchemaConfig.from_dict(
            {
                "mode": "strict",
                "fields": ["id: int"],
            }
        )
        contract = create_contract_from_config(config)

        # Explicit schemas have complete type info - locked immediately
        assert contract.locked is True

    def test_dynamic_contract_is_unlocked(self) -> None:
        """Dynamic schemas start unlocked (types inferred from first row)."""
        config = SchemaConfig.from_dict({"fields": "dynamic"})
        contract = create_contract_from_config(config)

        assert contract.locked is False
