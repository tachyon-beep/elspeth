"""Core type enumerations for Elspeth framework.

This module defines type-safe enumerations for security levels, determinism levels,
and data types used throughout the framework.
"""

from enum import Enum
from typing import Any


class SecurityLevel(str, Enum):
    """Australian Government PSPF security classification levels.

    These levels form a strict hierarchy from least to most restrictive:
    UNOFFICIAL < OFFICIAL < OFFICIAL_SENSITIVE < PROTECTED < SECRET

    Security aggregation rule: MOST restrictive wins.
    Example: OFFICIAL + SECRET → SECRET

    Note: The string "SECRET" below is a classification level name, not a password.
    """

    UNOFFICIAL = "UNOFFICIAL"
    OFFICIAL = "OFFICIAL"
    OFFICIAL_SENSITIVE = "OFFICIAL: SENSITIVE"
    PROTECTED = "PROTECTED"
    # This is a classification level, not a password
    SECRET = "SECRET"  # noqa: S105  # nosec B105: classification level label, not a password/secret

    def __lt__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        if not isinstance(other, SecurityLevel):
            return NotImplemented
        order = [
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.OFFICIAL_SENSITIVE,
            SecurityLevel.PROTECTED,
            SecurityLevel.SECRET,
        ]
        return order.index(self) < order.index(other)

    def __le__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        return self == other or self < other

    def __gt__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        if not isinstance(other, SecurityLevel):
            return NotImplemented
        return other < self

    def __ge__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        return self == other or self > other

    @classmethod
    def from_string(cls, value: str | None) -> "SecurityLevel":
        """Parse a string into a SecurityLevel enum.

        Handles case-insensitive input and common aliases.

        Args:
            value: String representation (e.g., "official", "OFFICIAL")

        Returns:
            SecurityLevel enum value

        Raises:
            ValueError: If the string doesn't match any known level
        """
        if value is None or not str(value).strip():
            return cls.UNOFFICIAL

        # Replace punctuation sequences with single underscore
        # Order matters: replace ": " (colon-space) first to avoid double underscores
        normalized = str(value).strip().upper().replace(": ", "_").replace("-", "_").replace(" ", "_").replace(":", "_")

        # Handle legacy/alias mappings
        aliases = {
            "PUBLIC": cls.UNOFFICIAL,
            "INTERNAL": cls.OFFICIAL,
            "CONFIDENTIAL": cls.PROTECTED,
            "SENSITIVE": cls.OFFICIAL_SENSITIVE,
        }

        if normalized in aliases:
            return aliases[normalized]

        try:
            return cls[normalized]  # Lookup by enum name, not value
        except KeyError as exc:
            valid_levels = ", ".join(level.value for level in cls)
            raise ValueError(f"Unknown security level '{value}'. Must be one of: {valid_levels}") from exc


class DeterminismLevel(str, Enum):
    """Determinism spectrum for reproducibility guarantees.

    These levels form a spectrum from least to most deterministic:
    NONE < LOW < HIGH < GUARANTEED

    Determinism aggregation rule: LEAST deterministic wins (opposite of security).
    Example: HIGH + NONE → NONE

    Level Definitions:
        NONE: High variance, non-deterministic (e.g., no seed, wall-clock timing, network jitter)
        LOW: Moderate variance, same distribution (e.g., LLM temp>0 with seed, randomized algorithms)
        HIGH: Negligible variance (e.g., LLM temp=0 with seed, floating-point rounding)
        GUARANTEED: Zero variance, cryptographically identical (e.g., static data, deterministic algorithms)
    """

    NONE = "none"
    LOW = "low"
    HIGH = "high"
    GUARANTEED = "guaranteed"

    def __lt__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        if not isinstance(other, DeterminismLevel):
            return NotImplemented
        order = [
            DeterminismLevel.NONE,
            DeterminismLevel.LOW,
            DeterminismLevel.HIGH,
            DeterminismLevel.GUARANTEED,
        ]
        return order.index(self) < order.index(other)

    def __le__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        return self == other or self < other

    def __gt__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        if not isinstance(other, DeterminismLevel):
            return NotImplemented
        return other < self

    def __ge__(self, other: str) -> Any:
        """Support comparison for hierarchy enforcement."""
        return self == other or self > other

    @classmethod
    def from_string(cls, value: str | None) -> "DeterminismLevel":
        """Parse a string into a DeterminismLevel enum.

        Handles case-insensitive input.

        Args:
            value: String representation (e.g., "high", "HIGH", "guaranteed")

        Returns:
            DeterminismLevel enum value

        Raises:
            ValueError: If the string doesn't match any known level
        """
        if value is None or not str(value).strip():
            return cls.NONE

        normalized = str(value).strip().lower()

        try:
            return cls(normalized)
        except ValueError as exc:
            valid_levels = ", ".join(level.value for level in cls)
            raise ValueError(f"Unknown determinism level '{value}'. Must be one of: {valid_levels}") from exc


