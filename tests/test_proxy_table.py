"""Tests for ProxyTable and SecureFrameProxy."""

import time
from uuid import uuid4

import pytest

from elspeth.core.security.proxy import SecureFrameProxy
from elspeth.core.security.proxy_table import ProxyEntry, ProxyTable


def test_proxy_entry_with_incremented_version():
    """Test creating entry with incremented version."""
    entry = ProxyEntry(
        proxy_id="abc123",
        frame_id=uuid4(),
        version=1,
        created_at=1000.0,
        last_accessed=1000.0,
    )

    new_entry = entry.with_incremented_version()

    assert new_entry.proxy_id == entry.proxy_id
    assert new_entry.frame_id == entry.frame_id
    assert new_entry.version == 2  # Incremented
    assert new_entry.created_at == entry.created_at
    assert new_entry.last_accessed > entry.last_accessed  # Updated


def test_proxy_entry_with_updated_access_time():
    """Test updating access time without changing version."""
    entry = ProxyEntry(
        proxy_id="abc123",
        frame_id=uuid4(),
        version=1,
        created_at=1000.0,
        last_accessed=1000.0,
    )

    time.sleep(0.01)  # Ensure time difference
    new_entry = entry.with_updated_access_time()

    assert new_entry.proxy_id == entry.proxy_id
    assert new_entry.frame_id == entry.frame_id
    assert new_entry.version == entry.version  # Same version
    assert new_entry.created_at == entry.created_at
    assert new_entry.last_accessed > entry.last_accessed  # Updated


def test_proxy_table_create_proxy():
    """Test creating new proxy."""
    table = ProxyTable()
    frame_id = uuid4()

    proxy_id = table.create_proxy(frame_id)

    assert len(proxy_id) == 32  # UUID4 hex is 32 chars
    assert table.contains(proxy_id)


def test_proxy_table_lookup():
    """Test looking up proxy by ID."""
    table = ProxyTable()
    frame_id = uuid4()

    proxy_id = table.create_proxy(frame_id)
    entry = table.lookup(proxy_id)

    assert entry.proxy_id == proxy_id
    assert entry.frame_id == frame_id
    assert entry.version == 1  # Initial version


def test_proxy_table_lookup_updates_access_time():
    """Test that lookup updates last_accessed timestamp."""
    table = ProxyTable()
    frame_id = uuid4()

    proxy_id = table.create_proxy(frame_id)
    entry1 = table.lookup(proxy_id)

    time.sleep(0.01)  # Ensure time difference
    entry2 = table.lookup(proxy_id)

    assert entry2.last_accessed > entry1.last_accessed


def test_proxy_table_lookup_unknown_proxy_fails():
    """Test that looking up unknown proxy raises KeyError."""
    table = ProxyTable()
    unknown_id = "nonexistent"

    with pytest.raises(KeyError, match="not found"):
        table.lookup(unknown_id)


def test_proxy_table_contains():
    """Test checking if proxy exists."""
    table = ProxyTable()
    frame_id = uuid4()

    proxy_id = table.create_proxy(frame_id)

    assert table.contains(proxy_id)
    assert not table.contains("nonexistent")


def test_proxy_table_increment_version():
    """Test incrementing proxy version."""
    table = ProxyTable()
    frame_id = uuid4()

    proxy_id = table.create_proxy(frame_id)
    entry1 = table.lookup(proxy_id)
    assert entry1.version == 1

    table.increment_version(proxy_id)
    entry2 = table.lookup(proxy_id)
    assert entry2.version == 2


def test_proxy_table_increment_version_unknown_proxy():
    """Test that incrementing version of unknown proxy fails."""
    table = ProxyTable()
    unknown_id = "nonexistent"

    with pytest.raises(KeyError, match="not found"):
        table.increment_version(unknown_id)


def test_proxy_table_update_frame_id():
    """Test updating frame_id after mutation."""
    table = ProxyTable()
    old_frame_id = uuid4()
    new_frame_id = uuid4()

    proxy_id = table.create_proxy(old_frame_id)
    entry1 = table.lookup(proxy_id)
    assert entry1.frame_id == old_frame_id
    assert entry1.version == 1

    # Update to new frame
    updated_entry = table.update_frame_id(proxy_id, new_frame_id)
    assert updated_entry.frame_id == new_frame_id
    assert updated_entry.version == 2  # Version incremented

    # Verify lookup returns updated entry
    entry2 = table.lookup(proxy_id)
    assert entry2.frame_id == new_frame_id
    assert entry2.version == 2


def test_proxy_table_update_frame_id_unknown_proxy():
    """Test that updating frame_id of unknown proxy fails."""
    table = ProxyTable()
    unknown_id = "nonexistent"
    new_frame_id = uuid4()

    with pytest.raises(KeyError, match="not found"):
        table.update_frame_id(unknown_id, new_frame_id)


def test_proxy_table_revoke():
    """Test revoking proxy."""
    table = ProxyTable()
    frame_id = uuid4()

    proxy_id = table.create_proxy(frame_id)
    assert table.contains(proxy_id)

    # Revoke proxy
    table.revoke(proxy_id)
    assert not table.contains(proxy_id)

    # Lookup should fail
    with pytest.raises(KeyError, match="revoked"):
        table.lookup(proxy_id)


