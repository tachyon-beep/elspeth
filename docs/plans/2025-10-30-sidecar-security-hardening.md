# Sidecar Security Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden sidecar daemon against DoS attacks (request size limits) and verify file descriptor isolation (FD_CLOEXEC).

**Architecture:** Add configurable request size limit with bounded reading to prevent memory exhaustion DoS. Verify Unix socket file descriptors have FD_CLOEXEC set to prevent inheritance by spawned processes.

**Tech Stack:** Rust (tokio async runtime, Unix sockets, nix crate for FD_CLOEXEC)

**Security Impact:** Prevents attackers from exhausting daemon memory with oversized CBOR payloads. Ensures sidecar socket descriptors are not leaked to child processes.

---

## Task 1: Add Request Size Limit Configuration

**Files:**
- Modify: `sidecar/src/config.rs:26` (add max_request_size_bytes field)
- Modify: `sidecar/Cargo.toml` (verify dependencies)
- Test: Manual config file validation

### Step 1: Add max_request_size_bytes field to Config struct

**File:** `sidecar/src/config.rs`

Add field after `grant_ttl_secs`:

```rust
    /// Grant TTL in seconds
    pub grant_ttl_secs: u64,

    /// Maximum request size in bytes (DoS protection)
    /// Default: 1 MiB (sufficient for largest valid CBOR request)
    #[serde(default = "default_max_request_size")]
    pub max_request_size_bytes: usize,

    /// Log level (trace, debug, info, warn, error)
    pub log_level: String,
```

Add default function at end of file (before closing brace):

```rust
/// Default max request size (1 MiB).
///
/// Rationale:
/// - Largest valid request: authorize_construct with 32-byte digest (~200 bytes CBOR)
/// - 1 MiB provides 5000x headroom for future protocol extensions
/// - Prevents multi-gigabyte DoS attacks
fn default_max_request_size() -> usize {
    1024 * 1024 // 1 MiB
}
```

### Step 2: Add accessor method

**File:** `sidecar/src/config.rs`

Add after `grant_ttl()` method:

```rust
    /// Grant TTL as Duration.
    pub fn grant_ttl(&self) -> Duration {
        Duration::from_secs(self.grant_ttl_secs)
    }

    /// Maximum request size in bytes.
    pub fn max_request_size(&self) -> usize {
        self.max_request_size_bytes
    }
}
```

### Step 3: Verify Config compiles

**Run:**
```bash
cd /home/john/elspeth/sidecar
cargo check --all-targets
```

**Expected:** Compiles successfully with no errors.

### Step 4: Commit configuration changes

**Run:**
```bash
git add sidecar/src/config.rs
git commit -m "Security: Add max_request_size_bytes config for DoS protection

Adds configurable request size limit (default 1 MiB) to prevent
memory exhaustion attacks from oversized CBOR payloads.

Rationale:
- Largest valid request ~200 bytes (authorize_construct)
- 1 MiB provides 5000x headroom
- Prevents multi-GB DoS attacks

Related: Security review recommendation #4
"
```

---

## Task 2: Implement Bounded Request Reading

**Files:**
- Modify: `sidecar/src/server.rs:125-129` (replace read_to_end with bounded read)
- Test: `sidecar/tests/handlers_test.rs` (add oversized request test)

### Step 1: Write failing test for oversized request rejection

**File:** `sidecar/tests/handlers_test.rs`

Add test at end of file (before closing brace):

