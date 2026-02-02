# Unified Schema Contracts Design

**Date:** 2026-02-02
**Status:** Draft - Pending Review
**Related Issues:** elspeth-rapid-500, elspeth-rapid-m76

## Problem Statement

ELSPETH currently has two related problems:

1. **Type information lost:** We generate typed Pydantic models from `SchemaConfig`, validate data, then immediately discard type information by calling `model_dump()` → `dict[str, Any]`.

2. **Original field names lost:** Sources normalize messy headers (e.g., `'Important - Data !!'` → `important_data`), but template authors must learn normalized names. Original names are needed for template UX and sink header restoration.

These problems share a root cause: **metadata discarded at the source boundary**.

## Design Goals

1. **Preserve type information** through the pipeline (not just at validation)
2. **Preserve original field names** alongside normalized names
3. **Support dual-name access** in templates (both original and normalized work)
4. **Maintain audit trail integrity** (full traceability of field mappings)
5. **Enable infer-and-lock** for dynamic schemas (types locked on first observation)

## Schema Modes

Three distinct modes with clear semantics:

| Mode | Declared Fields | Extras | Type Enforcement |
|------|----------------|--------|------------------|
| **FIXED** | Required | Rejected | Strict on declared |
| **FLEXIBLE** | Required minimum | Allowed (infer-and-lock) | Strict on declared + inferred |
| **DYNAMIC** | None | All fields are "extra" | Infer-and-lock all |

Mapping from current modes:
- `strict` → **FIXED** (contract is complete, no extras)
- `free` → **FLEXIBLE** (contract is minimum guarantee, extras OK)
- `dynamic` → **DYNAMIC** (contract discovered at runtime)

### Infer-and-Lock Semantics

For FLEXIBLE and DYNAMIC modes:
- First row defines field types for any "extra" fields
- Types are locked for the duration of the run
- Subsequent rows with type violations → quarantine sink
- New fields can still appear (be cool about it), but once seen, they're locked

## Core Data Structures

### FieldContract

Represents a single field in a schema contract:

```python
@dataclass(frozen=True, slots=True)
class FieldContract:
    """A field in the schema contract.

    Immutable after creation - type locking means no mutation.
    """
    normalized_name: str                           # Dict key: "important_data"
    original_name: str                             # Display: "'Important - Data !!'"
    python_type: type                              # int, str, float, bool, Any (primitives only!)
    required: bool                                 # Must be present in row?
    source: Literal["declared", "inferred"]        # Config-time vs runtime discovery
```

### SchemaContract

The full contract for a node, including name resolution:

```python
def _normalize_type_for_contract(value: Any) -> type:
    """Convert numpy/pandas types to Python primitives for contract storage.

    This is critical because `type(numpy.int64(42))` returns `numpy.int64`,
    not `int`. Contracts must store primitive types for consistent validation.
    """
    if value is None:
        return type(None)  # NoneType

    # Handle numpy types (if numpy is available)
    type_name = type(value).__name__
    numpy_to_primitive = {
        "int8": int, "int16": int, "int32": int, "int64": int,
        "uint8": int, "uint16": int, "uint32": int, "uint64": int,
        "float16": float, "float32": float, "float64": float,
        "bool_": bool,
        "str_": str,
    }
    if type_name in numpy_to_primitive:
        return numpy_to_primitive[type_name]

    # Handle pandas Timestamp -> datetime
    if type_name == "Timestamp":
        from datetime import datetime
        return datetime

    # Already a primitive
    return type(value)


@dataclass(frozen=True, slots=True)
class SchemaContract:
    """Immutable schema contract for a node.

    Uses frozen dataclass pattern - all "mutations" return new instances.
    This ensures contracts are safe to share across checkpoint boundaries.
    """
    mode: Literal["FIXED", "FLEXIBLE", "DYNAMIC"]
    fields: tuple[FieldContract, ...]              # Immutable sequence
    locked: bool = False                           # True after first row processed

    # Computed indices (populated by __post_init__)
    _by_normalized: dict[str, FieldContract] = field(default_factory=dict, repr=False)
    _by_original: dict[str, str] = field(default_factory=dict, repr=False)  # original -> normalized

    def __post_init__(self) -> None:
        # Build O(1) lookup indices (bypassing frozen via object.__setattr__)
        by_norm = {fc.normalized_name: fc for fc in self.fields}
        by_orig = {fc.original_name: fc.normalized_name for fc in self.fields}
        object.__setattr__(self, "_by_normalized", by_norm)
        object.__setattr__(self, "_by_original", by_orig)

    def resolve_name(self, key: str) -> str:
        """Resolve original or normalized name to normalized name.

        O(1) lookup via precomputed indices.
        Enables dual-name access: both original and normalized names work.
        """
        if key in self._by_normalized:
            return key  # Already normalized
        if key in self._by_original:
            return self._by_original[key]
        raise KeyError(f"'{key}' not found")

    def with_field(self, normalized: str, original: str, value: Any) -> "SchemaContract":
        """Return new contract with inferred field added.

        Called for DYNAMIC/FLEXIBLE extras on first row.
        Returns new instance (frozen pattern).
        """
        if self.locked and normalized in self._by_normalized:
            raise TypeError(f"Field '{original}' ({normalized}) already locked")

        new_field = FieldContract(
            normalized_name=normalized,
            original_name=original,
            python_type=_normalize_type_for_contract(value),  # Primitive types only!
            required=False,  # Extras are never required
            source="inferred",
        )
        return SchemaContract(
            mode=self.mode,
            fields=self.fields + (new_field,),
            locked=self.locked,
        )

    def with_locked(self) -> "SchemaContract":
        """Return new contract with locked=True."""
        return SchemaContract(mode=self.mode, fields=self.fields, locked=True)

    def validate(self, row: dict[str, Any]) -> list[ContractViolation]:
        """Validate row against locked contract."""
        violations = []
        for fc in self.fields:
            if fc.required and fc.normalized_name not in row:
                violations.append(MissingField(fc))
            elif fc.normalized_name in row:
                value = row[fc.normalized_name]
                # Normalize the runtime type for comparison
                actual_type = _normalize_type_for_contract(value)
                if actual_type != fc.python_type and fc.python_type is not type(None):
                    violations.append(TypeMismatch(fc, actual_type, value))
        return violations

    def with_inferred(self, data: dict[str, Any]) -> "SchemaContract":
        """Return new contract with any new fields inferred from data."""
        # For FIXED mode, reject extras
        # For FLEXIBLE/DYNAMIC, infer new field types
        ...
```

### PipelineRow

Wraps row data with contract reference for dual-name access:

```python
class PipelineRow:
    """Row wrapper that enables dual-name access and type tracking."""

    __slots__ = ("_data", "_contract")

    def __init__(self, data: dict[str, Any], contract: SchemaContract):
        self._data = data          # Actual values, keyed by normalized names
        self._contract = contract

    def __getitem__(self, key: str) -> Any:
        """Access by original OR normalized name."""
        normalized = self._contract.resolve_name(key)
        return self._data[normalized]

    def __getattr__(self, key: str) -> Any:
        """Dot notation access: row.field_name"""
        if key.startswith("_"):
            raise AttributeError(key)
        return self[key]

    def __contains__(self, key: str) -> bool:
        """Support 'if field in row' checks."""
        try:
            self._contract.resolve_name(key)
            return True
        except KeyError:
            return False

    def to_dict(self) -> dict[str, Any]:
        """Export raw data (normalized keys) for serialization."""
        return dict(self._data)

    @property
    def contract(self) -> SchemaContract:
        """Access the schema contract (for introspection/debugging)."""
        return self._contract
```

## Contract Flow Through Pipeline

Each node declares its **input contract** (what it requires) and **output contract** (what it guarantees). The schema evolves at each stage:

```
Source (DYNAMIC)              Transform (FLEXIBLE)           Sink (FIXED)
┌─────────────────────┐      ┌─────────────────────┐       ┌─────────────────────┐
│ Input: N/A          │      │ Input:              │       │ Input:              │
│                     │      │   requires: [a, b]  │       │   requires: [a,b,d] │
│ Output:             │      │   mode: FLEXIBLE    │       │   mode: FIXED       │
│   inferred: {a,b,c} │─────►│                     │──────►│                     │
│   mode: DYNAMIC     │      │ Output:             │       │ Output: N/A         │
│                     │      │   guarantees: [a,b,d]│       │                     │
└─────────────────────┘      │   mode: FLEXIBLE    │       └─────────────────────┘
                             └─────────────────────┘
```

### DAG Validation

At config time:
- Check that upstream `guaranteed_fields` ⊇ downstream `required_fields`
- For DYNAMIC sources, validation deferred until first row (fields unknown upfront)

At runtime per row:
```python
def process_row(row: PipelineRow, node: Node) -> PipelineRow | Quarantine:
    # 1. Validate row against node's INPUT contract
    violations = node.input_contract.validate(row)
    if violations:
        return Quarantine(row, violations, node.on_validation_failure)

    # 2. Execute node logic (transform, gate, etc.)
    output_data = node.execute(row)

    # 3. Wrap output with node's OUTPUT contract
    #    (infers new fields if FLEXIBLE/DYNAMIC)
    output_contract = node.output_contract.with_inferred(output_data)
    return PipelineRow(output_data, output_contract)
```

## Template Access

Templates support dual-name access - both original and normalized names work:

```jinja2
{# All of these work: #}
{{ row.important_data }}                    {# Normalized (dot notation) #}
{{ row["important_data"] }}                 {# Normalized (bracket) #}
{{ row["'Important - Data !!'"] }}          {# Original (bracket) #}
```

Developers working in the codebase prefer normalized names (cleaner code). End users who just see their CSV data can use original names (what they see in their data).

## Error Message Format

Error messages show both names for full debuggability:

```
"'Original Name' (normalized_name)"
```

Examples:
```
TemplateError: Field "'Important - Data !!'" (important_data) not found
TypeError: Field "'Amount USD'" (amount_usd) expected int, got str
```

Original first (what user sees in data), normalized in parens (for debugging).

## Sink Header Restoration

Sinks can output headers in three modes:

```yaml
sinks:
  output:
    plugin: csv
    options:
      path: results.csv
      headers: original    # "original" | "normalized" | {custom mapping}
```

| Mode | Output Header | Use Case |
|------|--------------|----------|
| `normalized` | `important_data` | Machine-readable output |
| `original` | `'Important - Data !!'` | Match source format |
| `{custom}` | User-defined mapping | Renamed headers for handover |

Custom mapping for external system handover:
```yaml
sinks:
  warehouse_export:
    plugin: csv
    options:
      headers:
        important_data: "IMPORTANT_DATA_FIELD"
        amount_usd: "AMOUNT_USD"
```

Full chain with all three names recorded in audit trail:
```
Source Header          Internal (normalized)      Sink Header (custom)
"'Important Data!'"  →  important_data         →  "IMPORTANT_DATA_FIELD"
```

## Audit Trail Integration

The Landscape records schema contracts for full traceability:

### runs table
```json
{
  "field_resolution": {
    "original_to_normalized": {
      "'Important - Data !!'": "important_data",
      "Amount (USD)": "amount_usd"
    },
    "normalization_version": "1.0.0"
  }
}
```

### nodes table
```json
{
  "contract": {
    "mode": "FLEXIBLE",
    "declared_fields": [
      {"name": "important_data", "type": "int", "required": true}
    ],
    "guaranteed_fields": ["important_data", "amount_usd"],
    "required_fields": ["important_data"]
  }
}
```

