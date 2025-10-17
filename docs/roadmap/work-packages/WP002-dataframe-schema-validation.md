# WP002: DataFrame Schema Validation and Type Safety

**Status**: Implemented with Pydantic v2
**Priority**: Critical
**Estimated Effort**: 3-4 days (1 FTE)
**Dependencies**: None (but complements WP001)
**Created**: 2025-10-13
**Updated**: 2025-10-14 (Pydantic v2 migration)
**Owner**: Core Tech Team

**Note**: As of 2025-10-14, this implementation uses **Pydantic v2.12.0** with modern patterns (`model_config`, `model_validate`, explicit `Optional` types).

---

## 1. Problem Statement

### Current Situation

Elspeth has a **critical type safety gap**: DataFrames flow from datasources through experiment runners to plugins with **no schema validation**. This causes:

1. **Late Failures**: Experiments crash on row 501 after 500 successful rows when a required column is missing
2. **No Interface Contracts**: Plugins cannot programmatically declare required input fields
3. **Type Unsafety**: `Dict[str, Any]` provides no guarantees about column presence or types
4. **Poor Developer Experience**: Errors discovered at runtime, not configuration time

### User Requirement

> "Each plugin has a defined schema which is its interface (and is defined in configuration) - so my configuration for my data source says 'use the CSV text loader, read this specific file, and the schema is text: colour, text: fruit, number: qty - the system should ensure that it only plugs into other components that have that exact schema - this means I have to manually define all my interfaces in my config which is a desired outcome... Before data flow is permitted from a data source, a plugin should be satisfied that its audience is 'security cleared' and is speaking the same schema."

### Key Requirements

1. **Datasources Declare Output Schema**: "This CSV produces columns: [APPID, question, expected_answer]"
2. **Plugins Declare Input Requirements**: "This plugin requires columns: [score, threshold] with specific types"
3. **Config-Time Validation**: Fail fast at configuration load/setup, not during execution
4. **Security + Schema**: Both clearance and schema must match before data flows
5. **Type Safety**: Column types (str/int/float) must be validated

---

## 2. Proposed Solution

### 2.1 Pydantic-Based Schema System

**Why Pydantic**:
- Native Python integration (no new DSL)
- Automatic validation + type coercion
- Excellent error messages with field-level detail
- JSON Schema generation for documentation
- Already dominant in Python data ecosystem (FastAPI, LangChain, etc.)

**Alternative Considered**: Pandera (DataFrame-specific), but Pydantic is more flexible for our dict-based plugin API

### 2.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Configuration Phase (Fail Fast)                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DataSource Config              Plugin Config               │
│  ┌──────────────┐              ┌──────────────┐            │
│  │ CSV File     │              │ ScoreExtract │            │
│  │ schema:      │              │ requires:    │            │
│  │   APPID: str │              │   score: int │            │
│  │   score: int │──────────────▶  threshold   │            │
│  │   notes: str │  Validate    │   notes: str │            │
│  └──────────────┘  at config   └──────────────┘            │
│                     load time                               │
│                                                              │
│  ✅ Schema compatible: Continue                             │
│  ❌ Missing "threshold": Fail with clear error              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Runtime Phase (Optional Strict Validation)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DataFrame Row         Pydantic Validation   Plugin Input   │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────┐ │
│  │ APPID: "A1"  │     │ Validate     │     │ Validated  │ │
│  │ score: "95"  │────▶│ + Coerce     │────▶│ score: 95  │ │
│  │ notes: null  │     │ Types        │     │ (int)      │ │
│  └──────────────┘     └──────────────┘     └────────────┘ │
│                                                              │
│  Optional: Runtime validation in strict mode                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Implementation Plan

### Phase 1: Core Schema Infrastructure (1 day)

**FR1: DataSource Schema Protocol**

