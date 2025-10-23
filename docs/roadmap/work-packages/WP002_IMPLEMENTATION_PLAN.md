# WP002 Implementation Plan - Schema Validation for Demo

**Target**: Demo-ready in 1-2 days
**Scope**: Pydantic-based DataFrame schema validation with config-time error detection
**Demo Value**: "Fail fast at config time, not row 501"

---

## Demo Story

**Problem**: Experiments crash 500 rows in when column is missing
**Solution**: Schema validation at config load catches mismatches immediately
**Demo Flow**:
1. Show config with schema mismatch
2. Run `elspeth validate-schemas` → clear error message
3. Fix schema
4. Run experiment → works perfectly

---

## Prioritized Implementation Phases

### Phase 1: Core Infrastructure (Day 1 Morning - 3 hours)

**Goal**: Get basic Pydantic schemas working with CSV datasource

#### Task 1.1: Pydantic Base Classes (30 min)
**File**: `src/elspeth/core/base/schema.py` (NEW)

```python
"""DataFrame schema validation using Pydantic."""

from __future__ import annotations
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field, create_model
import pandas as pd

class DataFrameSchema(BaseModel):
    """Base class for DataFrame column schemas.

    Subclasses define column names as fields with type annotations.
    Example:
        class MySchema(DataFrameSchema):
            user_id: int
            name: str
            score: float = Field(ge=0, le=100)
    """

    class Config:
        extra = "allow"  # Allow undeclared columns by default
        arbitrary_types_allowed = True

def infer_schema_from_dataframe(
    df: pd.DataFrame,
    schema_name: str = "InferredSchema"
) -> Type[DataFrameSchema]:
    """Infer Pydantic schema from DataFrame dtypes.

    Args:
        df: DataFrame to infer from
        schema_name: Name for the generated schema class

    Returns:
        Pydantic model class representing the DataFrame schema
    """
    fields: Dict[str, tuple] = {}

    for col in df.columns:
        dtype = df[col].dtype
        python_type = _pandas_dtype_to_python(dtype)
        fields[col] = (python_type, Field(default=None))

    return create_model(
        schema_name,
        __base__=DataFrameSchema,
        **fields
    )

def _pandas_dtype_to_python(dtype) -> type:
    """Convert pandas dtype to Python type for Pydantic."""
    import numpy as np

    if pd.api.types.is_integer_dtype(dtype):
        return int
    elif pd.api.types.is_float_dtype(dtype):
        return float
    elif pd.api.types.is_bool_dtype(dtype):
        return bool
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return str  # Store as ISO string for simplicity
    else:
        return str

def _parse_type_string(type_str: str) -> type:
    """Convert config type string to Python type."""
    mapping = {
        "str": str,
        "string": str,
        "int": int,
        "integer": int,
        "float": float,
        "number": float,
        "bool": bool,
        "boolean": bool,
    }
    return mapping.get(type_str.lower(), str)

def schema_from_config(
    schema_dict: Dict[str, str | Dict[str, Any]],
    schema_name: str = "ConfigSchema"
) -> Type[DataFrameSchema]:
    """Build Pydantic schema from config dict.

    Args:
        schema_dict: Config schema like {"col1": "int", "col2": "str"}
        schema_name: Name for the generated schema class

    Returns:
        Pydantic model class

    Example:
        schema_dict = {"APPID": "str", "score": "int"}
        Schema = schema_from_config(schema_dict)
    """
    fields: Dict[str, tuple] = {}

    for col_name, col_spec in schema_dict.items():
        if isinstance(col_spec, str):
            # Simple type: "int", "str"
            python_type = _parse_type_string(col_spec)
            fields[col_name] = (python_type, Field(default=None))
        elif isinstance(col_spec, dict):
            # Complex type with constraints: {"type": "int", "min": 0, "max": 100}
            type_str = col_spec.get("type", "str")
            python_type = _parse_type_string(type_str)

            # Extract Pydantic Field constraints
            field_kwargs = {}
            if "min" in col_spec:
                field_kwargs["ge"] = col_spec["min"]
            if "max" in col_spec:
                field_kwargs["le"] = col_spec["max"]
            if "description" in col_spec:
                field_kwargs["description"] = col_spec["description"]

            field_kwargs["default"] = None
            fields[col_name] = (python_type, Field(**field_kwargs))
        else:
            # Fallback
            fields[col_name] = (str, Field(default=None))

    return create_model(
        schema_name,
        __base__=DataFrameSchema,
        **fields
    )
```

