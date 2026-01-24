"""Plugin configuration validation subsystem.

Validates plugin configurations BEFORE instantiation, providing clear error
messages and enabling test fixtures to bypass validation when needed.

Design:
- Validation is separate from plugin construction
- Returns structured errors (not exceptions) for better error messages
- Validates against Pydantic config models (CSVSourceConfig, etc.)
- Does NOT instantiate plugins (just validates config)

Usage:
    validator = PluginConfigValidator()
    errors = validator.validate_source_config("csv", config)
    if errors:
        raise ValueError(f"Invalid config: {errors}")
    source = CSVSource(config)  # Assumes config is valid
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError as PydanticValidationError

if TYPE_CHECKING:
    from elspeth.plugins.config_base import PluginConfig


@dataclass
class ValidationError:
    """Structured validation error.

    Attributes:
        field: Field name that failed validation
        message: Human-readable error message
        value: The invalid value (for debugging)
    """

    field: str
    message: str
    value: Any


class PluginConfigValidator:
    """Validates plugin configurations before instantiation.

    Validates configs against Pydantic models (CSVSourceConfig, etc.)
    without actually instantiating the plugin.
    """

    def validate_source_config(
        self,
        source_type: str,
        config: dict[str, Any],
    ) -> list[ValidationError]:
        """Validate source plugin configuration.

        Args:
            source_type: Plugin type name (e.g., "csv", "json")
            config: Plugin configuration dict

        Returns:
            List of validation errors (empty if valid)
        """
        # Get config model for source type
        config_model = self._get_source_config_model(source_type)

        # Handle special case: null_source has no config class
        if config_model is None:
            return []  # No validation needed

        # Validate using Pydantic
        try:
            config_model.from_dict(config)
            return []  # Valid
        except PydanticValidationError as e:
            return self._extract_errors(e)
        except Exception as e:
            # from_dict wraps ValidationError in PluginConfigError
            # Extract the original Pydantic error from the exception chain
            if e.__cause__ and isinstance(e.__cause__, PydanticValidationError):
                return self._extract_errors(e.__cause__)
            raise  # Re-raise if not a wrapped validation error

    def _get_source_config_model(self, source_type: str) -> type["PluginConfig"] | None:
        """Get Pydantic config model for source type.

        Returns:
            Config model class, or None for sources with no config (e.g., null_source)
        """
        # Import here to avoid circular dependencies
        if source_type == "csv":
            from elspeth.plugins.sources.csv_source import CSVSourceConfig

            return CSVSourceConfig
        elif source_type == "json":
            from elspeth.plugins.sources.json_source import JSONSourceConfig

            return JSONSourceConfig
        elif source_type == "null_source":
            # NullSource has no config class (resume-only source)
            # Return None to signal "no validation needed"
            return None
        else:
            raise ValueError(f"Unknown source type: {source_type}")

    def _extract_errors(
        self,
        pydantic_error: PydanticValidationError,
    ) -> list[ValidationError]:
        """Convert Pydantic errors to structured ValidationError list."""
        errors: list[ValidationError] = []

        for err in pydantic_error.errors():
            # Pydantic error dict has: loc, msg, type, ctx
            field_path = ".".join(str(loc) for loc in err["loc"])
            message = err["msg"]

            # Try to extract the invalid value from input
            value = err.get("input", "<unknown>")

            errors.append(
                ValidationError(
                    field=field_path,
                    message=message,
                    value=value,
                )
            )

        return errors