```python
# src/elspeth/core/interfaces.py

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Type, Dict, Any
import pandas as pd

class DataFrameSchema(BaseModel):
    """Base class for declaring DataFrame column schemas.

    Subclasses define column names as fields with type annotations.
    """

    model_config = ConfigDict(
        extra="allow",  # Allow undeclared columns by default
        arbitrary_types_allowed=True,
    )

# Update DataSource protocol
@runtime_checkable
class DataSource(Protocol):
    def load(self) -> pd.DataFrame:
        """Load data, returning DataFrame with schema in attrs."""
        ...

    def output_schema(self) -> Optional[Type[DataFrameSchema]]:
        """Return Pydantic model describing output columns.

        Returns None if schema is not declared (backwards compatible).
        """
        ...
```

**FR2: Plugin Input Schema Protocol**

```python
# src/elspeth/core/experiments/plugins.py

class RowExperimentPlugin(Protocol):
    name: str

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        """Declare required input columns and types.

        Returns None if plugin accepts any schema (backwards compatible).

        Example:
            class MyPluginSchema(DataFrameSchema):
                score: int = Field(ge=0, le=100, description="Score 0-100")
                threshold: Optional[int] = Field(default=50)

            def input_schema(self) -> Type[DataFrameSchema]:
                return MyPluginSchema
        """
        return None

    def process_row(self, row: Dict[str, Any], responses: Dict[str, Any]) -> Dict[str, Any]:
        ...

class AggregatorPlugin(Protocol):
    name: str

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        """Declare required columns for aggregation."""
        return None

    def finalize(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        ...
```

**FR3: Schema Validation Utilities**

```python
# src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py (new functions)

from pydantic import ValidationError

class SchemaCompatibilityError(ConfigurationError):
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
    source_fields = source_schema.__fields__
    required_fields = required_schema.__fields__

    errors = []

    for field_name, field_info in required_fields.items():
        # Check field exists
        if field_name not in source_fields:
            if field_info.is_required():
                errors.append(f"Missing required field '{field_name}'")
            continue

        # Check type compatibility
        source_type = source_fields[field_name].type_
        required_type = field_info.type_

        if not _is_type_compatible(source_type, required_type):
            errors.append(
                f"Field '{field_name}' type mismatch: "
                f"source provides {source_type}, plugin requires {required_type}"
            )

    if errors:
        raise SchemaCompatibilityError(
            f"{context}: Schema compatibility check failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )

def _is_type_compatible(source_type: type, required_type: type) -> bool:
    """Check if source type can be coerced to required type.

    Compatible conversions:
        - int → float (widening)
        - str → str (exact match)
        - Any → T (no validation)

    Incompatible:
        - float → int (narrowing, lossy)
        - str → int (requires parsing, can fail)
    """
    # Exact match
    if source_type == required_type:
        return True

    # Any source is compatible
    if source_type == Any:
        return True

    # Int can widen to float
    if source_type == int and required_type == float:
        return True

    # Check if types are subclass compatible
    try:
        return issubclass(source_type, required_type)
    except TypeError:
        return False
```

**FR4: Configuration Schema Extensions**

```yaml
# config/sample_suite/settings.yaml

datasource:
  plugin: local_csv
  options:
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
  - name: score_extraction
    row_plugins:
      - plugin: score_extractor
        options:
          score_field: "raw_score"
        schema:  # NEW: Plugin declares requirements
          raw_score: int
          question: str  # Optional: for context
```

**FR5: Schema Inference (Auto-detection)**