**Tests**: `tests/test_schema_core.py`
- Test schema inference from DataFrame
- Test schema from config dict
- Test type parsing

---

#### Task 1.2: Datasource Protocol Extension (30 min)
**File**: `src/elspeth/core/interfaces.py` (MODIFY)

```python
# Add to existing DataSource protocol
@runtime_checkable
class DataSource(Protocol):
    """Loads experiment input data as a pandas DataFrame."""

    def load(self) -> pd.DataFrame:
        """Return the experiment dataset."""
        raise NotImplementedError

    def output_schema(self) -> Optional[Type["DataFrameSchema"]]:  # NEW
        """Return Pydantic model describing output columns.

        Returns None if schema is not declared (backwards compatible).
        """
        return None  # Default: no schema
```

---

#### Task 1.3: CSV Datasource Schema Support (1 hour)
**File**: `src/elspeth/plugins/datasources/csv_local.py` (MODIFY)

```python
from elspeth.core.base.schema import (
    DataFrameSchema,
    infer_schema_from_dataframe,
    schema_from_config
)
from typing import Type, Optional

class CSVDataSource:
    """Local CSV file datasource with schema support."""

    def __init__(
        self,
        path: str,
        encoding: str = "utf-8",
        dtype: Dict[str, Any] | None = None,
        schema: Dict[str, str | Dict] | None = None,  # NEW parameter
        **pandas_kwargs
    ):
        self.path = path
        self.encoding = encoding
        self.dtype = dtype or {}
        self.schema_config = schema  # NEW: explicit schema from config
        self.pandas_kwargs = pandas_kwargs
        self._inferred_schema: Optional[Type[DataFrameSchema]] = None
        self.security_level = None  # Set by registry
        self.determinism_level = None  # Set by registry

    def output_schema(self) -> Optional[Type[DataFrameSchema]]:
        """Return schema (explicit from config or inferred from CSV)."""
        if self.schema_config:
            # Use explicit schema from config
            return schema_from_config(
                self.schema_config,
                schema_name=f"CSVSchema_{Path(self.path).stem}"
            )
        else:
            # Infer schema from CSV (lazy loading)
            return self._infer_schema()

    def _infer_schema(self) -> Type[DataFrameSchema]:
        """Infer schema from CSV header and first few rows."""
        if self._inferred_schema:
            return self._inferred_schema

        # Read just header + first row for type inference
        df_sample = pd.read_csv(
            self.path,
            nrows=5,  # Sample size
            dtype=self.dtype,
            encoding=self.encoding
        )

        self._inferred_schema = infer_schema_from_dataframe(
            df_sample,
            schema_name=f"CSVSchema_{Path(self.path).stem}_inferred"
        )
        return self._inferred_schema

    def load(self) -> pd.DataFrame:
        """Load CSV file and attach schema metadata."""
        df = pd.read_csv(
            self.path,
            dtype=self.dtype,
            encoding=self.encoding,
            **self.pandas_kwargs
        )

        # Attach metadata
        df.attrs["security_level"] = self.security_level
        df.attrs["determinism_level"] = self.determinism_level
        df.attrs["schema"] = self.output_schema()  # NEW: attach schema

        return df
```

**Tests**: `tests/test_datasource_csv_schema.py`
- Test explicit schema from config
- Test schema inference
- Test DataFrame attrs includes schema

---

#### Task 1.4: Plugin Protocol Extension (30 min)
**File**: `src/elspeth/core/experiments/plugins.py` (MODIFY)

```python
# Add to existing experiment plugin protocols

class RowExperimentPlugin(Protocol):
    """Row-level experiment plugin protocol."""

    name: str

    def input_schema(self) -> Optional[Type["DataFrameSchema"]]:  # NEW
        """Declare required input columns and types.

        Returns None if plugin accepts any schema (backwards compatible).
        """
        return None  # Default: no requirements

    def process_row(
        self, row: Dict[str, Any], responses: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process single row."""
        raise NotImplementedError

class AggregatorPlugin(Protocol):
    """Aggregator plugin protocol."""

    name: str

    def input_schema(self) -> Optional[Type["DataFrameSchema"]]:  # NEW
        """Declare required columns for aggregation."""
        return None

    def finalize(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate results."""
        raise NotImplementedError
```

---

### Phase 2: Validation Engine (Day 1 Afternoon - 3 hours)

#### Task 2.1: Schema Compatibility Checker (1 hour)
**File**: `src/elspeth/core/base/schema.py` (ADD)