```rust
#[tokio::test]
async fn test_oversized_request_rejected() {
    use std::os::unix::net::UnixStream as StdUnixStream;
    use std::io::Write;
    use tempfile::tempdir;

    // Create config with 1 KiB limit
    let dir = tempdir().unwrap();
    let socket_path = dir.path().join("test.sock");
    let session_key_path = dir.path().join("session.key");

    let config_content = format!(
        r#"
mode = "standalone"
socket_path = "{}"
session_key_path = "{}"
appuser_uid = {}
grant_ttl_secs = 30
max_request_size_bytes = 1024
log_level = "debug"
"#,
        socket_path.display(),
        session_key_path.display(),
        unsafe { libc::getuid() }
    );

    let config_path = dir.path().join("config.toml");
    std::fs::write(&config_path, config_content).unwrap();

    let config = elspeth_sidecar::config::Config::load(config_path.to_str().unwrap()).unwrap();
    let server = elspeth_sidecar::server::Server::new(config.clone()).unwrap();

    // Start server in background
    let socket_path_clone = socket_path.clone();
    tokio::spawn(async move {
        server.run().await.ok();
    });

    // Wait for server to start
    tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

    // Send 2 KiB request (exceeds 1 KiB limit)
    let oversized_payload = vec![0x42; 2048]; // 2 KiB of 0x42 bytes

    let mut stream = StdUnixStream::connect(&socket_path).unwrap();
    stream.write_all(&oversized_payload).unwrap();
    stream.shutdown(std::net::Shutdown::Write).unwrap();

    // Read response (should be error)
    let mut response = Vec::new();
    std::io::Read::read_to_end(&mut stream, &mut response).unwrap();

    // Should receive error response (not crash/hang)
    assert!(!response.is_empty(), "Should receive error response, not hang");

    // Parse CBOR response
    let resp: elspeth_sidecar::protocol::Response = serde_cbor::from_slice(&response).unwrap();

    // Should be Error variant
    match resp {
        elspeth_sidecar::protocol::Response::Error { error, reason } => {
            assert!(reason.contains("exceeds maximum") || reason.contains("too large"),
                    "Error should mention size limit, got: {}", reason);
        }
        _ => panic!("Expected Error response, got: {:?}", resp),
    }
}
```

### Step 2: Run test to verify it fails

**Run:**
```bash
cd /home/john/elspeth/sidecar
cargo test test_oversized_request_rejected -- --nocapture
```

**Expected:** Test fails (timeout or panic) because unbounded `read_to_end()` tries to read all 2 KiB.

### Step 3: Implement bounded reading in handle_client

**File:** `sidecar/src/server.rs`

Replace lines 125-132 with bounded reading logic:

```rust
        debug!("Client connected (UID {} verified)", peer_uid);

        // Read CBOR request with size limit (DoS protection)
        let max_size = self.config.max_request_size();
        let mut buffer = Vec::with_capacity(4096.min(max_size)); // Start with 4 KiB or max_size
        let mut total_read = 0;

        loop {
            let mut chunk = vec![0u8; 4096];
            match stream.read(&mut chunk).await {
                Ok(0) => break, // EOF
                Ok(n) => {
                    total_read += n;

                    // Enforce size limit
                    if total_read > max_size {
                        error!(
                            "Request size {} bytes exceeds maximum {} bytes",
                            total_read, max_size
                        );
                        let error_response = Response::Error {
                            error: "Request too large".to_string(),
                            reason: format!(
                                "Request size {} bytes exceeds maximum {} bytes (DoS protection)",
                                total_read, max_size
                            ),
                        };
                        let response_bytes = serde_cbor::to_vec(&error_response)?;
                        stream.write_all(&response_bytes).await?;
                        anyhow::bail!("Request exceeds size limit");
                    }

                    buffer.extend_from_slice(&chunk[..n]);
                }
                Err(e) => return Err(e.into()),
            }
        }

        if buffer.is_empty() {
            return Ok(()); // EOF without data
        }
```

**Note:** Change `use tokio::io::{AsyncReadExt, AsyncWriteExt};` to enable `read()` method.

### Step 4: Update imports if needed

**File:** `sidecar/src/server.rs` (line 13)

Verify import includes `AsyncReadExt`:

```rust
use tokio::io::{AsyncReadExt, AsyncWriteExt};
```

(Already present, no change needed.)

### Step 5: Run test to verify it passes

**Run:**
```bash
cd /home/john/elspeth/sidecar
cargo test test_oversized_request_rejected -- --nocapture
```

**Expected:** Test passes - daemon rejects oversized request with error response.

### Step 6: Run all existing tests to ensure no regressions

**Run:**
```bash
cd /home/john/elspeth/sidecar
cargo test
```

**Expected:** All tests pass (no behavioral changes to valid requests).

### Step 7: Commit bounded reading implementation

**Run:**
```bash
git add sidecar/src/server.rs sidecar/tests/handlers_test.rs
git commit -m "Security: Implement bounded request reading with size limits

Replaces unbounded read_to_end() with chunked reading that enforces
max_request_size_bytes limit. Prevents memory exhaustion DoS attacks.

Changes:
- Read in 4 KiB chunks with running total
- Reject requests exceeding max_size with error response
- Add test for oversized request rejection (2 KiB > 1 KiB limit)

Security impact: Attacker can no longer exhaust daemon memory with
multi-gigabyte CBOR payloads.

Related: Security review recommendation #4
"
```