```python
# src/elspeth/plugins/datasources/csv_local.py

from pydantic import create_model
from typing import Type
import pandas as pd

class CSVDataSource:
    def __init__(self, path: str, dtype: Dict[str, Any] = None, schema: Dict[str, str] = None, ...):
        self.path = path
        self.dtype = dtype or {}
        self.schema_config = schema  # Explicit schema from config
        self._inferred_schema: Optional[Type[DataFrameSchema]] = None

    def output_schema(self) -> Optional[Type[DataFrameSchema]]:
        """Return schema (explicit or inferred)."""
        if self.schema_config:
            # Use explicit schema from config
            return self._build_schema_from_config()
        else:
            # Infer schema from CSV header
            return self._infer_schema()

    def _build_schema_from_config(self) -> Type[DataFrameSchema]:
        """Build Pydantic model from explicit schema config."""
        fields = {}
        for col_name, col_type_str in self.schema_config.items():
            python_type = _parse_type_string(col_type_str)
            fields[col_name] = (python_type, Field(default=None))

        return create_model(
            f'CSVSchema_{Path(self.path).stem}',
            **fields,
            __base__=DataFrameSchema
        )

    def _infer_schema(self) -> Type[DataFrameSchema]:
        """Infer schema from CSV header and dtypes."""
        if self._inferred_schema:
            return self._inferred_schema

        # Read just the header + first row for type inference
        df_sample = pd.read_csv(self.path, nrows=1, dtype=self.dtype)

        fields = {}
        for col in df_sample.columns:
            dtype = df_sample[col].dtype
            python_type = _pandas_dtype_to_python(dtype)
            fields[col] = (python_type, Field(default=None))

        self._inferred_schema = create_model(
            f'CSVSchema_{Path(self.path).stem}_inferred',
            **fields,
            __base__=DataFrameSchema
        )
        return self._inferred_schema

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path, dtype=self.dtype, encoding=self.encoding)
        df.attrs["security_level"] = self.security_level
        df.attrs["determinism_level"] = self.determinism_level
        df.attrs["schema"] = self.output_schema()  # NEW: Attach schema
        return df

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

def _pandas_dtype_to_python(dtype: np.dtype) -> type:
    """Convert pandas dtype to Python type."""
    if pd.api.types.is_integer_dtype(dtype):
        return int
    elif pd.api.types.is_float_dtype(dtype):
        return float
    elif pd.api.types.is_bool_dtype(dtype):
        return bool
    else:
        return str
```

---

### Phase 2: Validation Integration (1 day)

**FR6: Experiment Runner Schema Validation**

```python
# src/elspeth/core/experiments/runner.py

class ExperimentRunner:
    def run(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Execute experiment with schema validation."""

        # Validate schemas at start (fail fast)
        datasource_schema = df.attrs.get("schema")
        if datasource_schema:
            self._validate_plugin_schemas(datasource_schema)

        # ... rest of execution

    def _validate_plugin_schemas(self, datasource_schema: Type[DataFrameSchema]) -> None:
        """Validate all plugins are compatible with datasource schema."""

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
                        f"Row plugin '{plugin.name}' schema incompatible with datasource:\n{e}"
                    )

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
                        f"Aggregator '{aggregator.name}' schema incompatible with datasource:\n{e}"
                    )

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
                        f"Validator '{validator.name}' schema incompatible with datasource:\n{e}"
                    )
```

**FR7: Optional Runtime Validation (Strict Mode)**

```python
# src/elspeth/core/pipeline/processing.py

def prepare_prompt_context(
    row: pd.Series,
    *,
    include_fields: Iterable[str] | None = None,
    alias_map: Dict[str, str] | None = None,
    schema: Optional[Type[DataFrameSchema]] = None,  # NEW
    strict: bool = False,  # NEW: Enable runtime validation
) -> Dict[str, Any]:
    """Prepare prompt context from DataFrame row.

    Args:
        row: DataFrame row
        include_fields: Optional field filtering
        alias_map: Field renaming
        schema: Optional Pydantic schema for validation
        strict: If True, validate against schema at runtime

    Returns:
        Dict of row data, optionally validated

    Raises:
        ValidationError: If strict=True and validation fails
    """
    data = row.to_dict()

    # Runtime validation (optional, for strict mode)
    if strict and schema:
        try:
            validated_model = schema(**data)
            data = validated_model.dict()
        except ValidationError as e:
            raise ValueError(
                f"Row validation failed:\n{e}"
            )

    # Apply field filtering
    if include_fields is not None:
        data = {k: data.get(k) for k in include_fields}

    # Apply aliasing
    if alias_map:
        data = {alias_map.get(k, k): v for k, v in data.items()}

    return data
```

---

### Phase 3: Plugin Schema Implementations (1 day)