```python
class SchemaCompatibilityError(Exception):
    """Raised when datasource schema is incompatible with plugin requirements."""
    pass

def validate_schema_compatibility(
    source_schema: Type[DataFrameSchema],
    required_schema: Type[DataFrameSchema],
    *,
    context: str = "schema_validation"
) -> None:
    """Validate that source schema provides all required fields.

    Args:
        source_schema: Pydantic model from datasource.output_schema()
        required_schema: Pydantic model from plugin.input_schema()
        context: Error context for debugging

    Raises:
        SchemaCompatibilityError: If schemas are incompatible

    Validation Rules:
        1. All required fields in required_schema must exist in source_schema
        2. Field types must be compatible (int → float OK, str → int NOT OK)
        3. Optional fields in required_schema can be missing
    """
    source_fields = source_schema.model_fields
    required_fields = required_schema.model_fields

    errors = []

    for field_name, field_info in required_fields.items():
        # Check field exists
        if field_name not in source_fields:
            if field_info.is_required():
                errors.append(
                    f"Missing required field '{field_name}' "
                    f"(required by plugin, not in datasource)"
                )
            continue

        # Check type compatibility
        source_type = source_fields[field_name].annotation
        required_type = field_info.annotation

        if not _is_type_compatible(source_type, required_type):
            errors.append(
                f"Field '{field_name}' type mismatch: "
                f"datasource provides {source_type.__name__}, "
                f"plugin requires {required_type.__name__}"
            )

    if errors:
        error_msg = f"{context}: Schema compatibility check failed:\n"
        error_msg += "\n".join(f"  ❌ {e}" for e in errors)
        error_msg += "\n\n💡 Solutions:\n"
        error_msg += "  1. Update datasource schema to include missing fields\n"
        error_msg += "  2. Make plugin fields optional if not always present\n"
        error_msg += "  3. Add row plugin to generate missing fields"
        raise SchemaCompatibilityError(error_msg)

def _is_type_compatible(source_type: type, required_type: type) -> bool:
    """Check if source type can be coerced to required type."""
    # Exact match
    if source_type == required_type:
        return True

    # Any source is compatible
    from typing import Any
    if source_type == Any or source_type is Any:
        return True

    # Int can widen to float
    if source_type == int and required_type == float:
        return True

    # Handle Optional types
    from typing import get_origin, get_args
    if get_origin(required_type) is type(None) or str(required_type).startswith("typing.Optional"):
        # Optional type - extract inner type
        args = get_args(required_type)
        if args:
            inner_type = args[0]
            return _is_type_compatible(source_type, inner_type)

    # Check subclass relationship
    try:
        if isinstance(source_type, type) and isinstance(required_type, type):
            return issubclass(source_type, required_type)
    except TypeError:
        pass

    return False
```

**Tests**: `tests/test_schema_validation.py`
- Test exact match (pass)
- Test missing required field (fail)
- Test missing optional field (pass)
- Test type mismatch (fail)
- Test compatible types: int → float (pass)
- Test incompatible types: str → int (fail)

---

#### Task 2.2: ExperimentRunner Integration (1 hour)
**File**: `src/elspeth/core/experiments/runner.py` (MODIFY)

```python
from elspeth.core.base.schema import validate_schema_compatibility, SchemaCompatibilityError

class ExperimentRunner:
    """Execute single experiment with schema validation."""

    def run(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Execute experiment with config-time schema validation."""

        # NEW: Validate schemas at start (fail fast)
        datasource_schema = df.attrs.get("schema")
        if datasource_schema:
            self._validate_plugin_schemas(datasource_schema)

        # ... rest of existing execution logic

    def _validate_plugin_schemas(
        self, datasource_schema: Type["DataFrameSchema"]
    ) -> None:
        """Validate all plugins are compatible with datasource schema."""
        from elspeth.config import ConfigurationError

        # Validate row plugins
        for plugin in self.row_plugins or []:
            plugin_schema = getattr(plugin, "input_schema", lambda: None)()
            if plugin_schema:
                try:
                    validate_schema_compatibility(
                        datasource_schema,
                        plugin_schema,
                        context=f"row_plugin:{plugin.name}"
                    )
                except SchemaCompatibilityError as e:
                    raise ConfigurationError(
                        f"Row plugin '{plugin.name}' schema incompatible "
                        f"with datasource:\n{e}"
                    ) from e

        # Validate aggregators
        for aggregator in self.aggregators or []:
            agg_schema = getattr(aggregator, "input_schema", lambda: None)()
            if agg_schema:
                try:
                    validate_schema_compatibility(
                        datasource_schema,
                        agg_schema,
                        context=f"aggregator:{aggregator.name}"
                    )
                except SchemaCompatibilityError as e:
                    raise ConfigurationError(
                        f"Aggregator '{aggregator.name}' schema incompatible "
                        f"with datasource:\n{e}"
                    ) from e

        # Validate validators
        for validator in self.validators or []:
            val_schema = getattr(validator, "input_schema", lambda: None)()
            if val_schema:
                try:
                    validate_schema_compatibility(
                        datasource_schema,
                        val_schema,
                        context=f"validator:{validator.name}"
                    )
                except SchemaCompatibilityError as e:
                    raise ConfigurationError(
                        f"Validator '{validator.name}' schema incompatible "
                        f"with datasource:\n{e}"
                    ) from e
```