---

## Task 3: Verify FD_CLOEXEC on Unix Socket

**Files:**
- Modify: `sidecar/Cargo.toml` (add nix dependency if needed)
- Create: `sidecar/tests/fd_cloexec_test.rs` (test to verify FD_CLOEXEC)
- Modify: `sidecar/src/server.rs` (add FD_CLOEXEC if not set by tokio)

### Step 1: Research tokio's FD_CLOEXEC behavior

**Background:** Tokio's `UnixListener::bind()` uses `socket2` crate which sets `SOCK_CLOEXEC` by default on Linux (via `socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0)`).

**Verification needed:** Write test to confirm FD_CLOEXEC is actually set.

### Step 2: Add nix dependency for FD_CLOEXEC checking

**File:** `sidecar/Cargo.toml`

Check if `nix` is already present. If not, add under `[dev-dependencies]`:

```toml
[dev-dependencies]
nix = { version = "0.29", features = ["fs"] }
tempfile = "3.8"
```

**Run:**
```bash
cd /home/john/elspeth/sidecar
cargo check --tests
```

**Expected:** Dependency resolves successfully.

### Step 3: Write test to verify FD_CLOEXEC

**File:** `sidecar/tests/fd_cloexec_test.rs` (create new file)

```rust
//! Test to verify Unix socket has FD_CLOEXEC flag set.
//!
//! This prevents file descriptors from being inherited by child processes,
//! which could allow plugins to access the sidecar socket.

use nix::fcntl::{fcntl, FcntlArg, FdFlag};
use std::os::unix::io::AsRawFd;
use tempfile::tempdir;
use tokio::net::UnixListener;

#[tokio::test]
async fn test_unix_socket_has_fd_cloexec() {
    let dir = tempdir().unwrap();
    let socket_path = dir.path().join("test_cloexec.sock");

    // Bind Unix socket (same as server.rs does)
    let listener = UnixListener::bind(&socket_path).expect("Failed to bind socket");

    // Get raw file descriptor
    let fd = listener.as_raw_fd();

    // Query FD flags
    let flags = fcntl(fd, FcntlArg::F_GETFD).expect("Failed to get FD flags");
    let fd_flags = FdFlag::from_bits(flags).expect("Invalid FD flags");

    // Verify FD_CLOEXEC is set
    assert!(
        fd_flags.contains(FdFlag::FD_CLOEXEC),
        "Unix socket should have FD_CLOEXEC flag set to prevent inheritance by child processes"
    );

    println!("✓ FD_CLOEXEC is set on Unix socket (flags: {:?})", fd_flags);
}

#[tokio::test]
async fn test_accepted_connection_has_fd_cloexec() {
    use std::os::unix::net::UnixStream as StdUnixStream;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let dir = tempdir().unwrap();
    let socket_path = dir.path().join("test_accept_cloexec.sock");

    // Bind listener
    let listener = UnixListener::bind(&socket_path).expect("Failed to bind socket");

    // Connect in background
    let socket_path_clone = socket_path.clone();
    let client_handle = tokio::spawn(async move {
        tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;
        StdUnixStream::connect(socket_path_clone).expect("Failed to connect");
    });

    // Accept connection
    let (stream, _) = listener.accept().await.expect("Failed to accept connection");

    // Verify accepted stream has FD_CLOEXEC
    let fd = stream.as_raw_fd();
    let flags = fcntl(fd, FcntlArg::F_GETFD).expect("Failed to get FD flags");
    let fd_flags = FdFlag::from_bits(flags).expect("Invalid FD flags");

    assert!(
        fd_flags.contains(FdFlag::FD_CLOEXEC),
        "Accepted connection should have FD_CLOEXEC flag set"
    );

    println!("✓ FD_CLOEXEC is set on accepted connection (flags: {:?})", fd_flags);

    client_handle.await.unwrap();
}
```

### Step 4: Run test to verify FD_CLOEXEC is set by tokio

**Run:**
```bash
cd /home/john/elspeth/sidecar
cargo test test_unix_socket_has_fd_cloexec -- --nocapture
cargo test test_accepted_connection_has_fd_cloexec -- --nocapture
```

**Expected:** Tests pass, confirming tokio sets FD_CLOEXEC automatically.

**If tests fail:** Proceed to Step 5 to manually set FD_CLOEXEC.