class DataType(str, Enum):
    """Data type enumeration for DataFrame schema validation.

    These types represent the semantic data types that can appear in DataFrames.
    Each type maps to underlying Pandas dtypes but provides semantic meaning.

    Simple Types:
        STRING: Text data (maps to object/string dtype)
        CHAR: Single character (maps to object dtype with length validation)
        INT: Integer numbers (maps to int64)
        FLOAT: Floating-point numbers (maps to float64)
        BOOL: Boolean values (maps to bool)
        DATETIME: Date and time (maps to datetime64)
        DATE: Date only (maps to datetime64 with time=00:00:00)
        TIME: Time only (maps to timedelta64 or object)

    Complex Types:
        JSON: JSON-encoded data (maps to object dtype with JSON validation)
        XML: XML-encoded data (maps to object dtype with XML validation)
        BINARY: Binary data (maps to object dtype containing bytes)
        ARRAY: Array/list data (maps to object dtype containing lists)
        OBJECT: Generic object (maps to object dtype, no validation)

    Numeric Types:
        INT8, INT16, INT32, INT64: Specific integer sizes
        UINT8, UINT16, UINT32, UINT64: Unsigned integer sizes
        FLOAT16, FLOAT32, FLOAT64: Specific float sizes

    Category Type:
        CATEGORY: Categorical data (maps to category dtype)
    """

    # Simple types
    STRING = "string"
    CHAR = "char"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATETIME = "datetime"
    DATE = "date"
    TIME = "time"

    # Complex types
    JSON = "json"
    XML = "xml"
    BINARY = "binary"
    ARRAY = "array"
    OBJECT = "object"

    # Specific numeric types
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    INT64 = "int64"
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    FLOAT16 = "float16"
    FLOAT32 = "float32"
    FLOAT64 = "float64"

    # Category type
    CATEGORY = "category"

    @classmethod
    def from_string(cls, value: str | None) -> "DataType":
        """Parse a string into a DataType enum.

        Handles case-insensitive input and common aliases.

        Args:
            value: String representation (e.g., "string", "STRING", "str")

        Returns:
            DataType enum value

        Raises:
            ValueError: If the string doesn't match any known type
        """
        if value is None or not str(value).strip():
            raise ValueError("DataType cannot be None or empty")

        normalized = str(value).strip().lower()

        # Handle aliases
        aliases = {
            "str": cls.STRING,
            "text": cls.STRING,
            "integer": cls.INT,
            "double": cls.FLOAT,
            "number": cls.FLOAT,
            "boolean": cls.BOOL,
            "timestamp": cls.DATETIME,
            "bytes": cls.BINARY,
            "list": cls.ARRAY,
        }

        if normalized in aliases:
            return aliases[normalized]

        try:
            return cls(normalized)
        except ValueError as exc:
            valid_types = ", ".join(dtype.value for dtype in cls)
            raise ValueError(f"Unknown data type '{value}'. Must be one of: {valid_types}") from exc

    def to_pandas_dtype(self) -> str:
        """Convert DataType enum to Pandas dtype string.

        Returns:
            Pandas dtype string suitable for DataFrame.astype()
        """
        mapping = {
            DataType.STRING: "object",
            DataType.CHAR: "object",
            DataType.INT: "int64",
            DataType.FLOAT: "float64",
            DataType.BOOL: "bool",
            DataType.DATETIME: "datetime64[ns]",
            DataType.DATE: "datetime64[ns]",
            DataType.TIME: "object",
            DataType.JSON: "object",
            DataType.XML: "object",
            DataType.BINARY: "object",
            DataType.ARRAY: "object",
            DataType.OBJECT: "object",
            DataType.INT8: "int8",
            DataType.INT16: "int16",
            DataType.INT32: "int32",
            DataType.INT64: "int64",
            DataType.UINT8: "uint8",
            DataType.UINT16: "uint16",
            DataType.UINT32: "uint32",
            DataType.UINT64: "uint64",
            DataType.FLOAT16: "float16",
            DataType.FLOAT32: "float32",
            DataType.FLOAT64: "float64",
            DataType.CATEGORY: "category",
        }
        return mapping.get(self, "object")


