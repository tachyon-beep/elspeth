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

from dataclasses import dataclass
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

    Security Model:
        - Classification is immutable (frozen dataclass)
        - Uplifting creates new instance (original unchanged)
        - Downgrading is impossible (max() operation prevents it)
        - Access validation provides runtime failsafe

    Example:
        >>> df = ClassifiedDataFrame(data, SecurityLevel.OFFICIAL)
        >>> df.classification = SecurityLevel.UNOFFICIAL  # AttributeError (frozen)
        >>>
        >>> # Uplifting to SECRET (data passed through SECRET LLM)
        >>> secret_df = df.with_uplifted_classification(SecurityLevel.SECRET)
        >>> assert secret_df.classification == SecurityLevel.SECRET
        >>> assert df.classification == SecurityLevel.OFFICIAL  # Original unchanged
        >>>
        >>> # Attempting to downgrade (creates SECRET, not OFFICIAL)
        >>> result = secret_df.with_uplifted_classification(SecurityLevel.OFFICIAL)
        >>> assert result.classification == SecurityLevel.SECRET  # max() prevents downgrade

    ADR-002 Threat Prevention:
        - T4 (Classification Mislabeling): Automatic uplifting prevents forgotten manual tagging
        - T3 (Runtime Bypass): validate_access_by() catches start-time validation bypass
    """

    data: pd.DataFrame
    classification: SecurityLevel

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
            >>> input_df = ClassifiedDataFrame(data, SecurityLevel.OFFICIAL)
            >>> llm_level = SecurityLevel.SECRET
            >>> output_df = input_df.with_uplifted_classification(llm_level)
            >>> assert output_df.classification == SecurityLevel.SECRET
            >>>
            >>> # Attempting to "downgrade" preserves higher classification
            >>> result = output_df.with_uplifted_classification(SecurityLevel.OFFICIAL)
            >>> assert result.classification == SecurityLevel.SECRET  # max() wins
        """
        uplifted_classification = max(self.classification, new_level)

        return ClassifiedDataFrame(
            data=self.data,  # Share DataFrame (immutability at classification level)
            classification=uplifted_classification,
        )

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
            >>> secret_df = ClassifiedDataFrame(data, SecurityLevel.SECRET)
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