def test_proxy_table_revoke_unknown_proxy():
    """Test that revoking unknown proxy fails."""
    table = ProxyTable()
    unknown_id = "nonexistent"

    with pytest.raises(KeyError, match="not found"):
        table.revoke(unknown_id)


def test_proxy_table_revoked_proxy_cannot_be_used():
    """Test that revoked proxy cannot be used for operations."""
    table = ProxyTable()
    frame_id = uuid4()

    proxy_id = table.create_proxy(frame_id)
    table.revoke(proxy_id)

    # All operations should fail on revoked proxy
    with pytest.raises(KeyError, match="revoked"):
        table.lookup(proxy_id)

    with pytest.raises(KeyError, match="revoked"):
        table.increment_version(proxy_id)

    with pytest.raises(KeyError, match="revoked"):
        table.update_frame_id(proxy_id, uuid4())


def test_proxy_table_active_count():
    """Test counting active proxies."""
    table = ProxyTable()

    assert table.active_count() == 0

    # Create 3 proxies
    proxy_ids = []
    for _ in range(3):
        proxy_ids.append(table.create_proxy(uuid4()))

    assert table.active_count() == 3

    # Revoke 1 proxy
    table.revoke(proxy_ids[0])
    assert table.active_count() == 2


def test_proxy_table_cleanup_stale():
    """Test cleaning up stale proxies."""
    table = ProxyTable()

    # Create 3 proxies
    proxy_ids = []
    for _ in range(3):
        proxy_ids.append(table.create_proxy(uuid4()))

    # Wait a bit
    time.sleep(0.1)

    # Cleanup proxies older than 0.05 seconds (all 3 should be stale)
    removed_count = table.cleanup_stale(max_age_seconds=0.05)

    assert removed_count == 3
    assert table.active_count() == 0

    # Revoked proxies cannot be used
    for proxy_id in proxy_ids:
        with pytest.raises(KeyError):
            table.lookup(proxy_id)


def test_proxy_table_cleanup_preserves_recently_accessed():
    """Test that cleanup preserves recently accessed proxies."""
    table = ProxyTable()

    # Create 2 proxies
    old_proxy_id = table.create_proxy(uuid4())
    time.sleep(0.05)
    new_proxy_id = table.create_proxy(uuid4())

    # Cleanup proxies older than 0.03 seconds (only old_proxy should be stale)
    removed_count = table.cleanup_stale(max_age_seconds=0.03)

    assert removed_count == 1
    assert not table.contains(old_proxy_id)
    assert table.contains(new_proxy_id)


def test_proxy_table_list_proxy_ids():
    """Test listing all proxy IDs."""
    table = ProxyTable()

    assert table.list_proxy_ids() == []

    # Create 3 proxies
    proxy_ids = set()
    for _ in range(3):
        proxy_ids.add(table.create_proxy(uuid4()))

    listed_ids = table.list_proxy_ids()
    assert len(listed_ids) == 3
    assert set(listed_ids) == proxy_ids


def test_secure_frame_proxy_initialization():
    """Test SecureFrameProxy initialization."""
    proxy = SecureFrameProxy(proxy_id="abc123", rpc_client=None)

    assert proxy.proxy_id == "abc123"
    assert repr(proxy) == "SecureFrameProxy(proxy_id='abc123')"


def test_secure_frame_proxy_get_view_without_rpc():
    """Test that get_view raises NotImplementedError without RPC client."""
    proxy = SecureFrameProxy(proxy_id="abc123", rpc_client=None)

    with pytest.raises(NotImplementedError, match="RPC client not configured"):
        proxy.get_view()


def test_secure_frame_proxy_replace_data_without_rpc():
    """Test that replace_data raises NotImplementedError without RPC client."""
    import pandas as pd

    proxy = SecureFrameProxy(proxy_id="abc123", rpc_client=None)
    df = pd.DataFrame({"a": [1, 2, 3]})

    with pytest.raises(NotImplementedError, match="RPC client not configured"):
        proxy.replace_data(df, version=1)


def test_secure_frame_proxy_with_uplifted_security_level_without_rpc():
    """Test that with_uplifted_security_level raises NotImplementedError without RPC client."""
    from elspeth.core.base.types import SecurityLevel

    proxy = SecureFrameProxy(proxy_id="abc123", rpc_client=None)

    with pytest.raises(NotImplementedError, match="RPC client not configured"):
        proxy.with_uplifted_security_level(SecurityLevel.OFFICIAL)


def test_secure_frame_proxy_with_new_data_without_rpc():
    """Test that with_new_data raises NotImplementedError without RPC client."""
    import pandas as pd

    proxy = SecureFrameProxy(proxy_id="abc123", rpc_client=None)
    df = pd.DataFrame({"a": [1, 2, 3]})

    with pytest.raises(NotImplementedError, match="RPC client not configured"):
        proxy.with_new_data(df)


def test_secure_frame_proxy_get_metadata_without_rpc():
    """Test that get_metadata raises NotImplementedError without RPC client."""
    proxy = SecureFrameProxy(proxy_id="abc123", rpc_client=None)

    with pytest.raises(NotImplementedError, match="RPC client not configured"):
        proxy.get_metadata()