**If tests pass:** Skip to Step 6 (document finding).

### Step 5: Manually set FD_CLOEXEC if tokio doesn't (conditional)

**Only if Step 4 tests fail.**

**File:** `sidecar/src/server.rs`

Add after `UnixListener::bind()` (line 63):

```rust
        // Bind Unix socket
        let listener =
            UnixListener::bind(&self.config.socket_path).context("Failed to bind Unix socket")?;

        // SECURITY: Ensure FD_CLOEXEC is set (prevent inheritance by child processes)
        // This prevents plugin workers from inheriting the sidecar socket FD
        use nix::fcntl::{fcntl, FcntlArg, FdFlag};
        use std::os::unix::io::AsRawFd;

        let fd = listener.as_raw_fd();
        let mut flags = FdFlag::from_bits(fcntl(fd, FcntlArg::F_GETFD)?)
            .context("Invalid FD flags")?;
        flags.insert(FdFlag::FD_CLOEXEC);
        fcntl(fd, FcntlArg::F_SETFD(flags)).context("Failed to set FD_CLOEXEC")?;

        debug!("FD_CLOEXEC set on Unix socket (fd {})", fd);
```

Add `nix` to `[dependencies]` in `Cargo.toml`:

```toml
[dependencies]
nix = { version = "0.29", features = ["fs"] }
```

### Step 6: Document FD_CLOEXEC verification in SECURITY.md

**File:** `sidecar/SECURITY.md`

Add subsection under "Unix Socket Security" (after line 37):

```markdown
### 2. Unix Socket Security

**Socket Path:** `/run/sidecar/auth.sock`
**Permissions:** `0600` (owner-only read/write)
**Authentication:** `SO_PEERCRED` validation + HMAC-SHA256

**File Descriptor Isolation (FD_CLOEXEC):**
- Unix socket file descriptor has `FD_CLOEXEC` flag set
- Prevents inheritance by child processes (plugin workers)
- Verified by `tests/fd_cloexec_test.rs`
- tokio's `UnixListener` sets `SOCK_CLOEXEC` by default (Linux kernel ≥2.6.27)

**Defense in Depth:**
```

### Step 7: Run full test suite

**Run:**
```bash
cd /home/john/elspeth/sidecar
cargo test
cargo clippy -- -D warnings
cargo fmt --check
```

**Expected:** All tests pass, clippy clean, formatting clean.

### Step 8: Commit FD_CLOEXEC verification

**Run:**
```bash
git add sidecar/tests/fd_cloexec_test.rs sidecar/SECURITY.md sidecar/Cargo.toml
git commit -m "Security: Verify FD_CLOEXEC on Unix socket descriptors

Adds tests confirming Unix socket file descriptors have FD_CLOEXEC
flag set, preventing inheritance by child processes (plugin workers).

Verification:
- tokio's UnixListener sets SOCK_CLOEXEC by default (Linux)
- Accepted connections inherit FD_CLOEXEC
- Tests confirm expected behavior

Security impact: Plugin workers cannot inherit sidecar socket FD,
preventing bypass of UID/socket permission checks.

Related: Security review recommendation #5
"
```

---

## Task 4: Update Documentation and Integration Tests

**Files:**
- Modify: `sidecar/SECURITY.md` (add DoS protection section)
- Modify: `tests/test_sidecar_integration.py` (add Python integration test for size limits)

### Step 1: Add DoS protection section to SECURITY.md

**File:** `sidecar/SECURITY.md`

Add new section after "Threat Mitigations" (before "Vulnerability Disclosure"):

```markdown
---

## DoS Protection

### Request Size Limits

**Maximum Request Size:** 1 MiB (default, configurable via `max_request_size_bytes`)

**Rationale:**
- Largest valid CBOR request: ~200 bytes (`authorize_construct` with 32-byte digest)
- 1 MiB provides 5000× safety margin for future protocol extensions
- Prevents memory exhaustion attacks from multi-gigabyte payloads

**Implementation:**
- Daemon reads requests in 4 KiB chunks
- Rejects requests exceeding `max_request_size_bytes` with error response
- Client connection closed after error (no partial processing)

**Attack Mitigation:**
- Attacker sends 10 GB CBOR payload → Daemon rejects at 1 MiB, responds with error
- Memory usage bounded to configured limit + small overhead
- No daemon crash or service degradation

**Configuration:**

```toml
# sidecar.toml
max_request_size_bytes = 1048576  # 1 MiB (default)
```

**Monitoring:**
- Large request rejections logged at `ERROR` level
- Metric: `requests_served` excludes rejected oversized requests
```