### node_states table
```json
{
  "inferred_schema": {
    "fields": [
      {"name": "important_data", "original": "'Important - Data !!'", "type": "int"},
      {"name": "extra_field", "original": "Extra Field", "type": "str"}
    ],
    "locked_at_row": 1
  }
}
```

### validation_errors table
```json
{
  "field": "important_data",
  "original_name": "'Important - Data !!'",
  "expected_type": "int",
  "actual_type": "str",
  "actual_value": "not_a_number",
  "row_id": "row_42"
}
```

## Checkpoint Serialization

`PipelineRow` must survive crash recovery. The checkpoint format separates data from contract:

```python
class PipelineRow:
    def to_checkpoint_format(self) -> dict[str, Any]:
        """Serialize for checkpoint storage.

        Returns dict with data and contract_ref (not full contract).
        Contract is stored once per node, not per row.
        """
        return {
            "data": self._data,
            "contract_version": self._contract.version_hash(),
        }

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_data: dict[str, Any],
        contract_registry: dict[str, SchemaContract],
    ) -> "PipelineRow":
        """Restore from checkpoint.

        Args:
            checkpoint_data: Output from to_checkpoint_format()
            contract_registry: Node contracts indexed by version_hash
        """
        contract = contract_registry[checkpoint_data["contract_version"]]
        return cls(data=checkpoint_data["data"], contract=contract)


class SchemaContract:
    def version_hash(self) -> str:
        """Deterministic hash of contract for checkpoint references.

        Uses canonical JSON of field definitions for reproducibility.
        """
        field_defs = [
            {
                "n": fc.normalized_name,
                "o": fc.original_name,
                "t": fc.python_type.__name__,
                "r": fc.required,
            }
            for fc in sorted(self.fields, key=lambda f: f.normalized_name)
        ]
        return hashlib.sha256(
            canonical_json({"mode": self.mode, "fields": field_defs}).encode()
        ).hexdigest()[:16]

    def to_checkpoint_format(self) -> dict[str, Any]:
        """Full contract serialization for checkpoint storage."""
        return {
            "mode": self.mode,
            "locked": self.locked,
            "fields": [
                {
                    "normalized_name": fc.normalized_name,
                    "original_name": fc.original_name,
                    "python_type": fc.python_type.__name__,
                    "required": fc.required,
                    "source": fc.source,
                }
                for fc in self.fields
            ],
        }

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any]) -> "SchemaContract":
        """Restore contract from checkpoint format."""
        type_map = {"int": int, "str": str, "float": float, "bool": bool, "NoneType": type(None)}
        fields = tuple(
            FieldContract(
                normalized_name=f["normalized_name"],
                original_name=f["original_name"],
                python_type=type_map.get(f["python_type"], str),  # Default to str for unknown
                required=f["required"],
                source=f["source"],
            )
            for f in data["fields"]
        )
        return cls(mode=data["mode"], fields=fields, locked=data["locked"])
```

**Checkpoint storage strategy:**

1. Contracts stored once per node in `node_checkpoints` table
2. Rows reference contract by `version_hash` (16 hex chars)
3. On resume, contracts loaded first, then rows restored with contract references

## Fork/Join Contract Merge Semantics

When parallel paths converge at a coalesce node, their contracts must merge:

```python
class SchemaContract:
    def merge(self, other: "SchemaContract") -> "SchemaContract":
        """Merge two contracts at a coalesce point.

        Rules:
        1. Mode: Most restrictive wins (FIXED > FLEXIBLE > DYNAMIC)
        2. Fields present in both: Types must match (error if not)
        3. Fields in only one: Included but marked non-required
        4. Locked: True if either is locked
        """
        # Mode precedence
        mode_order = {"FIXED": 0, "FLEXIBLE": 1, "DYNAMIC": 2}
        merged_mode = min(self.mode, other.mode, key=lambda m: mode_order[m])

        # Build merged field set
        merged_fields: dict[str, FieldContract] = {}

        all_names = set(fc.normalized_name for fc in self.fields) | \
                    set(fc.normalized_name for fc in other.fields)

        for name in all_names:
            self_fc = self._by_normalized.get(name)
            other_fc = other._by_normalized.get(name)

            if self_fc and other_fc:
                # Both have field - types must match
                if self_fc.python_type != other_fc.python_type:
                    raise ContractMergeError(
                        f"Type mismatch at coalesce: '{self_fc.original_name}' ({name}) "
                        f"has type {self_fc.python_type.__name__} in one path, "
                        f"{other_fc.python_type.__name__} in another"
                    )
                # Use the one that's required if either is
                merged_fields[name] = FieldContract(
                    normalized_name=name,
                    original_name=self_fc.original_name,
                    python_type=self_fc.python_type,
                    required=self_fc.required or other_fc.required,
                    source="declared" if self_fc.source == "declared" else other_fc.source,
                )
            else:
                # Only in one path - include but mark non-required
                fc = self_fc or other_fc
                merged_fields[name] = FieldContract(
                    normalized_name=fc.normalized_name,
                    original_name=fc.original_name,
                    python_type=fc.python_type,
                    required=False,  # Can't require field that only exists in one path
                    source=fc.source,
                )

        return SchemaContract(
            mode=merged_mode,
            fields=tuple(merged_fields.values()),
            locked=self.locked or other.locked,
        )
```

**Merge scenarios:**

| Scenario | Result |
|----------|--------|
| Path A has `{x: int}`, Path B has `{x: int}` | `{x: int}` (types match) |
| Path A has `{x: int}`, Path B has `{x: str}` | **Error** - type mismatch |
| Path A has `{x: int, y: str}`, Path B has `{x: int}` | `{x: int, y?: str}` (y optional) |
| Path A is FIXED, Path B is DYNAMIC | Merged is FIXED (most restrictive) |

**Design rationale:** Type mismatches at coalesce are bugs in the pipeline design, not data issues. A gate that routes to different paths with incompatible transformations cannot safely merge. This is caught at the coalesce point, not silently widened.

## Implementation Phases

### Phase 1: Core Contracts
- Implement `FieldContract`, `SchemaContract`, `PipelineRow`
- Unit tests for name resolution, type locking, validation

### Phase 2: Source Integration
- Sources emit `PipelineRow` with inferred contracts
- Update `FieldResolution` to merge into `SchemaContract`
- Infer-and-lock on first row for DYNAMIC sources

### Phase 3: Transform/Sink Integration
- Transforms validate input against contract, propagate output contract
- Sinks validate input, support header mode configuration
- Quarantine routing for contract violations

### Phase 4: Template Resolver
- Dual-name support in Jinja2 environment
- Error messages with "original (normalized)" format

### Phase 5: Audit Trail
- Record contracts in Landscape schema
- Update MCP analysis tools for contract introspection

## Breaking Changes

Per NO LEGACY CODE policy, all call sites updated in same commit:

| Component | Current | New |
|-----------|---------|-----|
| `SchemaConfig.mode` | `strict\|free\|None` | `FIXED\|FLEXIBLE\|DYNAMIC` |
| `PluginSchema.to_row()` | Returns `dict[str, Any]` | Returns `PipelineRow` |
| `FieldResolution` | Separate dataclass | Merged into `SchemaContract` |
| Row in transforms | `dict[str, Any]` | `PipelineRow` |
| Sink `restore_source_headers` | `bool` | `headers: original\|normalized\|{custom}` |

## Open Questions

1. **Performance:** Is `PipelineRow` wrapper overhead acceptable for high-throughput pipelines?
2. **Serialization:** How does `PipelineRow` serialize for checkpoints?
3. **Schema evolution:** Can inferred types widen (int → int|str) or only lock?

## Decision: Types Lock, No Widening

Per brainstorming discussion: types lock on first observation and do not widen. If `amount` is `int` on row 1, `amount: "hello"` on row 500 is a validation failure → quarantine.

This is the "shortest path" rule: validate external data as early as possible, then trust it.
