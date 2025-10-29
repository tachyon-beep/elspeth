"""Content-based digest computation for tamper detection.

Replaces memory-address-based sealing (CVE-ADR-002-A-009) with content-based
BLAKE3 digests computed over canonical Parquet serialization.

Security Properties:
- Content-based: Digest changes when data changes
- Canonical: Deterministic serialization ensures consistent digests
- Collision-resistant: BLAKE3 provides 128-bit security
- Fast: ~1GB/s throughput on typical hardware

Architecture:
- DataFrame → Canonical Parquet → BLAKE3 digest
- Parquet provides deterministic schema + data encoding
- BLAKE3 provides cryptographic collision resistance

This replaces the vulnerable id(data) approach which was based on
memory addresses that could be manipulated.
"""

import io
from typing import TYPE_CHECKING

import pandas as pd

try:
    import blake3
except ImportError as e:
    raise ImportError(
        "blake3 is required for content-based digest computation. "
        "Install with: pip install blake3"
    ) from e

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as e:
    raise ImportError(
        "pyarrow is required for canonical Parquet serialization. "
        "Install with: pip install pyarrow"
    ) from e


def compute_dataframe_digest(data: pd.DataFrame) -> bytes:
    """Compute BLAKE3 digest of DataFrame using canonical Parquet encoding.

    Serializes DataFrame to Parquet (deterministic schema + data) then
    computes BLAKE3 hash of the bytes. This provides content-based
    tamper detection that's independent of memory layout.

    Args:
        data: DataFrame to digest

    Returns:
        32-byte BLAKE3 digest

    Security Properties:
        - Content-based: Digest changes when data/schema changes
        - Deterministic: Same data always produces same digest
        - Collision-resistant: BLAKE3 provides 128-bit security
        - Fast: Parquet compression disabled for speed

    Performance:
        - ~10ms for 10k rows on typical hardware
        - Parquet serialization dominates (90% of time)
        - BLAKE3 hashing is ~1GB/s

    Example:
        >>> df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        >>> digest1 = compute_dataframe_digest(df)
        >>> digest2 = compute_dataframe_digest(df)
        >>> digest1 == digest2  # Deterministic
        True
        >>> df.iloc[0, 0] = 999
        >>> digest3 = compute_dataframe_digest(df)
        >>> digest1 == digest3  # Content changed
        False

    Raises:
        ValueError: If DataFrame cannot be serialized to Parquet
    """
    try:
        # Convert DataFrame to Arrow Table
        table = pa.Table.from_pandas(data, preserve_index=True)

        # Serialize to Parquet with canonical settings
        buffer = io.BytesIO()
        pq.write_table(
            table,
            buffer,
            compression=None,  # No compression for speed + determinism
            use_dictionary=False,  # Disable dictionary encoding for determinism
            write_statistics=False,  # No statistics (non-deterministic metadata)
            store_schema=True,  # Include schema for schema change detection
        )

        # Get Parquet bytes
        parquet_bytes = buffer.getvalue()

        # Compute BLAKE3 digest
        hasher = blake3.blake3()
        hasher.update(parquet_bytes)
        digest = hasher.digest()

        return digest

    except Exception as e:
        raise ValueError(
            f"Failed to compute digest for DataFrame: {e}. "
            "Ensure DataFrame contains Parquet-compatible types."
        ) from e


def compute_digest_for_frame(
    data: pd.DataFrame, frame_id: bytes, level: int
) -> bytes:
    """Compute digest binding DataFrame content, frame_id, and security level.

    Combines DataFrame digest with frame_id and security level to create
    a unique digest for this specific frame instance.

    Args:
        data: DataFrame to digest
        frame_id: 16-byte frame UUID
        level: Security level (0-4)

    Returns:
        32-byte BLAKE3 digest binding data + frame_id + level

    Security:
        - Binds digest to specific frame instance (prevents digest reuse)
        - Includes security level (detects relabeling)
        - Content-based (detects data tampering)
    """
    # Compute base data digest
    data_digest = compute_dataframe_digest(data)

    # Combine with frame_id and level
    hasher = blake3.blake3()
    hasher.update(data_digest)
    hasher.update(frame_id)
    hasher.update(level.to_bytes(4, byteorder="big"))

    return hasher.digest()


def verify_digest(data: pd.DataFrame, expected_digest: bytes) -> bool:
    """Verify DataFrame digest matches expected value.

    Args:
        data: DataFrame to verify
        expected_digest: Expected 32-byte BLAKE3 digest

    Returns:
        True if digest matches, False otherwise

    Note:
        Uses constant-time comparison to prevent timing attacks.
    """
    import hmac

    actual_digest = compute_dataframe_digest(data)
    return hmac.compare_digest(actual_digest, expected_digest)