**Tests**: `tests/test_runner_schema_validation.py`
- Test runner validates schemas at startup
- Test error raised for incompatible plugin
- Test no error when schemas compatible

---

#### Task 2.3: Row-Level Runtime Validation with Malformed Data Routing (1 hour)
**File**: `src/elspeth/core/base/schema.py` (ADD)

```python
from pydantic import ValidationError as PydanticValidationError
from typing import Dict, Any, Tuple, List

class SchemaViolation:
    """Represents a schema validation failure for a single row."""

    def __init__(
        self,
        row_index: int,
        row_data: Dict[str, Any],
        errors: List[Dict[str, Any]],
        schema_name: str,
    ):
        self.row_index = row_index
        self.row_data = row_data
        self.errors = errors  # Pydantic error details
        self.schema_name = schema_name
        self.timestamp = pd.Timestamp.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for sink writing."""
        return {
            "row_index": self.row_index,
            "schema_name": self.schema_name,
            "timestamp": self.timestamp.isoformat(),
            "validation_errors": self.errors,
            "malformed_data": self.row_data,
        }

def validate_row(
    row: Dict[str, Any],
    schema: Type[DataFrameSchema],
    *,
    row_index: int = 0
) -> Tuple[bool, Optional[SchemaViolation]]:
    """Validate a single row against schema.

    Args:
        row: Row data as dict
        schema: Pydantic schema class
        row_index: Row index for error reporting

    Returns:
        Tuple of (is_valid, violation_or_none)
        - (True, None) if valid
        - (False, SchemaViolation) if invalid
    """
    try:
        # Attempt to validate and coerce types
        validated = schema(**row)
        return (True, None)
    except PydanticValidationError as e:
        # Convert Pydantic errors to structured format
        errors = []
        for error in e.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "type": error["type"],
                "message": error["msg"],
                "input_value": error.get("input"),
            })

        violation = SchemaViolation(
            row_index=row_index,
            row_data=row,
            errors=errors,
            schema_name=schema.__name__,
        )
        return (False, violation)
```

**File**: `src/elspeth/core/experiments/runner.py` (MODIFY)

```python
class ExperimentRunner:
    """Execute single experiment with schema validation and malformed data routing."""

    def __init__(
        self,
        *,
        on_schema_violation: str = "abort",  # NEW: "abort" | "route" | "skip"
        malformed_data_sink: Optional[ResultSink] = None,  # NEW
        # ... existing parameters
    ):
        self.on_schema_violation = on_schema_violation
        self.malformed_data_sink = malformed_data_sink
        self.malformed_rows: List[SchemaViolation] = []  # Buffer for routing
        # ... existing initialization

    def run(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Execute experiment with row-level validation and routing."""

        # Config-time validation (existing)
        datasource_schema = df.attrs.get("schema")
        if datasource_schema:
            self._validate_plugin_schemas(datasource_schema)

        # Process rows with runtime validation
        results = []
        malformed_count = 0

        for idx, (_, row) in enumerate(df.iterrows()):
            row_dict = row.to_dict()

            # Runtime row validation (NEW)
            if datasource_schema and self.on_schema_violation != "abort":
                is_valid, violation = validate_row(
                    row_dict,
                    datasource_schema,
                    row_index=idx
                )

                if not is_valid:
                    malformed_count += 1
                    self.malformed_rows.append(violation)

                    if self.on_schema_violation == "skip":
                        # Skip malformed row, continue with next
                        logger.warning(
                            f"Row {idx} failed schema validation, skipping: "
                            f"{violation.errors}"
                        )
                        continue
                    elif self.on_schema_violation == "route":
                        # Route to malformed sink, continue processing
                        logger.info(
                            f"Row {idx} failed schema validation, routing to "
                            f"malformed data sink"
                        )
                        continue
                    # else: "abort" would have raised at config-time validation

            # Process valid row (existing logic)
            record = self._process_single_row(row_dict, idx)
            results.append(record)

        # Write malformed data to sink (NEW)
        if self.malformed_rows and self.malformed_data_sink:
            self._write_malformed_data()

        # ... rest of existing execution logic

        # Add malformed count to metadata
        metadata = {
            "malformed_rows": malformed_count,
            "valid_rows": len(results),
            # ... existing metadata
        }

        return {
            "results": results,
            "metadata": metadata,
            # ... existing payload
        }

    def _write_malformed_data(self) -> None:
        """Write malformed rows to dedicated sink."""
        if not self.malformed_data_sink or not self.malformed_rows:
            return

        malformed_payload = {
            "malformed_data": [v.to_dict() for v in self.malformed_rows],
            "count": len(self.malformed_rows),
            "schema_name": self.malformed_rows[0].schema_name,
        }

        try:
            self.malformed_data_sink.write(
                malformed_payload,
                metadata={"type": "schema_violations"}
            )
            logger.info(
                f"Wrote {len(self.malformed_rows)} malformed rows to sink"
            )
        except Exception as e:
            logger.error(f"Failed to write malformed data: {e}")
```