**FR8: Built-in Plugin Schemas**

```python
# src/elspeth/plugins/experiments/metrics.py

from elspeth.core.interfaces import DataFrameSchema
from pydantic import Field

# Score Extractor Plugin
class ScoreExtractorSchema(DataFrameSchema):
    """Input schema for ScoreExtractorPlugin."""
    # No required fields - reads from LLM response, not row

class ScoreExtractorPlugin:
    name = "score_extractor"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return ScoreExtractorSchema  # No row requirements

    def process_row(self, row: Dict[str, Any], responses: Dict[str, Any]) -> Dict[str, Any]:
        # Extract score from LLM response
        ...

# Statistics Aggregator
class StatisticsAggregatorSchema(DataFrameSchema):
    """Input schema for StatisticsAggregator."""
    score: float = Field(description="Numeric score to aggregate")

class StatisticsAggregator:
    name = "statistics"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return StatisticsAggregatorSchema

    def finalize(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Aggregate scores
        scores = [r["score"] for r in records if "score" in r]
        ...

# RAG Query Plugin
class RAGQuerySchema(DataFrameSchema):
    """Input schema for RAGQueryPlugin."""
    question: str = Field(description="Question text for RAG retrieval")
    context: Optional[str] = Field(default=None, description="Optional additional context")

class RAGQueryPlugin:
    name = "rag_query"

    def input_schema(self) -> Optional[Type[DataFrameSchema]]:
        return RAGQuerySchema

    def process_row(self, row: Dict[str, Any], responses: Dict[str, Any]) -> Dict[str, Any]:
        # Query retrieval system
        question = row["question"]  # Type-safe: validated by schema
        ...
```

**FR9: Validation Plugin Schemas**

```python
# src/elspeth/plugins/experiments/validation.py

class RegexValidatorSchema(DataFrameSchema):
    """Input schema for RegexValidator."""
    # Validates LLM response, not row data - no requirements

class JSONValidatorSchema(DataFrameSchema):
    """Input schema for JSONValidator."""
    # Validates LLM response structure - no row requirements

class LLMGuardSchema(DataFrameSchema):
    """Input schema for LLMGuardValidator."""
    expected_answer: Optional[str] = Field(default=None, description="Expected answer for comparison")
```

---

### Phase 4: CLI and Tooling (0.5 days)

**FR10: Schema Validation CLI Command**

```python
# src/elspeth/cli.py (new command)

@click.command()
@click.option("--settings", required=True, help="Path to settings YAML")
@click.option("--suite-root", help="Suite root directory")
def validate_schemas(settings: str, suite_root: str | None) -> None:
    """Validate all experiment schemas for compatibility.

    Checks:
        1. All datasources declare valid schemas
        2. All plugins declare valid schemas
        3. All plugin requirements are satisfied by datasources
        4. Security clearances are compatible

    Exits with code 0 if all schemas valid, 1 if any issues found.
    """
    config = load_settings(settings, suite_root)

    errors = []

    for experiment_config in config["experiments"]:
        exp_name = experiment_config["name"]

        try:
            # Validate datasource schema
            ds_plugin = experiment_config["datasource"]["plugin"]
            ds_options = experiment_config["datasource"]["options"]
            datasource = registry.create_datasource(ds_plugin, ds_options)

            ds_schema = datasource.output_schema()
            if not ds_schema:
                print(f"⚠️  {exp_name}: Datasource '{ds_plugin}' has no schema (skipping validation)")
                continue

            print(f"✓ {exp_name}: Datasource schema OK ({len(ds_schema.__fields__)} fields)")

            # Validate each plugin
            for plugin_config in experiment_config.get("row_plugins", []):
                plugin_name = plugin_config["plugin"]
                plugin = _load_plugin(plugin_name, plugin_config.get("options", {}))

                plugin_schema = getattr(plugin, "input_schema", lambda: None)()
                if plugin_schema:
                    validate_schema_compatibility(ds_schema, plugin_schema, context=f"{exp_name}:{plugin_name}")
                    print(f"  ✓ Plugin '{plugin_name}' schema compatible")
                else:
                    print(f"  ⚠️  Plugin '{plugin_name}' has no schema (skipping)")

        except (SchemaCompatibilityError, ConfigurationError) as e:
            errors.append(f"{exp_name}: {e}")
            print(f"❌ {exp_name}: {e}")

    if errors:
        print(f"\n❌ Schema validation failed ({len(errors)} errors)")
        sys.exit(1)
    else:
        print(f"\n✅ All schemas valid")
        sys.exit(0)
```