### Step 2: Add Python integration test for size limits

**File:** `tests/test_sidecar_integration.py`

Add test after existing integration tests:

```python
def test_oversized_request_rejected(sidecar_client):
    """Test that oversized requests are rejected to prevent DoS."""
    import cbor2

    # Create oversized CBOR payload (2 MiB)
    oversized_request = {
        "op": "health_check",
        "padding": b"\x00" * (2 * 1024 * 1024),  # 2 MiB of null bytes
    }

    oversized_bytes = cbor2.dumps(oversized_request)

    # Attempt to send oversized request
    try:
        # Manually send request (bypass sidecar_client methods)
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(str(sidecar_client.config.socket_path))

        sock.sendall(oversized_bytes)
        sock.shutdown(socket.SHUT_WR)

        # Read response
        response_chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_chunks.append(chunk)

        response_bytes = b"".join(response_chunks)
        response = cbor2.loads(response_bytes)

        # Should receive error response
        assert "error" in response, f"Expected error response, got: {response}"
        assert "too large" in response.get("reason", "").lower() or \
               "exceeds" in response.get("reason", "").lower(), \
               f"Error should mention size limit: {response}"

        sock.close()

    except Exception as e:
        pytest.fail(f"Oversized request handling failed: {e}")
```

### Step 3: Run Python integration tests

**Run:**
```bash
cd /home/john/elspeth
source .venv/bin/activate
ELSPETH_RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_sidecar_integration.py::test_oversized_request_rejected -v
```

**Expected:** Test passes - daemon rejects oversized request with error.

### Step 4: Run full integration test suite

**Run:**
```bash
cd /home/john/elspeth
ELSPETH_RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_sidecar_integration.py -v
```

**Expected:** All integration tests pass (no regressions).

### Step 5: Commit documentation and integration tests

**Run:**
```bash
git add sidecar/SECURITY.md tests/test_sidecar_integration.py
git commit -m "docs: Document DoS protection and add integration tests

Adds SECURITY.md section documenting request size limits and DoS
protection mechanisms. Includes Python integration test verifying
oversized request rejection.

Documentation:
- Request size limit rationale (1 MiB default)
- Attack mitigation scenario
- Configuration guidance

Testing:
- Python integration test sends 2 MiB request
- Verifies daemon rejects with error response
- No daemon crash or hang

Related: Security review recommendations #4, #5
"
```

---

## Task 5: Final Verification and PR Preparation

**Files:**
- Create: `docs/architecture/decisions/002-d-sidecar-dos-protection.md` (optional ADR)
- Modify: `sidecar/SECURITY.md` (update "Last Updated" date)

### Step 1: Run complete test suite (Rust + Python)

**Run:**
```bash
# Rust tests
cd /home/john/elspeth/sidecar
cargo test
cargo clippy -- -D warnings
cargo fmt --check

# Python tests
cd /home/john/elspeth
source .venv/bin/activate
ELSPETH_RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_sidecar_integration.py -v
python -m mypy src/elspeth/core/security/sidecar_client.py
```

**Expected:** All tests pass, no linter warnings.

### Step 2: Update SECURITY.md last updated date

**File:** `sidecar/SECURITY.md` (line 219)

```markdown
---

**Last Updated:** 2025-10-30
**Maintainer:** ELSPETH Security Team
**Security Contact:** See `SECURITY.md` in repository root
```

### Step 3: Create summary of security improvements

**File:** `docs/architecture/decisions/002-d-sidecar-dos-protection.md` (optional)

