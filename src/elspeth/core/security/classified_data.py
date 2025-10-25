"""ClassifiedDataFrame - DataFrame wrapper with immutable classification metadata.

This module implements ADR-002 classification uplifting and data tainting for
suite-level security enforcement.

Security Properties:
1. Classification is IMMUTABLE after creation (frozen dataclass)
2. Uplifting is AUTOMATIC via max() operation (never downgrades)
3. Access validation enforces clearance checks (runtime failsafe)

CRITICAL: Classification uplifting is NOT optional - it's enforced by the
          type system and immutability guarantees.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from elspeth.core.base.types import SecurityLevel

if TYPE_CHECKING:
    from elspeth.core.base.protocols import BasePlugin


@dataclass(frozen=True)
class ClassifiedDataFrame:
    """DataFrame wrapper with immutable classification metadata.

    Represents data with a specific security classification that cannot be
    downgraded. Supports automatic classification uplifting when data passes
    through higher-security components.

    Security Model (ADR-002-A Trusted Container):
        - Classification is immutable (frozen dataclass)
        - Only datasources can create instances (constructor protection)
        - Plugins can only uplift, never relabel (prevents laundering)
        - Uplifting creates new instance (original unchanged)
        - Downgrading is impossible (max() operation prevents it)
        - Access validation provides runtime failsafe

    Creation Patterns:
        Datasource (trusted source):
            >>> frame = ClassifiedDataFrame.create_from_datasource(
            ...     data, SecurityLevel.OFFICIAL
            ... )

        Plugin transformation (in-place mutation):
            >>> frame.data['processed'] = transform(frame.data['input'])
            >>> result = frame.with_uplifted_classification(plugin.get_security_level())

        Plugin data generation (LLMs, aggregations):
            >>> new_df = llm.generate(...)
            >>> result = frame.with_new_data(new_df).with_uplifted_classification(
            ...     plugin.get_security_level()
            ... )

        Anti-Pattern (BLOCKED):
            >>> ClassifiedDataFrame(data, level)  # SecurityValidationError

    ADR-002 Threat Prevention:
        - T4 (Classification Mislabeling): Constructor protection prevents laundering
        - T3 (Runtime Bypass): validate_access_by() catches start-time validation bypass
    """

    data: pd.DataFrame
    classification: SecurityLevel
    _created_by_datasource: bool = field(default=False, init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Enforce datasource-only creation (ADR-002-A constructor protection).

        Only datasources can create ClassifiedDataFrame instances from scratch.
        Plugins must use with_uplifted_classification() or with_new_data().

        This prevents classification laundering attacks where malicious plugins
        create "fresh" frames with lower classifications, bypassing uplifting logic.

        Raises:
            SecurityValidationError: If called from non-trusted context
        """
        import inspect

        # Allow datasource factory
        if object.__getattribute__(self, "_created_by_datasource"):
            return

        # Walk up call stack to find trusted methods
        # __post_init__ is called by __init__, which is called by the method we care about
        frame = inspect.currentframe()
        if frame is None:
            # Cannot determine caller - allow (fail-open for edge cases)
            return

        # Check up to 5 frames up the stack for trusted callers
        current_frame = frame
        for _ in range(5):
            if current_frame is None or current_frame.f_back is None:
                break
            current_frame = current_frame.f_back
            caller_name = current_frame.f_code.co_name

            # Allow internal methods (with_uplifted_classification, with_new_data)
            # SECURITY: Verify this is OUR method, not a spoofed function (CVE-ADR-002-A-001)
            if caller_name in ("with_uplifted_classification", "with_new_data"):
                # Verify the caller's 'self' is actually a ClassifiedDataFrame instance
                caller_self = current_frame.f_locals.get('self')
                if isinstance(caller_self, ClassifiedDataFrame):
                    return  # Legitimate internal method call

        # Block all other attempts (plugins, direct construction)
        from elspeth.core.validation.base import SecurityValidationError

        raise SecurityValidationError(
            "ClassifiedDataFrame can only be created by datasources using "
            "create_from_datasource(). Plugins must use with_uplifted_classification() "
            "to uplift existing frames or with_new_data() to generate new data. "
            "This prevents classification laundering attacks (ADR-002-A)."
        )

    @classmethod
    def create_from_datasource(
        cls, data: pd.DataFrame, classification: SecurityLevel
    ) -> "ClassifiedDataFrame":
        """Create ClassifiedDataFrame from datasource (trusted source only).

        This is the ONLY way to create a ClassifiedDataFrame from scratch.
        Datasources are trusted to label data with correct classification.

        Args:
            data: Pandas DataFrame containing the data
            classification: Security classification of the data

        Returns:
            New ClassifiedDataFrame with datasource-authorized creation

        Security:
            - This factory method sets _created_by_datasource=True
            - This allows __post_init__ validation to pass
            - Only datasources should call this method (verified during certification)

        Example:
            >>> # In datasource implementation
            >>> df = pd.DataFrame({"data": [1, 2, 3]})
            >>> frame = ClassifiedDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
        """
        # Use __new__ to bypass __init__ and set fields manually
        instance = cls.__new__(cls)
        object.__setattr__(instance, "data", data)
        object.__setattr__(instance, "classification", classification)
        object.__setattr__(instance, "_created_by_datasource", True)
        return instance

    def with_uplifted_classification(
        self, new_level: SecurityLevel
    ) -> "ClassifiedDataFrame":
        """Return new instance with uplifted classification (immutable update).

        Classification uplifting enforces the "high water mark" principle:
        data passing through a high-security component inherits the higher
        classification automatically and irreversibly.

        Args:
            new_level: Security level to uplift to

        Returns:
            New ClassifiedDataFrame with max(current, new_level) classification

        Note:
            This is NOT a downgrade operation - if new_level < current classification,
            the current classification is preserved (max() operation).

        Example:
            >>> # OFFICIAL data through SECRET LLM
            >>> input_df = ClassifiedDataFrame.create_from_datasource(
            ...     data, SecurityLevel.OFFICIAL
            ... )
            >>> llm_level = SecurityLevel.SECRET
            >>> output_df = input_df.with_uplifted_classification(llm_level)
            >>> assert output_df.classification == SecurityLevel.SECRET
            >>>
            >>> # Attempting to "downgrade" preserves higher classification
            >>> result = output_df.with_uplifted_classification(SecurityLevel.OFFICIAL)
            >>> assert result.classification == SecurityLevel.SECRET  # max() wins
        """
        uplifted_classification = max(self.classification, new_level)

        # Use __new__ to bypass __init__ (same pattern as create_from_datasource)
        instance = ClassifiedDataFrame.__new__(ClassifiedDataFrame)
        object.__setattr__(instance, "data", self.data)
        object.__setattr__(instance, "classification", uplifted_classification)
        object.__setattr__(instance, "_created_by_datasource", False)
        return instance

    def with_new_data(self, new_data: pd.DataFrame) -> "ClassifiedDataFrame":
        """Create frame with different data, preserving current classification.

        For plugins that generate entirely new DataFrames (LLMs, aggregations)
        that cannot mutate .data in-place due to schema changes.

        Args:
            new_data: New pandas DataFrame to wrap

        Returns:
            New ClassifiedDataFrame with new data but SAME classification

        Security:
            - Preserves current classification (cannot downgrade)
            - Plugin must still call with_uplifted_classification() afterwards
            - Bypasses __post_init__ validation (trusted internal method)

        Example:
            >>> # LLM generates new DataFrame
            >>> input_frame = ClassifiedDataFrame.create_from_datasource(
            ...     input_df, SecurityLevel.OFFICIAL
            ... )
            >>> new_df = llm.generate(...)
            >>> output_frame = input_frame.with_new_data(new_df)
            >>> # Must still uplift to LLM's security level
            >>> final_frame = output_frame.with_uplifted_classification(
            ...     SecurityLevel.SECRET
            ... )
        """
        # Use __new__ to bypass __init__ (same pattern as create_from_datasource)
        instance = ClassifiedDataFrame.__new__(ClassifiedDataFrame)
        object.__setattr__(instance, "data", new_data)
        object.__setattr__(instance, "classification", self.classification)
        object.__setattr__(instance, "_created_by_datasource", False)
        return instance

    def validate_access_by(self, accessor: "BasePlugin") -> None:
        """Validate accessor has sufficient clearance for this data.

        Runtime failsafe that enforces clearance checks at every data hand-off.
        This provides defense-in-depth if start-time validation is bypassed.

        Args:
            accessor: Plugin attempting to access this data

        Raises:
            SecurityValidationError: If accessor clearance < data classification

        Security Property:
            accessor.get_security_level() >= self.classification

        Example:
            >>> secret_df = ClassifiedDataFrame.create_from_datasource(
            ...     data, SecurityLevel.SECRET
            ... )
            >>> unofficial_sink = UnofficialSink()  # Reports UNOFFICIAL clearance
            >>>
            >>> secret_df.validate_access_by(unofficial_sink)
            >>> # Raises: SecurityValidationError("Cannot provide SECRET data to
            >>> #         UnofficialSink (clearance: UNOFFICIAL)")

        ADR-002 Threat Prevention:
            - T3 (Runtime Bypass): Catches if start-time validation bypassed/broken
            - Defense in depth: Redundant with start-time validation (PRIMARY control)
        """
        from elspeth.core.validation.base import SecurityValidationError

        accessor_clearance = accessor.get_security_level()

        if accessor_clearance < self.classification:
            raise SecurityValidationError(
                f"Cannot provide {self.classification.name} data to "
                f"{accessor.__class__.__name__} (clearance: {accessor_clearance.name}). "
                f"This is a runtime failsafe - start-time validation should have "
                f"prevented this configuration."
            )