**Usage**:
```bash
# Validate schemas before running suite
elspeth validate-schemas --settings config/sample_suite/settings.yaml

# Output:
# ✓ score_extraction: Datasource schema OK (4 fields)
#   ✓ Plugin 'score_extractor' schema compatible
#   ✓ Plugin 'statistics' schema compatible
# ✅ All schemas valid
```

---

### Phase 5: Documentation and Migration (0.5 days)

**FR11: Documentation Updates**

1. **docs/architecture/schema-validation.md**: New document explaining schema system
2. **docs/architecture/plugin-catalogue.md**: Update all plugin entries with schema information
3. **CLAUDE.md**: Add section on schema validation best practices
4. **README.md**: Add schema validation to feature list

**FR12: Migration Guide**

```markdown
# Schema Validation Migration Guide

## For Datasource Implementers

### Before (No Schema)
```python
class MyDataSource:
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        return df
```

### After (With Schema)
```python
from elspeth.core.interfaces import DataFrameSchema
from pydantic import create_model, Field

class MyDataSource:
    def output_schema(self) -> Type[DataFrameSchema]:
        # Option 1: Explicit schema
        class MySchema(DataFrameSchema):
            user_id: int
            name: str
            score: float = Field(ge=0, le=100)
        return MySchema

        # Option 2: Infer from data
        return self._infer_schema_from_file()

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        df.attrs["schema"] = self.output_schema()  # Attach schema
        return df
```

## For Plugin Implementers

### Before (No Schema)
```python
class MyPlugin:
    def process_row(self, row: Dict[str, Any], responses):
        score = row.get("score", 0)  # Hope "score" exists!
        return {"result": score * 2}
```

### After (With Schema)
```python
class MyPluginSchema(DataFrameSchema):
    score: int = Field(ge=0, description="Required score field")
    notes: Optional[str] = Field(default=None)

class MyPlugin:
    def input_schema(self) -> Type[DataFrameSchema]:
        return MyPluginSchema

    def process_row(self, row: Dict[str, Any], responses):
        score = row["score"]  # Type-safe: schema validated
        return {"result": score * 2}
```
```

**FR13: Backwards Compatibility**

- All schema methods return `Optional[Type[DataFrameSchema]]`
- `None` return = no validation (backwards compatible)
- Existing code continues to work without modification
- Schema validation only runs when both datasource and plugin declare schemas

---

## 4. Testing Strategy

### Unit Tests

```python
# tests/test_schema_validation.py

def test_schema_compatibility_exact_match():
    """Test exact schema match passes validation."""
    class SourceSchema(DataFrameSchema):
        id: int
        name: str

    class RequiredSchema(DataFrameSchema):
        id: int
        name: str

    validate_schema_compatibility(SourceSchema, RequiredSchema)  # Should pass

def test_schema_compatibility_missing_required_field():
    """Test missing required field fails validation."""
    class SourceSchema(DataFrameSchema):
        id: int

    class RequiredSchema(DataFrameSchema):
        id: int
        name: str  # Missing in source

    with pytest.raises(SchemaCompatibilityError, match="Missing required field 'name'"):
        validate_schema_compatibility(SourceSchema, RequiredSchema)

def test_schema_compatibility_optional_field():
    """Test missing optional field passes validation."""
    class SourceSchema(DataFrameSchema):
        id: int

    class RequiredSchema(DataFrameSchema):
        id: int
        name: Optional[str] = None

    validate_schema_compatibility(SourceSchema, RequiredSchema)  # Should pass

def test_schema_compatibility_type_mismatch():
    """Test incompatible types fail validation."""
    class SourceSchema(DataFrameSchema):
        score: str  # String

    class RequiredSchema(DataFrameSchema):
        score: int  # Int

    with pytest.raises(SchemaCompatibilityError, match="type mismatch"):
        validate_schema_compatibility(SourceSchema, RequiredSchema)

def test_schema_inference_csv():
    """Test schema inference from CSV header."""
    csv_content = "id,name,score\n1,Alice,95\n2,Bob,87\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        path = f.name

    try:
        ds = CSVDataSource(path=path, security_level="OFFICIAL", determinism_level="guaranteed")
        schema = ds.output_schema()

        assert schema is not None
        assert "id" in schema.__fields__
        assert "name" in schema.__fields__
        assert "score" in schema.__fields__
    finally:
        os.unlink(path)
```