**Configuration Example**:

```yaml
suite:
  defaults:
    datasource:
      type: local_csv
      path: "data/questions.csv"
      schema:
        APPID: str
        score: int  # Expecting integer

    validation:  # NEW configuration section
      on_schema_violation: route  # "abort" | "route" | "skip"
      malformed_data_sink:
        type: csv
        path: "outputs/malformed_data.csv"
        security_level: OFFICIAL
        determinism_level: high

experiments:
  - name: baseline_with_validation
    # Inherits validation config from defaults
```

**Tests**: `tests/test_runtime_schema_validation.py`
- Test route mode: malformed rows go to sink, valid rows processed
- Test skip mode: malformed rows skipped, logged
- Test abort mode: first malformed row raises error
- Test malformed sink receives correct data structure

---

### Phase 3: Plugin Schemas (Day 2 Morning - 2 hours)

#### Task 3.1: Implement Schemas for Key Plugins (1.5 hours)
**Files**: `src/elspeth/plugins/experiments/metrics.py`, `validation.py` (MODIFY)

```python
from elspeth.core.base.schema import DataFrameSchema
from pydantic import Field
from typing import Optional

# Score Extractor - No row requirements (reads from LLM response)
class ScoreExtractorSchema(DataFrameSchema):
    """Input schema for ScoreExtractorPlugin - no row requirements."""
    pass

class ScoreExtractorPlugin:
    name = "score_extractor"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return ScoreExtractorSchema  # No requirements

    # ... rest of implementation

# Statistics Aggregator - Requires score field
class StatisticsAggregatorSchema(DataFrameSchema):
    """Input schema for StatisticsAggregator."""
    score: float = Field(description="Numeric score to aggregate")

class StatisticsAggregator:
    name = "statistics"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return StatisticsAggregatorSchema

    # ... rest of implementation

# RAG Query Plugin - Requires question field
class RAGQuerySchema(DataFrameSchema):
    """Input schema for RAGQueryPlugin."""
    question: str = Field(description="Question text for RAG retrieval")
    context: Optional[str] = Field(default=None, description="Optional additional context")

class RAGQueryPlugin:
    name = "rag_query"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return RAGQuerySchema

    # ... rest of implementation

# Regex Validator - No row requirements (validates LLM response)
class RegexValidatorSchema(DataFrameSchema):
    """Input schema for RegexValidator - no row requirements."""
    pass

class RegexValidator:
    name = "regex_validator"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return RegexValidatorSchema

    # ... rest of implementation

# LLM Guard - Optional expected_answer field
class LLMGuardSchema(DataFrameSchema):
    """Input schema for LLMGuardValidator."""
    expected_answer: Optional[str] = Field(default=None, description="Expected answer for comparison")

class LLMGuardValidator:
    name = "llm_guard"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return LLMGuardSchema

    # ... rest of implementation
```

**Priority Plugins for Demo**:
1. ✅ ScoreExtractorPlugin
2. ✅ StatisticsAggregator
3. ✅ RAGQueryPlugin
4. ✅ RegexValidator
5. ✅ LLMGuardValidator