class PluginType(str, Enum):
    """Plugin type enumeration for registry organization.

    These types represent the different kinds of plugins in the Elspeth framework:

    Core Data Flow:
        DATASOURCE: Data source plugins that load input DataFrames
        LLM: LLM client plugins for text generation
        SINK: Output sink plugins that write experiment results

    LLM Enhancement:
        MIDDLEWARE: LLM middleware plugins for request/response processing

    Experiment Plugins:
        ROW_PLUGIN: Row-level experiment processors
        AGGREGATOR: Experiment aggregation plugins
        VALIDATOR: Experiment validation plugins
        EARLY_STOP: Early stopping condition plugins
        BASELINE: Baseline comparison plugins

    Utility:
        UTILITY: Utility plugins (e.g., retrieval_context, embeddings)

    System:
        BACKPLANE: System-level coordination and orchestration plugins
    """

    # Core data flow
    DATASOURCE = "datasource"
    LLM = "llm"
    SINK = "sink"

    # LLM enhancement
    MIDDLEWARE = "middleware"

    # Experiment plugins
    ROW_PLUGIN = "row_plugin"
    AGGREGATOR = "aggregator"
    VALIDATOR = "validator"
    EARLY_STOP = "early_stop"
    BASELINE = "baseline"

    # Utility
    UTILITY = "utility"

    # System
    BACKPLANE = "backplane"

    @classmethod
    def from_string(cls, value: str | None) -> "PluginType":
        """Parse a string into a PluginType enum.

        Handles case-insensitive input and common aliases.

        Args:
            value: String representation (e.g., "datasource", "DATASOURCE", "source")

        Returns:
            PluginType enum value

        Raises:
            ValueError: If the string doesn't match any known type
        """
        if value is None or not str(value).strip():
            raise ValueError("PluginType cannot be None or empty")

        normalized = str(value).strip().lower().replace("-", "_")

        # Handle aliases
        aliases = {
            "source": cls.DATASOURCE,
            "data_source": cls.DATASOURCE,
            "output": cls.SINK,
            "row": cls.ROW_PLUGIN,
            "agg": cls.AGGREGATOR,
            "validation": cls.VALIDATOR,
            "early_stopping": cls.EARLY_STOP,
            "baseline_comparison": cls.BASELINE,
        }

        if normalized in aliases:
            return aliases[normalized]

        try:
            return cls(normalized)
        except ValueError as exc:
            valid_types = ", ".join(ptype.value for ptype in cls)
            raise ValueError(f"Unknown plugin type '{value}'. Must be one of: {valid_types}") from exc


__all__ = ["SecurityLevel", "DeterminismLevel", "DataType", "PluginType"]