### Integration Tests

```python
# tests/test_schema_integration.py

def test_experiment_runner_schema_validation():
    """Test ExperimentRunner validates schemas at startup."""

    # Create datasource with schema
    df = pd.DataFrame({"id": [1, 2], "score": [95, 87]})

    class DSSchema(DataFrameSchema):
        id: int
        score: int

    df.attrs["schema"] = DSSchema

    # Create plugin requiring "name" field (missing)
    class PluginSchema(DataFrameSchema):
        id: int
        name: str  # Missing!

    class TestPlugin:
        name = "test"
        def input_schema(self):
            return PluginSchema

    runner = ExperimentRunner(row_plugins=[TestPlugin()])

    with pytest.raises(ConfigurationError, match="Missing required field 'name'"):
        runner.run(df)

def test_cli_validate_schemas_command():
    """Test CLI schema validation command."""
    result = subprocess.run(
        ["elspeth", "validate-schemas", "--settings", "config/sample_suite/settings.yaml"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "✅ All schemas valid" in result.stdout
```

### Negative Tests

```python
# tests/test_schema_errors.py

def test_clear_error_message_missing_field():
    """Test error message clearly identifies missing field."""
    class SourceSchema(DataFrameSchema):
        id: int

    class RequiredSchema(DataFrameSchema):
        id: int
        name: str
        email: str

    with pytest.raises(SchemaCompatibilityError) as exc_info:
        validate_schema_compatibility(SourceSchema, RequiredSchema)

    error_msg = str(exc_info.value)
    assert "Missing required field 'name'" in error_msg
    assert "Missing required field 'email'" in error_msg

def test_clear_error_message_type_mismatch():
    """Test error message clearly identifies type mismatch."""
    class SourceSchema(DataFrameSchema):
        score: str

    class RequiredSchema(DataFrameSchema):
        score: int

    with pytest.raises(SchemaCompatibilityError) as exc_info:
        validate_schema_compatibility(SourceSchema, RequiredSchema)

    error_msg = str(exc_info.value)
    assert "Field 'score' type mismatch" in error_msg
    assert "source provides" in error_msg.lower()
    assert "plugin requires" in error_msg.lower()
```

---

## 5. Configuration Examples

### Example 1: Explicit Schema Declaration

```yaml
# config/sample_suite/settings.yaml

datasource:
  plugin: local_csv
  options:
    path: "data/qa_pairs.csv"
    security_level: OFFICIAL
    determinism_level: guaranteed
    schema:  # Explicit declaration
      APPID: str
      question: str
      expected_answer: str
      category: str
      difficulty: int

experiments:
  - name: qa_evaluation
    row_plugins:
      - plugin: score_extractor
        # No schema required - reads from LLM response

      - plugin: custom_validator
        schema:  # Plugin declares requirements
          expected_answer: str
          category: str

    aggregators:
      - plugin: statistics
        schema:
          score: float  # Requires score from score_extractor
```

### Example 2: Schema Inference

```yaml
datasource:
  plugin: local_csv
  options:
    path: "data/user_feedback.csv"
    security_level: OFFICIAL
    determinism_level: high
    # No explicit schema - infer from CSV header
    dtype:  # Optional: type hints for inference
      user_id: int
      rating: float
      comment: str
```