---

#### Task 3.2: Update Sample Suite Config (30 min)
**File**: `config/sample_suite/settings.yaml` (MODIFY)

```yaml
suite:
  defaults:
    datasource:
      type: local_csv
      path: "data/questions.csv"
      security_level: OFFICIAL
      determinism_level: guaranteed
      schema:  # NEW: Explicit schema declaration
        APPID: str
        question: str
        expected_answer: str
        category: str
        difficulty: int

experiments:
  - name: baseline_gpt4
    description: "Baseline evaluation with schema validation"
    is_baseline: true

    row_plugins:
      - type: score_extractor
        # No schema requirements

    aggregators:
      - type: statistics
        # Requires: score (float) - provided by score_extractor
```

---

### Phase 4: CLI Validation (Day 2 Afternoon - 1.5 hours)

#### Task 4.1: CLI Command (1 hour)
**File**: `src/elspeth/cli.py` (ADD)

```python
@click.command()
@click.option("--settings", required=True, help="Path to settings YAML")
@click.option("--suite-root", help="Suite root directory")
def validate_schemas(settings: str, suite_root: str | None) -> None:
    """Validate all experiment schemas for compatibility.

    Checks:
        1. All datasources declare valid schemas
        2. All plugins declare valid schemas
        3. All plugin requirements satisfied by datasources

    Exits with code 0 if valid, 1 if issues found.
    """
    from elspeth.config import load_settings
    from elspeth.core.base.schema import validate_schema_compatibility, SchemaCompatibilityError

    click.echo("🔍 Validating experiment schemas...\n")

    config = load_settings(settings, suite_root)
    errors = []

    for experiment_config in config["experiments"]:
        exp_name = experiment_config["name"]

        try:
            # Get datasource schema
            ds_config = experiment_config.get("datasource", config["suite"]["defaults"].get("datasource"))
            datasource = create_datasource_from_config(ds_config)

            ds_schema = datasource.output_schema()
            if not ds_schema:
                click.echo(f"⚠️  {exp_name}: Datasource has no schema (skipping validation)")
                continue

            click.echo(f"✓ {exp_name}: Datasource schema OK ({len(ds_schema.model_fields)} fields)")

            # Validate each row plugin
            for plugin_config in experiment_config.get("row_plugins", []):
                plugin_name = plugin_config["type"]
                plugin = create_row_plugin_from_config(plugin_config)

                plugin_schema = getattr(plugin, "input_schema", lambda: None)()
                if plugin_schema:
                    validate_schema_compatibility(
                        ds_schema,
                        plugin_schema,
                        context=f"{exp_name}:row_plugin:{plugin_name}"
                    )
                    click.echo(f"  ✓ Row plugin '{plugin_name}' schema compatible")
                else:
                    click.echo(f"  ⚠️  Row plugin '{plugin_name}' has no schema")

            # Validate each aggregator
            for agg_config in experiment_config.get("aggregators", []):
                agg_name = agg_config["type"]
                aggregator = create_aggregator_from_config(agg_config)

                agg_schema = getattr(aggregator, "input_schema", lambda: None)()
                if agg_schema:
                    validate_schema_compatibility(
                        ds_schema,
                        agg_schema,
                        context=f"{exp_name}:aggregator:{agg_name}"
                    )
                    click.echo(f"  ✓ Aggregator '{agg_name}' schema compatible")
                else:
                    click.echo(f"  ⚠️  Aggregator '{agg_name}' has no schema")

        except (SchemaCompatibilityError, ConfigurationError) as e:
            errors.append(f"{exp_name}: {e}")
            click.echo(f"❌ {exp_name}: Schema validation failed\n{e}\n")

    if errors:
        click.echo(f"\n❌ Schema validation failed ({len(errors)} experiment(s) with errors)")
        sys.exit(1)
    else:
        click.echo(f"\n✅ All schemas valid - ready to run experiments")
        sys.exit(0)

# Register command
cli.add_command(validate_schemas, name="validate-schemas")
```

---

#### Task 4.2: Update CLI Help (30 min)
**File**: `src/elspeth/cli.py` (MODIFY main command group)

```python
@click.group()
@click.version_option()
def cli():
    """Elspeth - Secure orchestration framework with schema validation.

    Commands:
        run                Run experiment suite
        validate-schemas   Validate all experiment schemas (NEW!)

    Examples:
        # Validate schemas before running
        elspeth validate-schemas --settings config/sample_suite/settings.yaml

        # Run experiments
        elspeth run --settings config/sample_suite/settings.yaml --live-outputs
    """
    pass
```

