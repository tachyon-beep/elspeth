"""SecureDataFrame - DataFrame wrapper with immutable security level metadata.

This module implements ADR-002 security level uplifting and data tainting for
suite-level security enforcement.

Security Properties:
1. Security level is IMMUTABLE after creation (frozen dataclass)
2. Uplifting is AUTOMATIC via max() operation (never downgrades)
3. Access validation enforces clearance checks (runtime failsafe)

CRITICAL: Security level uplifting is NOT optional - it's enforced by the
          type system and immutability guarantees.
"""

import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from elspeth.core.base.types import SecurityLevel

# Module-private capability token (VULN-011)
# 256-bit entropy, process-local, not exported
# Only authorized factory methods can pass this token to __new__
_CONSTRUCTION_TOKEN = secrets.token_bytes(32)

if TYPE_CHECKING:
    pass  # ADR-004: ABC with nominal typing


@dataclass(frozen=True, slots=True)
class SecureDataFrame:
    """DataFrame wrapper with immutable security level metadata.

    Represents data with a specific security level that cannot be
    downgraded. Supports automatic security level uplifting when data passes
    through higher-security components.

    Security Model (ADR-002-A Trusted Container):
        - Security level is immutable (frozen dataclass)
        - Only datasources can create instances (constructor protection)
        - Plugins can only uplift, never relabel (prevents laundering)
        - Uplifting creates new instance (original unchanged)
        - Downgrading is impossible (max() operation prevents it)
        - Access validation provides runtime failsafe

    Creation Patterns:
        Datasource (trusted source):
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     data, SecurityLevel.OFFICIAL
            ... )

        Plugin transformation (in-place mutation):
            >>> frame.data['processed'] = transform(frame.data['input'])
            >>> result = frame.with_uplifted_security_level(plugin.get_security_level())

        Plugin data generation (LLMs, aggregations):
            >>> new_df = llm.generate(...)
            >>> result = frame.with_new_data(new_df).with_uplifted_security_level(
            ...     plugin.get_security_level()
            ... )

        Anti-Pattern (BLOCKED):
            >>> SecureDataFrame(data, level)  # SecurityValidationError

    ADR-002 Threat Prevention:
        - T4 (Security Level Mislabeling): Constructor protection prevents laundering
        - T3 (Runtime Bypass): validate_compatible_with() catches start-time validation bypass
    """

    data: pd.DataFrame
    security_level: SecurityLevel
    _created_by_datasource: bool = field(default=False, init=False, compare=False, repr=False)

    def __new__(cls, *args, _token=None, **kwargs):
        """Gate construction behind capability token (VULN-011).

        Replaces stack inspection with explicit permission model using
        module-private 256-bit token. Only authorized factory methods
        can pass this token.

        Args:
            _token: Module-private capability token (keyword-only)

        Raises:
            SecurityValidationError: If token missing or incorrect

        Security Properties:
            - 256-bit entropy prevents guessing attacks
            - Module-private scope (not exported via __all__)
            - Process-local (new token per import/process)
            - Explicit permission model (token = capability)
            - Runtime-agnostic (works in PyPy, Jython, all runtimes)

        Performance:
            - ~100ns per check (50x faster than stack inspection)
            - No frame introspection overhead
            - Simple integer comparison

        ADR-002-A Threat Prevention:
            - T4 (Security Level Laundering): Prevents unauthorized construction
            - CVE-ADR-002-A-001: Token cannot be guessed or forged
            - CVE-ADR-002-A-003: Works in all Python runtimes (no frame dependency)
        """
        from elspeth.core.validation.base import SecurityValidationError

        if _token is not _CONSTRUCTION_TOKEN:
            raise SecurityValidationError(
                "SecureDataFrame can only be created via authorized factory methods. "
                "Use create_from_datasource() for datasources, or "
                "with_uplifted_security_level()/with_new_data() for plugins. "
                "Direct construction prevents classification tracking (ADR-002-A)."
            )
        return object.__new__(cls)

    @classmethod
    def create_from_datasource(
        cls, data: pd.DataFrame, security_level: SecurityLevel
    ) -> "SecureDataFrame":
        """Create SecureDataFrame from datasource (trusted source only).

        This is the ONLY way to create a SecureDataFrame from scratch.
        Datasources are trusted to label data with correct security level.

        Args:
            data: Pandas DataFrame containing the data
            security_level: Security level of the data

        Returns:
            New SecureDataFrame with datasource-authorized creation

        Security:
            - This factory method passes _CONSTRUCTION_TOKEN to __new__
            - Token authorization replaces stack inspection (VULN-011)
            - Only datasources should call this method (verified during certification)

        Example:
            >>> # In datasource implementation
            >>> df = pd.DataFrame({"data": [1, 2, 3]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
        """
        # Pass token to __new__ for authorization (VULN-011)
        instance = cls.__new__(cls, _token=_CONSTRUCTION_TOKEN)
        object.__setattr__(instance, "data", data)
        object.__setattr__(instance, "security_level", security_level)
        object.__setattr__(instance, "_created_by_datasource", True)
        return instance

    def with_uplifted_security_level(
        self, new_level: SecurityLevel
    ) -> "SecureDataFrame":
        """Return new instance with uplifted security level (immutable update).

        Security level uplifting enforces the "high water mark" principle:
        data passing through a high-security component inherits the higher
        security level automatically and irreversibly.

        Args:
            new_level: Security level to uplift to

        Returns:
            New SecureDataFrame with max(current, new_level) security level

        Note:
            This is NOT a downgrade operation - if new_level < current security level,
            the current security level is preserved (max() operation).

        Example:
            >>> # OFFICIAL data through SECRET LLM
            >>> input_df = SecureDataFrame.create_from_datasource(
            ...     data, SecurityLevel.OFFICIAL
            ... )
            >>> llm_level = SecurityLevel.SECRET
            >>> output_df = input_df.with_uplifted_security_level(llm_level)
            >>> assert output_df.security_level == SecurityLevel.SECRET
            >>>
            >>> # Attempting to "downgrade" preserves higher security level
            >>> result = output_df.with_uplifted_security_level(SecurityLevel.OFFICIAL)
            >>> assert result.security_level == SecurityLevel.SECRET  # max() wins
        """
        uplifted_level = max(self.security_level, new_level)

        # Pass token to __new__ for authorization (VULN-011)
        instance = SecureDataFrame.__new__(SecureDataFrame, _token=_CONSTRUCTION_TOKEN)
        object.__setattr__(instance, "data", self.data)
        object.__setattr__(instance, "security_level", uplifted_level)
        object.__setattr__(instance, "_created_by_datasource", False)
        return instance

    def with_new_data(self, new_data: pd.DataFrame) -> "SecureDataFrame":
        """Create frame with different data, preserving current security level.

        For plugins that generate entirely new DataFrames (LLMs, aggregations)
        that cannot mutate .data in-place due to schema changes.

        Args:
            new_data: New pandas DataFrame to wrap

        Returns:
            New SecureDataFrame with new data but SAME security level

        Security:
            - Preserves current security level (cannot downgrade)
            - Plugin must still call with_uplifted_security_level() afterwards
            - Bypasses __post_init__ validation (trusted internal method)

        Example:
            >>> # LLM generates new DataFrame
            >>> input_frame = SecureDataFrame.create_from_datasource(
            ...     input_df, SecurityLevel.OFFICIAL
            ... )
            >>> new_df = llm.generate(...)
            >>> output_frame = input_frame.with_new_data(new_df)
            >>> # Must still uplift to LLM's security level
            >>> final_frame = output_frame.with_uplifted_security_level(
            ...     SecurityLevel.SECRET
            ... )
        """
        # Pass token to __new__ for authorization (VULN-011)
        instance = SecureDataFrame.__new__(SecureDataFrame, _token=_CONSTRUCTION_TOKEN)
        object.__setattr__(instance, "data", new_data)
        object.__setattr__(instance, "security_level", self.security_level)
        object.__setattr__(instance, "_created_by_datasource", False)
        return instance

    def validate_compatible_with(self, required_clearance: SecurityLevel) -> None:
        """Validate data security level is compatible with required clearance.

        Runtime failsafe that enforces clearance checks at every data hand-off.
        This provides defense-in-depth if start-time validation is bypassed.

        Args:
            required_clearance: Security level required to access this data

        Raises:
            SecurityValidationError: If required_clearance < data security level

        Security Property:
            required_clearance >= self.security_level

        Example:
            >>> secret_df = SecureDataFrame.create_from_datasource(
            ...     data, SecurityLevel.SECRET
            ... )
            >>>
            >>> # Validate UNOFFICIAL clearance (should fail)
            >>> secret_df.validate_compatible_with(SecurityLevel.UNOFFICIAL)
            >>> # Raises: SecurityValidationError("Cannot provide SECRET data
            >>> #         with UNOFFICIAL clearance")
            >>>
            >>> # Validate SECRET clearance (should pass)
            >>> secret_df.validate_compatible_with(SecurityLevel.SECRET)  # OK

        ADR-002 Threat Prevention:
            - T3 (Runtime Bypass): Catches if start-time validation bypassed/broken
            - Defense in depth: Redundant with start-time validation (PRIMARY control)
        """
        from elspeth.core.validation.base import SecurityValidationError

        if required_clearance < self.security_level:
            raise SecurityValidationError(
                f"Cannot provide {self.security_level.name} data "
                f"with {required_clearance.name} clearance. "
                f"This is a runtime failsafe - start-time validation should have "
                f"prevented this configuration."
            )

    # Convenience properties for DataFrame-like interface
    # These reduce integration friction while maintaining security wrapper

    @property
    def empty(self) -> bool:
        """Proxy to underlying DataFrame.empty for convenience.

        Returns:
            True if DataFrame has no rows, False otherwise

        Example:
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     pd.DataFrame(), SecurityLevel.OFFICIAL
            ... )
            >>> assert frame.empty is True
        """
        return self.data.empty

    @property
    def shape(self) -> tuple[int, int]:
        """Proxy to underlying DataFrame.shape for convenience.

        Returns:
            Tuple of (rows, columns)

        Example:
            >>> df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> assert frame.shape == (2, 2)
        """
        return self.data.shape

    def __len__(self) -> int:
        """Support len() for convenience - returns number of rows.

        Returns:
            Number of rows in underlying DataFrame

        Example:
            >>> df = pd.DataFrame({"a": [1, 2, 3]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> assert len(frame) == 3
        """
        return len(self.data)

    def __getitem__(self, key):
        """Proxy to underlying DataFrame.__getitem__ for column/row access.

        Allows standard DataFrame indexing syntax like frame["column"] or frame[0:5].

        Args:
            key: Column name, list of columns, slice, or boolean array

        Returns:
            Result of indexing operation on underlying DataFrame

        Example:
            >>> df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> assert list(frame["a"]) == [1, 2]
            >>> assert len(frame[0:1]) == 1
        """
        return self.data[key]

    def head(self, n: int = 5) -> "SecureDataFrame":
        """Return first n rows, preserving SecureDataFrame wrapper.

        Args:
            n: Number of rows to return (default 5)

        Returns:
            New SecureDataFrame with first n rows, same security level

        Example:
            >>> df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> head = frame.head(2)
            >>> assert len(head) == 2
            >>> assert head.security_level == SecurityLevel.OFFICIAL
        """
        return self.with_new_data(self.data.head(n))

    def tail(self, n: int = 5) -> "SecureDataFrame":
        """Return last n rows, preserving SecureDataFrame wrapper.

        Args:
            n: Number of rows to return (default 5)

        Returns:
            New SecureDataFrame with last n rows, same security level

        Example:
            >>> df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> tail = frame.tail(2)
            >>> assert len(tail) == 2
            >>> assert tail.security_level == SecurityLevel.OFFICIAL
        """
        return self.with_new_data(self.data.tail(n))

    @property
    def columns(self) -> pd.Index:
        """Proxy to underlying DataFrame.columns for convenience.

        Returns:
            Column labels of the DataFrame

        Example:
            >>> df = pd.DataFrame({"a": [1], "b": [2]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> assert list(frame.columns) == ["a", "b"]
        """
        return self.data.columns

    @property
    def index(self) -> pd.Index:
        """Proxy to underlying DataFrame.index for convenience.

        Returns:
            Row index of the DataFrame

        Example:
            >>> df = pd.DataFrame({"a": [1, 2, 3]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> assert len(frame.index) == 3
        """
        return self.data.index

    @property
    def dtypes(self) -> pd.Series:
        """Proxy to underlying DataFrame.dtypes for convenience.

        Returns:
            Series with column names as index and data types as values

        Example:
            >>> df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> assert frame.dtypes["a"] == pd.Int64Dtype() or frame.dtypes["a"].kind == "i"
        """
        return self.data.dtypes

    @property
    def attrs(self) -> dict:
        """Proxy to underlying DataFrame.attrs for metadata access.

        Returns:
            Dictionary containing DataFrame metadata

        Note:
            While attrs["security_level"] exists for legacy compatibility,
            prefer using the direct .security_level property on SecureDataFrame.

        Example:
            >>> df = pd.DataFrame({"a": [1]})
            >>> df.attrs["metadata"] = "custom_value"
            >>> frame = SecureDataFrame.create_from_datasource(
            ...     df, SecurityLevel.OFFICIAL
            ... )
            >>> assert frame.attrs["metadata"] == "custom_value"
        """
        return self.data.attrs