### Example 3: Complex Schema with Validation Rules

```yaml
datasource:
  plugin: local_csv
  options:
    path: "data/scores.csv"
    security_level: OFFICIAL_SENSITIVE
    determinism_level: guaranteed
    schema:
      student_id: int
      assignment: str
      score:
        type: int
        min: 0
        max: 100
        description: "Assignment score percentage"
      submitted_date: str
      grader_notes: str
```

---

## 6. Error Messages and User Experience

### Config-Time Error (Good UX)

```
❌ Configuration Error: Schema compatibility check failed

Experiment: score_extraction
Plugin: statistics (aggregator)

Schema mismatch:
  - Missing required field 'score'
    Plugin requires: score (type: float)
    Datasource provides: [APPID, question, expected_answer, category]

Suggestion: Add 'score_extractor' row plugin before 'statistics' aggregator,
           or update datasource to include 'score' column.

Configuration file: config/sample_suite/settings.yaml:45
```

### Runtime Error (Avoided by schema validation)

```
# Before schema validation (BAD):
Traceback (most recent call last):
  File "src/elspeth/plugins/experiments/metrics.py", line 120, in finalize
    scores = [r["score"] for r in records]
KeyError: 'score'

# After schema validation (GOOD):
# Error caught at config load time with clear message ✅
```

---

## 7. Performance Considerations

### Schema Validation Overhead

1. **Config-Time**: Negligible (<1ms per plugin)
2. **DataFrame Load**: Small overhead for schema inference (~10-50ms for typical CSV)
3. **Runtime Validation** (optional strict mode): ~1-5ms per row (disabled by default)

### Optimization Strategies

1. **Lazy Schema Inference**: Only infer schema when `output_schema()` is called
2. **Schema Caching**: Cache inferred schemas per datasource instance
3. **Optional Runtime Validation**: Disable by default, enable for debugging
4. **Early Validation**: Fail fast at configuration load, not during execution

---

## 8. Future Enhancements

### Post-MVP Features

1. **Schema Registry**: Central registry of reusable schema definitions
2. **Schema Evolution**: Handle schema migrations (add/remove columns)
3. **Custom Validators**: Pydantic field validators for business rules
4. **Schema Documentation**: Auto-generate docs from Pydantic models
5. **IDE Integration**: Type hints for autocomplete in plugin development

### Pydantic V2 Features

1. **Performance**: Pydantic v2 is 5-50x faster than v1
2. **JSON Schema**: Better OpenAPI/JSON Schema generation
3. **Serialization**: Efficient dict/JSON conversion
4. **Strict Mode**: Enforce exact types (no coercion)

---

## 9. Dependencies

### Required Packages

```toml
# pyproject.toml

[project.dependencies]
pydantic = "^2.0"  # Core validation library
```

### No Breaking Changes Required

- Existing code continues to work (schemas optional)
- Gradual migration path
- No changes to DataFrame structure

---

## 10. Success Criteria

### Functional Requirements

- ✅ Datasources can declare output schemas (optional)
- ✅ Plugins can declare input requirements (optional)
- ✅ Config-time validation when schemas present
- ✅ Clear error messages for schema mismatches
- ✅ Schema inference for CSV datasources

### Non-Functional Requirements

- ✅ Backwards compatible (existing code works)
- ✅ <10ms overhead for schema inference
- ✅ <1ms overhead for config-time validation
- ✅ 100% test coverage for validation logic
- ✅ Comprehensive documentation

### User Experience

- ✅ Fail fast at config time (not runtime)
- ✅ Clear, actionable error messages
- ✅ CLI tool for pre-flight validation
- ✅ Optional strict mode for runtime checking

---

## 11. Change Log

- **2025-10-13**: Initial draft based on user requirements and codebase analysis
- **2025-10-13**: Added Pydantic-based architecture and implementation plan
- **2025-10-13**: Added CLI validation command and migration guide