---

### Phase 5: Demo Documentation (Day 2 Late Afternoon - 1 hour)

#### Task 5.1: Demo Guide (30 min)
**File**: `docs/examples/SCHEMA_VALIDATION_DEMO.md` (NEW)

```markdown
# DataFrame Schema Validation - Demo Guide

## Overview

Elspeth's schema validation system catches configuration errors **at config time**, not runtime. This prevents experiments from crashing 500 rows in due to missing columns.

## Key Features

1. **Config-Time Validation**: Errors detected before any LLM calls
2. **Pydantic Schemas**: Type-safe column declarations
3. **Automatic Inference**: CSV schemas inferred from headers
4. **Clear Error Messages**: Actionable guidance for fixing issues
5. **Backward Compatible**: Optional feature, existing configs work unchanged

## Demo Scenario 1: Missing Field Detection

### Bad Configuration
```yaml
datasource:
  type: local_csv
  path: "data/questions.csv"
  schema:
    APPID: str
    question: str
    # Missing: expected_answer

experiments:
  - name: baseline
    aggregators:
      - type: statistics  # Requires 'score' field (from score_extractor)
      # BUG: score_extractor not configured!
```

### Validation Output
```bash
$ elspeth validate-schemas --settings bad_config.yaml

🔍 Validating experiment schemas...

✓ baseline: Datasource schema OK (2 fields)
❌ baseline: Schema validation failed

aggregator:statistics: Schema compatibility check failed:
  ❌ Missing required field 'score' (required by plugin, not in datasource)

💡 Solutions:
  1. Update datasource schema to include missing fields
  2. Make plugin fields optional if not always present
  3. Add row plugin to generate missing fields

❌ Schema validation failed (1 experiment(s) with errors)
```

### Fix
```yaml
experiments:
  - name: baseline
    row_plugins:
      - type: score_extractor  # Generates 'score' field
    aggregators:
      - type: statistics  # Now has required 'score'
```

### Success
```bash
$ elspeth validate-schemas --settings good_config.yaml

🔍 Validating experiment schemas...

✓ baseline: Datasource schema OK (2 fields)
  ✓ Row plugin 'score_extractor' schema compatible
  ✓ Aggregator 'statistics' schema compatible

✅ All schemas valid - ready to run experiments
```

## Demo Scenario 2: Type Mismatch

### Configuration
```yaml
datasource:
  type: local_csv
  path: "data/user_ratings.csv"
  schema:
    user_id: str  # BUG: Should be int
    rating: int
    comment: str
```

### Plugin Requirement
```python
class AnalyticsPluginSchema(DataFrameSchema):
    user_id: int  # Requires int
    rating: float
```

### Validation Output
```bash
❌ analytics_experiment: Schema validation failed

aggregator:analytics: Schema compatibility check failed:
  ❌ Field 'user_id' type mismatch: datasource provides str, plugin requires int

💡 Solutions:
  1. Update datasource schema to include missing fields
  2. Make plugin fields optional if not always present
  3. Add row plugin to generate missing fields
```

## Demo Scenario 3: Schema Inference (No Manual Declaration)

### Configuration
```yaml
datasource:
  type: local_csv
  path: "data/questions.csv"
  # No explicit schema - inferred from CSV
```

### CSV File
```csv
APPID,question,expected_answer,category
A001,What is 2+2?,4,math
A002,Capital of France?,Paris,geography
```

### Validation Output
```bash
✓ inference_demo: Datasource schema OK (4 fields)
  Schema inferred: APPID (str), question (str), expected_answer (str), category (str)
```

## Configuration Reference

### Explicit Schema
```yaml
datasource:
  type: local_csv
  path: "data/scores.csv"
  schema:
    student_id: int
    assignment: str
    score:
      type: int
      min: 0
      max: 100
      description: "Assignment score percentage"
```

### Schema Inference
```yaml
datasource:
  type: local_csv
  path: "data/scores.csv"
  # Schema inferred from CSV headers and dtypes
```

### Plugin Schema Declaration
```python
from elspeth.core.base.schema import DataFrameSchema
from pydantic import Field

class MyPluginSchema(DataFrameSchema):
    """Declare required input columns."""
    score: float = Field(ge=0, le=100, description="Score 0-100")
    notes: str | None = Field(default=None, description="Optional notes")

class MyPlugin:
    name = "my_plugin"

    def input_schema(self) -> Type[DataFrameSchema]:
        return MyPluginSchema