```markdown
# ADR-002-D: Sidecar DoS Protection

**Status:** Accepted
**Date:** 2025-10-30
**Related:** ADR-002 (MLS Architecture), ADR-002-C (Authentication Architecture)

## Context

Security review identified two high-priority hardening opportunities:
1. Unbounded request reading vulnerable to memory exhaustion DoS
2. File descriptor isolation (FD_CLOEXEC) needed verification

## Decision

### Request Size Limits

**Implementation:** Replace `read_to_end()` with bounded chunked reading.

**Configuration:** `max_request_size_bytes = 1048576` (1 MiB default)

**Rationale:**
- Largest valid request: ~200 bytes (authorize_construct)
- 1 MiB provides 5000× safety margin
- Prevents multi-GB DoS attacks

**Security Benefit:** Attacker cannot exhaust daemon memory with oversized CBOR payloads.

### File Descriptor Isolation

**Verification:** tokio's `UnixListener::bind()` sets `SOCK_CLOEXEC` by default on Linux.

**Testing:** Added `tests/fd_cloexec_test.rs` to verify FD_CLOEXEC is set.

**Security Benefit:** Plugin workers cannot inherit sidecar socket FD, preventing bypass of UID/permission checks.

## Consequences

**Positive:**
- Daemon resilient to memory exhaustion DoS
- File descriptor isolation verified and documented
- Defense-in-depth: multiple layers prevent plugin socket access

**Negative:**
- Legitimate requests exceeding 1 MiB would be rejected (unlikely - largest valid ~200 bytes)

## Testing

- Rust unit tests: `test_oversized_request_rejected`, `test_unix_socket_has_fd_cloexec`
- Python integration tests: `test_oversized_request_rejected`
- All existing tests pass (no behavioral regressions)

## Compliance

- ISM-0380: Access control enforcement (FD_CLOEXEC prevents descriptor leakage)
- ISM-1552: DoS resilience (request size limits)
```

### Step 4: Commit ADR (if created)

**Run:**
```bash
git add docs/architecture/decisions/002-d-sidecar-dos-protection.md sidecar/SECURITY.md
git commit -m "docs(ADR): Add ADR-002-D documenting DoS protection

Documents request size limits and FD_CLOEXEC verification.

Security improvements:
- Bounded request reading (1 MiB default limit)
- FD_CLOEXEC verification for file descriptor isolation
- Defense-in-depth against plugin socket access

Related: Security review recommendations #4, #5
"
```

### Step 5: Create PR summary

**Summary for PR description:**

```markdown
## Security Hardening: DoS Protection and FD Isolation

Completes security review recommendations #4 and #5.

### Changes

1. **Request Size Limits** (DoS Protection)
   - Added `max_request_size_bytes` config (default 1 MiB)
   - Replaced unbounded `read_to_end()` with chunked reading
   - Rejects oversized requests with error response
   - Prevents memory exhaustion attacks

2. **FD_CLOEXEC Verification** (File Descriptor Isolation)
   - Verified tokio sets `SOCK_CLOEXEC` by default
   - Added tests confirming FD_CLOEXEC on socket descriptors
   - Prevents plugin workers from inheriting sidecar socket FD
   - Documented in SECURITY.md

### Testing

- ✅ Rust unit tests: `test_oversized_request_rejected`, `test_unix_socket_has_fd_cloexec`
- ✅ Python integration tests: `test_oversized_request_rejected`
- ✅ All existing tests pass (no behavioral regressions)
- ✅ Clippy clean, formatted

### Security Impact

- **Before:** Attacker could exhaust daemon memory with multi-GB CBOR payloads
- **After:** Requests capped at 1 MiB, daemon remains responsive

- **Before:** FD_CLOEXEC not verified (potential descriptor leakage)
- **After:** Verified and documented, plugin workers cannot inherit socket FD

### Documentation

- Updated `sidecar/SECURITY.md` with DoS protection section
- Created ADR-002-D documenting design decisions
- Added inline code comments explaining security rationale

### Commits

1. `Security: Add max_request_size_bytes config for DoS protection`
2. `Security: Implement bounded request reading with size limits`
3. `Security: Verify FD_CLOEXEC on Unix socket descriptors`
4. `docs: Document DoS protection and add integration tests`
5. `docs(ADR): Add ADR-002-D documenting DoS protection`
```

### Step 6: Push to remote

**Run:**
```bash
git log --oneline -10  # Review commits
git push
```

**Expected:** All commits pushed successfully to `feature/sidecar-security-daemon`.

---

## Execution Summary

**Total Tasks:** 5
**Estimated Time:** 2-3 hours (assuming tests pass on first try)

**Critical Success Factors:**
1. All tests must pass (Rust + Python)
2. No behavioral regressions to existing functionality
3. Clippy and formatting clean
4. Documentation updated with security rationale

**Rollback Strategy:** If any task fails, revert commits for that task and investigate. Each task is independently committable.

**Final Deliverable:** PR ready for security review with comprehensive DoS protection and FD isolation verification.