```

## Benefits for Australian Government Deployments

1. **Early Error Detection**: Compliance violations caught before expensive LLM calls
2. **Audit Trail**: Schema declarations document expected data formats
3. **Type Safety**: Reduces runtime errors in PROTECTED/SECRET pipelines
4. **Configuration Validation**: Pre-flight checks before production deployment

## Testing

```bash
# Run schema validation tests
pytest tests/test_schema_*.py -v

# Test sample suite schemas
elspeth validate-schemas --settings config/sample_suite/settings.yaml

# Integration test
elspeth run --settings config/sample_suite/settings.yaml --head 5
```
```

---

#### Task 5.2: Update Main Documentation (30 min)
**Files**:
- Developer documentation - Add schema validation section
- `docs/architecture/plugin-catalogue.md` - Update plugin entries with schemas
- `README.md` - Add schema validation to feature list

---

## Testing Strategy

### Unit Tests (Throughout Implementation)
- `tests/test_schema_core.py` - Schema inference, config parsing
- `tests/test_schema_validation.py` - Compatibility checks
- `tests/test_datasource_csv_schema.py` - CSV schema support
- `tests/test_runner_schema_validation.py` - Runner integration
- `tests/test_plugin_schemas.py` - Plugin schema declarations

### Integration Tests (Day 2 End)
- `tests/test_schema_integration.py` - End-to-end with sample suite
- `tests/test_cli_validate_schemas.py` - CLI command

### Demo Validation (Final)
- Run `elspeth validate-schemas` on sample suite
- Test deliberate schema mismatch → clear error
- Fix and re-validate → success
- Run full experiment suite → works

---

## Demo Script (2 minutes)

**Setup**: Terminal with sample suite config

**Step 1: Show the Problem** (30s)
```bash
# Run experiment with missing field
elspeth run --settings bad_config.yaml

# Result: Crashes at row 501 with KeyError: 'score'
```

**Step 2: Schema Validation** (30s)
```bash
# Validate schemas first
elspeth validate-schemas --settings bad_config.yaml

# Result: Clear error message pointing to missing 'score' field
```

**Step 3: Fix and Validate** (30s)
```yaml
# Add score_extractor plugin
experiments:
  - name: baseline
    row_plugins:
      - type: score_extractor  # Generates 'score'
```

```bash
elspeth validate-schemas --settings fixed_config.yaml
# Result: ✅ All schemas valid
```

**Step 4: Success** (30s)
```bash
elspeth run --settings fixed_config.yaml --live-outputs
# Result: Experiment runs successfully, no runtime errors
```

---

## Dependencies

### Required Packages
```toml
[project.dependencies]
pydantic = "^2.0"  # Core validation
```

### Package Installation
```bash
pip install pydantic
```

---

## Success Criteria for Demo

- ✅ Can declare schemas in YAML config
- ✅ CSV datasource infers schema automatically
- ✅ `validate-schemas` CLI command works
- ✅ Clear error messages for mismatches
- ✅ 5+ plugins have schema declarations
- ✅ Sample suite validates successfully
- ✅ Demo script runs in <2 minutes

---

## Rollout Plan

### Day 1: Core Infrastructure
- Morning: Pydantic schemas + CSV support
- Afternoon: Validation engine + runner integration

### Day 2: Plugins and Demo
- Morning: 5 plugin schemas + sample config
- Afternoon: CLI command + demo documentation
- Evening: Full integration test

### Demo Day:
- 2-minute live demo
- Handout: SCHEMA_VALIDATION_DEMO.md
- Q&A: Schema benefits for government compliance

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Pydantic v2 breaking changes | Pin to `pydantic>=2.0,<3.0` |
| Complex type handling (Optional, Union) | Start simple (int/str/float), expand later |
| Existing configs break | All schema methods return Optional, default to None |
| Performance overhead | Schema inference cached, validation only at config load |
| Incomplete plugin coverage | Start with 5 key plugins, document pattern for others |

---

## Post-Demo Enhancements

**Phase 6** (if time permits):
1. Runtime validation in strict mode
2. Schema evolution/migration utilities
3. JSON Schema generation for documentation
4. IDE autocomplete via type stubs
5. Custom Pydantic validators for business rules

---

## Changelog

- **2025-10-13**: Initial implementation plan created for demo
- **2025-10-13**: Prioritized demo-ready features (Phases 1-5)
- **2025-10-13**: Added 2-minute demo script
