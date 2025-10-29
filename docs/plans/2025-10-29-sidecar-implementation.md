# Rust Sidecar Security Daemon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement production-grade Rust sidecar daemon to eliminate CVE-ADR-002-A-009 (secret export vulnerability) by moving `_CONSTRUCTION_TOKEN` and `_SEAL_KEY` into OS-isolated process with digest-bound capability authorization.

**Architecture:** Three-process model (Rust daemon UID 1001, Python orchestrator UID 1000, plugin workers UID 1002) communicating via Unix sockets with HMAC-authenticated CBOR protocol. Daemon holds secrets in Rust memory and computes digest-bound seals (`HMAC-BLAKE2s(seal_key, frame_id || level || data_digest)` where digest is BLAKE3 of canonical Parquet bytes). Orchestrator maintains FrameRegistry with stable UUIDs and uses `_from_sidecar()` factory. Plugins receive only opaque `SecureFrameProxy` handles with FD_CLOEXEC hygiene preventing descriptor leaks.

**Tech Stack:** Rust 1.77+ (tokio, ring/blake3, serde_cbor, dashmap, tracing, uuid), Python 3.12 (asyncio, cbor2, msgpack for worker RPC, blake3, pyarrow), Docker multi-stage build, supervisord

**Related Documents:**
- Design: `docs/plans/2025-10-29-sidecar-security-daemon-design-v3.md`
- ADRs: ADR-002 (MLS), ADR-002-A (Trusted Container), ADR-003 (Central Registry)
- Vulnerability: CVE-ADR-002-A-009

---

## Milestones

| Milestone | Scope | Blocking | Notes |
| --- | --- | --- | --- |
| M1 | Crypto primitives (`Secrets`, seal compute/verify, TDD harness) | ✅ | Required before any server work; unblocks daemon + client integration |
| M2 | Grant table + lifecycle tests | ✅ | Needed for authorize/redeem flow and replay protection |
| M3 | CBOR protocol definitions + round-trip tests | ✅ | Message schema agreement before implementing client/daemon handlers |
| M4 | Server loop (socket auth, request dispatch, logging) | ✅ | Minimal daemon capable of servicing orchestrator |
| M5 | Observability + metrics exporters | ❌ | Nice-to-have for prod readiness; can follow once daemon is functional |
| M6 | Benchmarks / perf harness (`criterion`, load tests) | ❌ | Optional once correctness is locked in |

## Phase 0: Environment Setup (System Tasks)

**These tasks must be completed by John (system administrator) before implementation begins.**

### Task 0.1: Install Rust Toolchain

**Run as system user:**

```bash
# Install rustup (Rust installer and version manager)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal

# Add cargo to PATH for current session
source $HOME/.cargo/env

# Verify installation
rustc --version  # Should show 1.77.0 or newer
cargo --version  # Should show 1.77.0 or newer

# Install additional components for development
rustup component add rustfmt clippy rust-analyzer
```

**Expected Output:**
```
info: downloading installer
info: profile set to 'minimal'
info: default host triple is x86_64-unknown-linux-gnu
...
Rust is installed now. Great!
```

**Verification:**
```bash
rustc --version
# rustc 1.83.0 (90b35a623 2024-11-26)

cargo --version
# cargo 1.83.0 (5ffbef321 2024-10-29)
```

### Task 0.2: Verify Docker Build Capability

**Run as system user:**

```bash
# Verify Docker can build multi-stage images
docker --version

# Test multi-stage build capability (create temporary Dockerfile)
cat > /tmp/test-multistage.Dockerfile <<'EOF'
FROM rust:1.77-slim as builder
RUN echo "Stage 1: Rust build"

FROM python:3.12-slim
COPY --from=builder /etc/os-release /tmp/test
RUN echo "Stage 2: Python runtime"
EOF

docker build -f /tmp/test-multistage.Dockerfile -t test-multistage /tmp
docker rmi test-multistage
rm /tmp/test-multistage.Dockerfile
```

**Expected Output:**
```
Successfully built [image-id]
Successfully tagged test-multistage:latest
```

### Task 0.3: Install Development Tools (Optional but Recommended)

**Run as system user:**

```bash
# Install VSCode Rust extension (if using VSCode)
# Extensions > Search "rust-analyzer" > Install

# Install cargo tools for development
cargo install cargo-watch    # Auto-rebuild on file changes
cargo install cargo-audit     # Security vulnerability scanning
cargo install cargo-outdated  # Check for outdated dependencies

# Install Python development tools for sidecar client
python -m pip install --upgrade msgpack pytest-asyncio
```

---

## Phase 1: Rust Daemon Skeleton (TDD Foundation)

### Task 1.1: Create Rust Project Structure

**Files:**
- Create: `sidecar/Cargo.toml`
- Create: `sidecar/src/main.rs`
- Create: `sidecar/src/lib.rs`
- Create: `sidecar/.gitignore`

**Step 1: Create sidecar directory and Cargo.toml**

```bash
mkdir -p sidecar/src
cd sidecar
```

Create `sidecar/Cargo.toml`:

```toml
[package]
name = "elspeth-sidecar-daemon"
version = "0.1.0"
edition = "2021"
rust-version = "1.77"

[dependencies]
tokio = { version = "1.35", features = ["full"] }
tokio-util = { version = "0.7", features = ["codec"] }
serde = { version = "1.0", features = ["derive"] }
serde_cbor = "0.11"
blake2 = { version = "0.10", features = ["mac"] }
blake3 = "1.5"
uuid = { version = "1.6", features = ["v4", "serde"] }
dashmap = "5.5"
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "json"] }
anyhow = "1.0"
ring = "0.17"

[dev-dependencies]
tempfile = "3.8"
criterion = "0.5"

[[bin]]
name = "elspeth-sidecar-daemon"
path = "src/main.rs"

[lib]
name = "elspeth_sidecar"
path = "src/lib.rs"

[[bench]]
name = "crypto_bench"
harness = false
```

**Step 2: Create minimal main.rs**

Create `sidecar/src/main.rs`:

```rust
use anyhow::Result;
use tracing::info;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "elspeth_sidecar=debug".into()),
        )
        .init();

    info!("Elspeth Sidecar Daemon starting...");

    // TODO: Load config, start server

    Ok(())
}
```

**Step 3: Create minimal lib.rs**

Create `sidecar/src/lib.rs`:

```rust
//! Elspeth Sidecar Security Daemon
//!
//! OS-isolated process holding `_CONSTRUCTION_TOKEN` and `_SEAL_KEY` in Rust memory.
//! Provides capability-based authorization via Unix socket with HMAC authentication.

pub mod config;
pub mod crypto;
pub mod protocol;
pub mod server;
pub mod grants;

pub use config::Config;
```

**Step 4: Create .gitignore**

Create `sidecar/.gitignore`:

```
/target
Cargo.lock
*.pem
*.key
.session
```

**Step 5: Verify Rust project builds**

```bash
cd sidecar
cargo build
```

**Expected Output:**
```
   Compiling elspeth-sidecar-daemon v0.1.0 (/home/john/elspeth/sidecar)
    Finished dev [unoptimized + debuginfo] target(s) in 45.23s
```

**Step 6: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): initialize Rust project skeleton

- Cargo.toml with tokio, ring, serde_cbor dependencies
- Minimal main.rs with tracing setup
- Placeholder lib.rs with module declarations
- .gitignore for Rust artifacts"
```

---

### Task 1.2: Implement Crypto Module (Secrets + HMAC)

**Files:**
- Create: `sidecar/src/crypto.rs`
- Create: `sidecar/tests/crypto_test.rs`

**Step 1: Write failing test for Secrets generation**

Create `sidecar/tests/crypto_test.rs`:

```rust
use elspeth_sidecar::crypto::Secrets;
use uuid::Uuid;

fn fixed_digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

#[test]
fn test_secrets_generate_creates_random_values() {
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0xAB);
    let seal1 = Secrets::generate().compute_seal(frame_id, 3, &digest);
    let seal2 = Secrets::generate().compute_seal(frame_id, 3, &digest);

    // Independent secrets should produce different seals with overwhelming probability.
    assert_ne!(seal1, seal2);
    assert_eq!(seal1.len(), 32);
    assert_eq!(seal2.len(), 32);
}

#[test]
fn test_secrets_compute_seal_deterministic() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0xAB);
    let level = 3u32; // SECRET

    let seal1 = secrets.compute_seal(frame_id, level, &digest);
    let seal2 = secrets.compute_seal(frame_id, level, &digest);

    // Same inputs produce same seal
    assert_eq!(seal1, seal2);
    assert_eq!(seal1.len(), 32);
}

#[test]
fn test_secrets_verify_seal_success() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0x42);

    let seal = secrets.compute_seal(frame_id, 2, &digest);

    // Verification succeeds for matching tuple
    assert!(secrets.verify_seal(frame_id, 2, &digest, &seal));
}

#[test]
fn test_secrets_verify_seal_fails_wrong_frame_id() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let other_frame_id = Uuid::new_v4();
    let digest = fixed_digest(0x11);

    let seal = secrets.compute_seal(frame_id, 1, &digest);

    assert!(!secrets.verify_seal(other_frame_id, 1, &digest, &seal));
}

#[test]
fn test_secrets_verify_seal_fails_wrong_level() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0x22);

    let seal = secrets.compute_seal(frame_id, 4, &digest);

    assert!(!secrets.verify_seal(frame_id, 3, &digest, &seal));
}

#[test]
fn test_secrets_verify_seal_fails_wrong_digest() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();

    let seal = secrets.compute_seal(frame_id, 3, &fixed_digest(0x33));

    assert!(!secrets.verify_seal(frame_id, 3, &fixed_digest(0x34), &seal));
}
```

**Step 2: Run test to verify it fails**

```bash
cargo test crypto_test
```

**Expected Output:**
```
error[E0433]: failed to resolve: could not find `crypto` in `elspeth_sidecar`
 --> tests/crypto_test.rs:1:27
  |
1 | use elspeth_sidecar::crypto::Secrets;
  |                       ^^^^^^ could not find `crypto` in `elspeth_sidecar`
```

**Step 3: Implement minimal Secrets struct**

Create `sidecar/src/crypto.rs`:

```rust
//! Cryptographic primitives for sidecar daemon.
//!
//! - `Secrets`: Holds construction token and seal key in Rust memory
//! - `compute_seal()`: BLAKE2s-MAC(seal_key, frame_id || level || data_digest)
//! - `verify_seal()`: Constant-time seal comparison

use blake2::digest::{Update, FixedOutput, KeyInit};
use blake2::Blake2sMac256;
use ring::rand::{SecureRandom, SystemRandom};
use ring::constant_time;
use uuid::Uuid;

/// Secrets held in Rust memory (never exported to Python).
pub struct Secrets {
    construction_token: [u8; 32],
    seal_key: [u8; 32],
}

impl Secrets {
    /// Generate fresh secrets using cryptographically secure RNG.
    pub fn generate() -> Self {
        let rng = SystemRandom::new();

        // Generate construction token (256-bit random)
        let mut construction_token = [0u8; 32];
        rng.fill(&mut construction_token)
            .expect("RNG failure");

        // Generate seal key (256-bit random for BLAKE2s MAC)
        let mut seal_key_bytes = [0u8; 32];
        rng.fill(&mut seal_key_bytes)
            .expect("RNG failure");

        Self {
            construction_token,
            seal_key: seal_key_bytes,
        }
    }

    /// Compute tamper-evident seal for `(frame_id, level, data_digest)`.
    ///
    /// Seal = BLAKE2s-MAC(seal_key, frame_id || level || data_digest)
    pub fn compute_seal(&self, frame_id: Uuid, level: u32, data_digest: &[u8; 32]) -> [u8; 32] {
        let mut message = Vec::with_capacity(16 + 4 + 32);
        message.extend_from_slice(frame_id.as_bytes());
        message.extend_from_slice(&level.to_be_bytes());
        message.extend_from_slice(data_digest);

        let mut mac = Blake2sMac256::new_from_slice(&self.seal_key)
            .expect("seal key length must be 32 bytes");
        mac.update(&message);
        let output = mac.finalize_fixed();
        let mut seal = [0u8; 32];
        seal.copy_from_slice(&output);
        seal
    }

    /// Verify seal using constant-time comparison.
    pub fn verify_seal(
        &self,
        frame_id: Uuid,
        level: u32,
        data_digest: &[u8; 32],
        seal: &[u8],
    ) -> bool {
        let expected = self.compute_seal(frame_id, level, data_digest);
        constant_time::verify_slices_are_equal(seal, &expected).is_ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn test_compute_seal_deterministic() {
        let secrets = Secrets::generate();
        let frame = Uuid::new_v4();
        let digest = [0x55; 32];
        let seal1 = secrets.compute_seal(frame, 3, &digest);
        let seal2 = secrets.compute_seal(frame, 3, &digest);
        assert_eq!(seal1, seal2);
    }

    #[test]
    fn test_verify_seal_success() {
        let secrets = Secrets::generate();
        let frame = Uuid::new_v4();
        let digest = [0x66; 32];
        let seal = secrets.compute_seal(frame, 3, &digest);
        assert!(secrets.verify_seal(frame, 3, &digest, &seal));
    }

    #[test]
    fn test_verify_seal_wrong_frame_id() {
        let secrets = Secrets::generate();
        let frame = Uuid::new_v4();
        let digest = [0x44; 32];
        let seal = secrets.compute_seal(frame, 3, &digest);
        assert!(!secrets.verify_seal(Uuid::new_v4(), 3, &digest, &seal));
    }
}
```

**Step 4: Run tests to verify they pass**

```bash
cargo test crypto
```

**Expected Output:**
```
running 5 tests
test crypto_test::test_secrets_compute_seal_deterministic ... ok
test crypto_test::test_secrets_generate_creates_random_values ... ok
test crypto_test::test_secrets_verify_seal_fails_wrong_digest ... ok
test crypto_test::test_secrets_verify_seal_fails_wrong_frame_id ... ok
test crypto_test::test_secrets_verify_seal_fails_wrong_level ... ok
test crypto_test::test_secrets_verify_seal_success ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

**Step 6: Commit**

```bash
git add sidecar/src/crypto.rs sidecar/tests/crypto_test.rs
git commit -m "feat(sidecar): implement Secrets with BLAKE2s seals

- Secrets::generate() creates random token + seal key
- compute_seal() produces BLAKE2s-MAC(seal_key, frame_id || level || data_digest)
- verify_seal() uses constant-time comparison
- 6 passing tests for determinism and verification"
```

---

### Task 1.3: Implement Grant Table (One-Shot Handles)

**Files:**
- Create: `sidecar/src/grants.rs`
- Create: `sidecar/tests/grants_test.rs`

**Step 1: Write failing test for grant lifecycle**

Create `sidecar/tests/grants_test.rs`:

```rust
use elspeth_sidecar::grants::{GrantRequest, GrantTable};
use std::time::Duration;
use uuid::Uuid;

fn digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

#[tokio::test]
async fn test_grant_authorize_and_redeem_success() {
    let table = GrantTable::new(Duration::from_secs(60));
    let request = GrantRequest {
        frame_id: Uuid::new_v4(),
        level: 3,
        data_digest: digest(0x90),
    };

    // Authorize creates grant
    let grant_id = table.authorize(request.clone()).await;
    assert_eq!(grant_id.len(), 16);

    // Redeem succeeds once
    let result = table.redeem(&grant_id).await;
    assert!(result.is_ok());
    let redeemed = result.unwrap();
    assert_eq!(redeemed.frame_id, request.frame_id);
    assert_eq!(redeemed.level, 3);
    assert_eq!(redeemed.data_digest, request.data_digest);

    // Redeem fails second time (one-shot)
    let result2 = table.redeem(&grant_id).await;
    assert!(result2.is_err());
}

#[tokio::test]
async fn test_grant_expires_after_ttl() {
    let table = GrantTable::new(Duration::from_millis(100));
    let request = GrantRequest {
        frame_id: Uuid::new_v4(),
        level: 3,
        data_digest: digest(0x33),
    };

    let grant_id = table.authorize(request).await;

    // Wait for expiry
    tokio::time::sleep(Duration::from_millis(150)).await;

    // Redeem fails (expired)
    let result = table.redeem(&grant_id).await;
    assert!(matches!(result, Err(_)));
}

#[tokio::test]
async fn test_grant_cleanup_removes_expired() {
    let table = GrantTable::new(Duration::from_millis(50));

    // Create 3 grants
    for tag in 0..3 {
        let request = GrantRequest {
            frame_id: Uuid::new_v4(),
            level: 3,
            data_digest: digest(tag),
        };
        table.authorize(request).await;
    }

    // Wait for expiry
    tokio::time::sleep(Duration::from_millis(100)).await;

    // Trigger cleanup
    table.cleanup_expired().await;

    // All grants should be removed (checking via active count)
    assert_eq!(table.active_count().await, 0);
}
```

**Step 2: Run test to verify it fails**

```bash
cargo test grants
```

**Expected Output:**
```
error[E0433]: failed to resolve: could not find `grants` in `elspeth_sidecar`
```

**Step 3: Implement GrantTable**

Create `sidecar/src/grants.rs`:

```rust
//! Grant table for one-shot authorization handles.
//!
//! - `authorize()`: Creates grant with TTL, returns 128-bit handle
//! - `redeem()`: Validates and consumes grant (one-shot)
//! - `cleanup_expired()`: Background task removes expired grants

use dashmap::DashMap;
use ring::rand::{SecureRandom, SystemRandom};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};
use uuid::Uuid;

/// Request to authorize SecureDataFrame construction.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct GrantRequest {
    pub frame_id: Uuid,
    pub level: u32,
    pub data_digest: [u8; 32],
}

/// Grant state (stored in table until redeemed or expired).
#[derive(Clone, Debug)]
struct Grant {
    request: GrantRequest,
    expires_at: Instant,
}

/// Grant table with TTL-based expiry and one-shot redemption.
pub struct GrantTable {
    grants: Arc<DashMap<[u8; 16], Grant>>,
    ttl: Duration,
    rng: SystemRandom,
}

impl GrantTable {
    /// Create new grant table with specified TTL.
    pub fn new(ttl: Duration) -> Self {
        Self {
            grants: Arc::new(DashMap::new()),
            ttl,
            rng: SystemRandom::new(),
        }
    }

    /// Authorize construction, return 128-bit grant ID.
    pub async fn authorize(&self, request: GrantRequest) -> [u8; 16] {
        let mut grant_id = [0u8; 16];
        self.rng.fill(&mut grant_id).expect("RNG failure");

        let grant = Grant {
            request,
            expires_at: Instant::now() + self.ttl,
        };

        self.grants.insert(grant_id, grant);
        grant_id
    }

    /// Redeem grant (one-shot, removes from table).
    pub async fn redeem(&self, grant_id: &[u8; 16]) -> Result<GrantRequest, String> {
        let (_, grant) = self
            .grants
            .remove(grant_id)
            .ok_or_else(|| "Grant not found or already redeemed".to_string())?;

        if Instant::now() > grant.expires_at {
            return Err("Grant expired".to_string());
        }

        Ok(grant.request)
    }

    /// Remove expired grants (background cleanup task).
    pub async fn cleanup_expired(&self) {
        let now = Instant::now();
        self.grants.retain(|_, grant| grant.expires_at > now);
    }

    /// Count active grants (for testing).
    pub async fn active_count(&self) -> usize {
        self.grants.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[tokio::test]
    async fn test_authorize_creates_unique_ids() {
        let table = GrantTable::new(Duration::from_secs(60));
        let request = GrantRequest {
            frame_id: Uuid::new_v4(),
            level: 3,
            data_digest: [0xAA; 32],
        };

        let id1 = table.authorize(request.clone()).await;
        let id2 = table.authorize(request.clone()).await;

        assert_ne!(id1, id2);
    }
}
```

**Step 4: Run tests to verify they pass**

```bash
cargo test grants
```

**Expected Output:**
```
running 4 tests
test grants_test::test_grant_authorize_and_redeem_success ... ok
test grants_test::test_grant_cleanup_removes_expired ... ok
test grants_test::test_grant_expires_after_ttl ... ok
test grants::tests::test_authorize_creates_unique_ids ... ok

test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

**Step 5: Commit**

```bash
git add sidecar/src/grants.rs sidecar/tests/grants_test.rs
git commit -m "feat(sidecar): implement GrantTable for one-shot handles

- authorize() creates 128-bit random grant with TTL
- redeem() validates and removes grant (one-shot)
- cleanup_expired() removes expired grants
- 4 passing tests for lifecycle and expiry"
```

---

### Task 1.4: Implement CBOR Protocol Messages

**Files:**
- Create: `sidecar/src/protocol.rs`
- Create: `sidecar/tests/protocol_test.rs`

**Step 1: Write failing test for message serialization**

Create `sidecar/tests/protocol_test.rs`:

```rust
use elspeth_sidecar::protocol::{Request, Response};

fn digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

fn frame(tag: u8) -> [u8; 16] {
    [tag; 16]
}

#[test]
fn test_authorize_construct_request_serialization() {
    let request = Request::AuthorizeConstruct {
        frame_id: frame(0xAA),
        level: 3,
        data_digest: digest(0xBB),
        auth: vec![0xAB; 32],
    };

    // Serialize to CBOR
    let bytes = serde_cbor::to_vec(&request).unwrap();

    // Deserialize back
    let decoded: Request = serde_cbor::from_slice(&bytes).unwrap();

    match decoded {
        Request::AuthorizeConstruct {
            frame_id,
            level,
            data_digest,
            auth,
        } => {
            assert_eq!(frame_id, frame(0xAA));
            assert_eq!(level, 3);
            assert_eq!(data_digest, digest(0xBB));
            assert_eq!(auth, vec![0xAB; 32]);
        }
        _ => panic!("Wrong variant"),
    }
}

#[test]
fn test_authorize_construct_reply_serialization() {
    let response = Response::AuthorizeConstructReply {
        grant_id: [0xFF; 16],
        expires_at: 1698765432.123,
    };

    let bytes = serde_cbor::to_vec(&response).unwrap();
    let decoded: Response = serde_cbor::from_slice(&bytes).unwrap();

    match decoded {
        Response::AuthorizeConstructReply { grant_id, expires_at } => {
            assert_eq!(grant_id, [0xFF; 16]);
            assert_eq!(expires_at, 1698765432.123);
        }
        _ => panic!("Wrong variant"),
    }
}

#[test]
fn test_error_response_serialization() {
    let response = Response::Error {
        error: "Grant not found".to_string(),
        reason: "Already redeemed".to_string(),
    };

    let bytes = serde_cbor::to_vec(&response).unwrap();
    let decoded: Response = serde_cbor::from_slice(&bytes).unwrap();

    match decoded {
        Response::Error { error, reason } => {
            assert_eq!(error, "Grant not found");
            assert_eq!(reason, "Already redeemed");
        }
        _ => panic!("Wrong variant"),
    }
}
```

**Step 2: Run test to verify it fails**

```bash
cargo test protocol
```

**Expected Output:**
```
error[E0433]: failed to resolve: could not find `protocol` in `elspeth_sidecar`
```

**Step 3: Implement protocol messages**

Create `sidecar/src/protocol.rs`:

```rust
//! CBOR protocol messages for daemon ↔ orchestrator communication.
//!
//! All messages include `auth` field with HMAC-BLAKE2s(session_key, canonical_cbor(request_without_auth)).

use serde::{Deserialize, Serialize};

/// Client request to daemon.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op")]
pub enum Request {
    /// Request one-shot grant for `(frame_id, level, data_digest)`.
    #[serde(rename = "authorize_construct")]
    AuthorizeConstruct {
        frame_id: [u8; 16],  // UUID v4 serialized to 16 bytes (Uuid::as_bytes())
        level: u32,
        data_digest: [u8; 32],
        auth: Vec<u8>, // HMAC over canonical tuple
    },

    /// Redeem grant for seal.
    #[serde(rename = "redeem_grant")]
    RedeemGrant {
        grant_id: [u8; 16],
        auth: Vec<u8>, // HMAC of grant_id
    },

    /// Consume construction ticket before instantiation.
    #[serde(rename = "consume_construction_ticket")]
    ConsumeConstructionTicket {
        ticket: [u8; 32],
        auth: Vec<u8>,
    },

    /// Compute seal for existing frame.
    #[serde(rename = "compute_seal")]
    ComputeSeal {
        frame_id: [u8; 16],
        level: u32,
        data_digest: [u8; 32],
        auth: Vec<u8>,
    },

    /// Verify seal integrity.
    #[serde(rename = "verify_seal")]
    VerifySeal {
        frame_id: [u8; 16],
        level: u32,
        data_digest: [u8; 32],
        seal: [u8; 32],
        auth: Vec<u8>,
    },
}

/// Daemon response to client.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Response {
    /// Grant authorized (expires after TTL).
    AuthorizeConstructReply {
        grant_id: [u8; 16],
        expires_at: f64, // Unix timestamp
    },

    /// Grant redeemed, seal computed.
    RedeemGrantReply {
        construction_ticket: [u8; 32],
        seal: [u8; 32],
        audit_id: u64,
    },

    /// Seal computed.
    ComputeSealReply {
        seal: [u8; 32],
        audit_id: u64,
    },

    /// Ticket consumption acknowledgement.
    ConsumeTicketReply {
        consumed: bool,
        audit_id: u64,
    },

    /// Seal verification result.
    VerifySealReply {
        valid: bool,
        audit_id: u64,
    },

    /// Error response.
    Error {
        error: String,
        reason: String,
    },
}

impl Request {
    /// Extract auth field for validation.
    pub fn auth(&self) -> &[u8] {
        match self {
            Request::AuthorizeConstruct { auth, .. } => auth,
            Request::RedeemGrant { auth, .. } => auth,
            Request::ConsumeConstructionTicket { auth, .. } => auth,
            Request::ComputeSeal { auth, .. } => auth,
            Request::VerifySeal { auth, .. } => auth,
        }
    }

    /// Canonical CBOR bytes (without auth field) for HMAC computation.
    pub fn canonical_bytes_without_auth(&self) -> Vec<u8> {
        match self {
            Request::AuthorizeConstruct {
                frame_id,
                level,
                data_digest,
                ..
            } => serde_cbor::to_vec(&(frame_id, *level, data_digest)).unwrap(),
            Request::RedeemGrant { grant_id, .. } => serde_cbor::to_vec(grant_id).unwrap(),
            Request::ConsumeConstructionTicket { ticket, .. } => serde_cbor::to_vec(ticket).unwrap(),
            Request::ComputeSeal {
                frame_id,
                level,
                data_digest,
                ..
            } => serde_cbor::to_vec(&(frame_id, *level, data_digest)).unwrap(),
            Request::VerifySeal {
                frame_id,
                level,
                data_digest,
                seal,
                ..
            } => serde_cbor::to_vec(&(frame_id, *level, data_digest, seal)).unwrap(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_canonical_bytes_deterministic() {
        let req = Request::AuthorizeConstruct {
            frame_id: [0x01; 16],
            level: 3,
            data_digest: [0x02; 32],
            auth: vec![],
        };

        let bytes1 = req.canonical_bytes_without_auth();
        let bytes2 = req.canonical_bytes_without_auth();

        assert_eq!(bytes1, bytes2);
    }
}
```

**Step 4: Run tests to verify they pass**

```bash
cargo test protocol
```

**Expected Output:**
```
running 4 tests
test protocol_test::test_authorize_construct_reply_serialization ... ok
test protocol_test::test_authorize_construct_request_serialization ... ok
test protocol_test::test_error_response_serialization ... ok
test protocol::tests::test_canonical_bytes_deterministic ... ok

test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

**Step 5: Commit**

```bash
git add sidecar/src/protocol.rs sidecar/tests/protocol_test.rs
git commit -m "feat(sidecar): implement CBOR protocol messages

- Request enum (AuthorizeConstruct, RedeemGrant, ComputeSeal, VerifySeal)
- Response enum (replies + Error variant)
- canonical_bytes_without_auth() for HMAC computation
- 4 passing tests for serialization roundtrips"
```

---

## Phase 2: Unix Socket Server (IPC Layer)

### Task 2.1: Implement Config Loading

**Files:**
- Create: `sidecar/src/config.rs`
- Create: `sidecar/config/sidecar.toml` (example)
- Create: `sidecar/tests/config_test.rs`

**Step 1: Write failing test for config parsing**

Create `sidecar/tests/config_test.rs`:

```rust
use elspeth_sidecar::Config;
use std::path::PathBuf;

#[test]
fn test_config_from_file() {
    let config_str = r#"
socket_path = "/run/sidecar/auth.sock"
session_key_path = "/run/sidecar/.session"
appuser_uid = 1000
grant_ttl_secs = 60
log_level = "debug"
"#;

    let config: Config = toml::from_str(config_str).unwrap();

    assert_eq!(config.socket_path, PathBuf::from("/run/sidecar/auth.sock"));
    assert_eq!(config.session_key_path, PathBuf::from("/run/sidecar/.session"));
    assert_eq!(config.appuser_uid, 1000);
    assert_eq!(config.grant_ttl_secs, 60);
    assert_eq!(config.log_level, "debug");
}
```

**Step 2: Run test to verify it fails**

```bash
cargo test config_test
```

**Expected Output:**
```
error[E0433]: failed to resolve: could not find `Config` in `elspeth_sidecar`
```

**Step 3: Implement Config struct**

Add to `sidecar/Cargo.toml`:
```toml
toml = "0.8"
```

Create `sidecar/src/config.rs`:

```rust
//! Configuration loading from TOML.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::time::Duration;

/// Sidecar daemon configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    /// Unix socket path (e.g., /run/sidecar/auth.sock)
    pub socket_path: PathBuf,

    /// Session key file path (e.g., /run/sidecar/.session)
    pub session_key_path: PathBuf,

    /// UID of orchestrator process (for SO_PEERCRED check)
    pub appuser_uid: u32,

    /// Grant TTL in seconds
    pub grant_ttl_secs: u64,

    /// Log level (trace, debug, info, warn, error)
    pub log_level: String,
}

impl Config {
    /// Load config from TOML file.
    pub fn load(path: &str) -> Result<Self> {
        let contents = fs::read_to_string(path)
            .with_context(|| format!("Failed to read config from {}", path))?;

        let config: Config = toml::from_str(&contents)
            .with_context(|| format!("Failed to parse TOML from {}", path))?;

        Ok(config)
    }

    /// Grant TTL as Duration.
    pub fn grant_ttl(&self) -> Duration {
        Duration::from_secs(self.grant_ttl_secs)
    }
}

impl Default for Config {
    fn default() -> Self {
        Self {
            socket_path: PathBuf::from("/run/sidecar/auth.sock"),
            session_key_path: PathBuf::from("/run/sidecar/.session"),
            appuser_uid: 1000,
            grant_ttl_secs: 60,
            log_level: "info".to_string(),
        }
    }
}
```

**Step 4: Create example config file**

Create `sidecar/config/sidecar.toml`:

```toml
# Elspeth Sidecar Daemon Configuration

# Unix socket path (must be writable by sidecar UID, readable by appuser)
socket_path = "/run/sidecar/auth.sock"

# Session key file (must be readable by appuser, written by sidecar)
session_key_path = "/run/sidecar/.session"

# UID of orchestrator process (for SO_PEERCRED enforcement)
appuser_uid = 1000

# Grant TTL in seconds (default: 60s)
grant_ttl_secs = 60

# Log level: trace, debug, info, warn, error
log_level = "info"
```

**Step 5: Run tests to verify they pass**

```bash
cargo test config
```

**Expected Output:**
```
running 1 test
test config_test::test_config_from_file ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

**Step 6: Commit**

```bash
git add sidecar/src/config.rs sidecar/config/sidecar.toml sidecar/tests/config_test.rs sidecar/Cargo.toml
git commit -m "feat(sidecar): implement Config loading from TOML

- Config struct with socket_path, session_key_path, appuser_uid
- load() method parses TOML file
- Default config for development
- Example config/sidecar.toml"
```

---

### Task 2.2: Implement Unix Socket Server Skeleton

**Files:**
- Create: `sidecar/src/server.rs`
- Modify: `sidecar/src/main.rs`

**Step 1: Implement server skeleton**

Create `sidecar/src/server.rs`:

```rust
//! Unix socket server for daemon ↔ orchestrator IPC.

use crate::config::Config;
use crate::crypto::Secrets;
use crate::grants::GrantTable;
use crate::protocol::{Request, Response};
use anyhow::{Context, Result};
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use tracing::{debug, error, info, warn};

/// Sidecar daemon server.
pub struct Server {
    config: Arc<Config>,
    secrets: Arc<Secrets>,
    grants: Arc<GrantTable>,
    session_key: Vec<u8>,
    session_key_path: PathBuf,  // Stored for session key persistence/reload
}

impl Server {
    /// Create new server with generated secrets.
    pub fn new(config: Config) -> Result<Self> {
        let secrets = Arc::new(Secrets::generate());
        let grants = Arc::new(GrantTable::new(config.grant_ttl()));
        let (session_key, session_key_path) = Self::load_or_init_session_key(&config)?;

        Ok(Self {
            config: Arc::new(config),
            secrets,
            grants,
            session_key,
            session_key_path,
        })
    }

    /// Run server (listens on Unix socket).
    pub async fn run(&self) -> Result<()> {
        // Remove stale socket if exists
        if self.config.socket_path.exists() {
            std::fs::remove_file(&self.config.socket_path)
                .context("Failed to remove stale socket")?;
        }

        // Bind Unix socket
        let listener = UnixListener::bind(&self.config.socket_path)
            .context("Failed to bind Unix socket")?;

        info!("Listening on {:?}", self.config.socket_path);

        // Accept connections
        loop {
            match listener.accept().await {
                Ok((stream, _addr)) => {
                    let config = self.config.clone();
                    let secrets = self.secrets.clone();
                    let grants = self.grants.clone();
                    let session_key = self.session_key.clone();

                    tokio::spawn(async move {
                        if let Err(e) = Self::handle_client(stream, config, secrets, grants, session_key).await {
                            error!("Client error: {}", e);
                        }
                    });
                }
                Err(e) => {
                    error!("Accept error: {}", e);
                }
            }
        }
    }

    /// Handle single client connection.
    async fn handle_client(
        mut stream: UnixStream,
        config: Arc<Config>,
        secrets: Arc<Secrets>,
        grants: Arc<GrantTable>,
        session_key: Vec<u8>,
    ) -> Result<()> {
        // TODO: SO_PEERCRED check

        debug!("Client connected");

        // Read CBOR frames
        let mut buffer = vec![0u8; 4096];
        let n = stream.read(&mut buffer).await?;

        if n == 0 {
            return Ok(()); // EOF
        }

        let request: Request = serde_cbor::from_slice(&buffer[..n])
            .context("Failed to parse CBOR request")?;

        debug!("Received request: {:?}", request);

        // TODO: Validate HMAC using session_key
        // TODO: Dispatch request
        // TODO: Send response

        let response = Response::Error {
            error: "Not implemented".to_string(),
            reason: "Server skeleton only".to_string(),
        };

        let response_bytes = serde_cbor::to_vec(&response)?;
        stream.write_all(&response_bytes).await?;

        Ok(())
    }

    fn load_or_init_session_key(config: &Config) -> Result<(Vec<u8>, PathBuf)> {
        // TODO: Implement in Task 2.3 (secure session key generation + persistence)
        unimplemented!("load_or_init_session_key placeholder");
    }
}
```

**Step 2: Update main.rs to start server**

Update `sidecar/src/main.rs`:

```rust
use anyhow::Result;
use elspeth_sidecar::{Config, server::Server};
use tracing::info;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "elspeth_sidecar=debug".into()),
        )
        .init();

    info!("Elspeth Sidecar Daemon starting...");

    // Load config
    let config = Config::load("/etc/elspeth/sidecar.toml")
        .unwrap_or_else(|_| {
            eprintln!("Failed to load config, using defaults");
            Config::default()
        });

    // Start server
    let server = Server::new(config)?;
    server.run().await?;

    Ok(())
}
```

**Step 3: Update lib.rs exports**

Update `sidecar/src/lib.rs`:

```rust
//! Elspeth Sidecar Security Daemon

pub mod config;
pub mod crypto;
pub mod protocol;
pub mod server;
pub mod grants;

pub use config::Config;
pub use server::Server;
```

**Step 4: Build and verify no compile errors**

```bash
cargo build
```

**Expected Output:**
```
   Compiling elspeth-sidecar-daemon v0.1.0
    Finished dev [unoptimized + debuginfo] target(s) in 12.34s
```

**Step 5: Commit**

```bash
git add sidecar/src/server.rs sidecar/src/main.rs sidecar/src/lib.rs
git commit -m "feat(sidecar): implement Unix socket server skeleton

- Server struct manages listener + connections
- handle_client() parses CBOR requests (dispatch TODO)
- main.rs loads config and starts server
- Compiles successfully (functionality incomplete)"
```

---

### Task 2.3: Initialize Session Key Material (Mutual Auth Backbone)

**Files:**
- Update: `sidecar/src/server.rs`
- Create: `sidecar/tests/session_key_test.rs`

**Goal:** Replace the placeholder all-zero session key with secure generation, persistence, and reload logic matching the design’s mutual-auth requirements.

**Step 1: Implement `load_or_init_session_key`**

- In `sidecar/src/server.rs`, replace the `unimplemented!` with logic that:
  - Uses `ring::rand::SystemRandom` to generate 32 random bytes when the session file is absent.
  - Writes the key to `config.session_key_path` using `OpenOptions` with `O_CREAT | O_EXCL`, `0o640` permissions, owner `sidecar`, group `appuser`.
  - Calls `fsync` on both file and parent directory.
  - Reloads the bytes on restart without regenerating.
  - Returns `(session_key, session_key_path.clone())`.
- Add explicit error messages when chmod/chown fails so ops know permissions are wrong.

**Step 2: Unit tests**

- Create `sidecar/tests/session_key_test.rs` covering:
  1. First call creates the file with correct length and `0o640` bits.
  2. Second call reuses the same key (no regeneration).
  3. Permission mismatch (e.g., file already exists but mode != 0o640) triggers an error.
  4. File owned by unexpected UID/GID raises error (simulate via `chown` in temp dir).

**Step 3: Wire into server startup**

- Ensure `Server::new` uses the new function, and store `session_key_path` on the struct.
- Update `Server::handle_client` TODO comment to reference `session_key`.
- Log a single structured message that session key was initialized (without printing the key).

**Step 4: Documentation**

- Update `sidecar/config/sidecar.toml` comments to stress that the daemon owns the file and orchestrators only need read access.
- Add a note in the runbook section explaining how ops rotate the session key (restart daemon).

**Step 5: Commit**

```bash
git add sidecar/src/server.rs sidecar/tests/session_key_test.rs sidecar/config/sidecar.toml
git commit -m "feat(sidecar): generate and persist session key material"
```

---

### Task 2.4: Track Registered Frames and Enforce Known IDs

**Why:** The v3 design requires the daemon to remember which `frame_id` values were legitimately created (grant redeemed) and to reject `compute_seal`/`verify_seal` calls for unknown IDs. Without this gate a rogue client could mint arbitrary frame identifiers and obtain seals, reopening CVE-ADR-002-A-009.

**Files:**
- Update: `sidecar/src/grants.rs`
- Update: `sidecar/src/server.rs`
- Create: `sidecar/src/frames.rs`
- Create: `sidecar/tests/frames_test.rs`

**Step 1: Define RegisteredFrameTable**

Create `sidecar/src/frames.rs` with a `RegisteredFrameTable` that stores `(frame_id, level, data_digest)` entries in a `DashMap<Uuid, FrameMetadata>`. Provide:
- `register_from_grant(grant_request: GrantRequest)` – inserts metadata when a grant is redeemed.
- `update(frame_id, level, digest)` – overwrites metadata on reseal (compute path).
- `get(frame_id)` – returns metadata if present.
- `contains(frame_id)` – helper for guard checks.

**Step 2: Add tests**

`sidecar/tests/frames_test.rs` should cover:
- Registering a frame via `register_from_grant` makes it discoverable.
- Attempting to update an unknown frame returns an error.
- Metadata reflects the latest level/digest after an update.

**Step 3: Integrate with GrantTable and Server**

- Modify `GrantTable::redeem` to return `GrantRequest` as today; the server will now call `RegisteredFrameTable::register_from_grant` immediately after a successful redeem.
- Extend `Server` with a new `frames: Arc<RegisteredFrameTable>` field.
- In the `compute_seal` and `verify_seal` handlers (implemented in later tasks), look up the frame first; if not found, return a `Response::Error { error: "unknown_frame_id", … }`.
- When `ComputeSeal` succeeds, call `frames.update(...)` with the new `(level, digest)` so future verifications use the latest metadata.

**Step 4: Tests for guard rails**

Add async integration tests (under `tests/grants_test.rs` or a new `tests/server_guard_test.rs`) that simulate:
- Calling `compute_seal` before any grant is redeemed → expect error.
- Redeeming a grant, then calling `compute_seal` → succeeds.
- Calling `verify_seal` with a known frame id but wrong digest → returns `valid=false`.

**Step 5: Commit**

```bash
git add sidecar/src/frames.rs sidecar/tests/frames_test.rs sidecar/src/grants.rs sidecar/src/server.rs
git commit -m "feat(sidecar): track registered frames and guard compute/verify

- RegisteredFrameTable persists frame metadata post-grant
- Server rejects compute/verify for unknown frame IDs
- Tests cover registration, updates, and guard failures"
```

---

## Phase 3: Python Integration (Sidecar Client + Factories)

### Task 3.0: Establish Plugin Worker Isolation Boundary

**Goal:** Make the trust boundary real before exposing the client. All untrusted plugins must execute in a subprocess running as `appplugin` (UID 1002) with no read access to `/run/sidecar/` or the session key.

**Files:**
- Create: `src/elspeth/orchestrator/worker_process.py`
- Update: `src/elspeth/orchestrator/runtime.py`
- Update: `docker/supervisord.conf`
- Update: Docker user/entrypoint scripts
- Add: integration tests under `tests/integration/test_worker_isolation.py`

**Steps:**
1. **Create worker entrypoint**
   - Implement `worker_process.py` that imports plugins and executes transformations.
   - Communicate with orchestrator over a restricted IPC channel (stdin/stdout msgpack or `multiprocessing.Connection`).
   - Ensure worker never imports `elspeth.core.security.sidecar_client`.
2. **Spawn worker with separate UID**
   - In orchestrator runtime, fork/exec the worker via `subprocess.Popen`, using `setuid(appplugin)` (Linux) or run script via `sudo -u appplugin` in container.
   - Ensure environment lacks `SIDECAR_SESSION_KEY` and has no access to `/run/sidecar/`.
3. **Descriptor hygiene**
   - Establish sidecar connection *after* worker spawn.
   - Mark orchestrator-side sockets/file descriptors with `FD_CLOEXEC`.
4. **Tests**
   - Add test that worker process cannot `open("/run/sidecar/.session")` (expect `PermissionError`).
   - Add test that worker attempting to connect to `/run/sidecar/auth.sock` gets `PermissionError`.
5. **Docs**
   - Update runbook to describe the new `appplugin` user and how to rotate credentials.

**Commit Example:**
```bash
git add src/elspeth/orchestrator/*.py docker/supervisord.conf tests/integration/test_worker_isolation.py
git commit -m "feat(orchestrator): isolate plugin workers under appplugin UID"
```

---

### Task 3.1: Implement Python Sidecar Client

**Files:**
- Create: `src/elspeth/orchestrator/sidecar_client.py`
- Create: `tests/orchestrator/test_sidecar_client.py`

**Step 1: Write failing test for sidecar client**

Create `tests/orchestrator/test_sidecar_client.py`:

```python
"""Tests for sidecar daemon client."""

import pytest
from elspeth.orchestrator.sidecar_client import SidecarClient, SidecarError


@pytest.mark.asyncio
async def test_sidecar_client_not_implemented():
    """Verify SidecarClient raises NotImplementedError (skeleton only)."""
    # NOTE: This test will be replaced once Rust daemon is running
    with pytest.raises((NotImplementedError, FileNotFoundError, SidecarError)):
        client = SidecarClient(socket_path="/run/sidecar/auth.sock")
        await client.connect()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/orchestrator/test_sidecar_client.py -v
```

**Expected Output:**
```
ModuleNotFoundError: No module named 'elspeth.orchestrator.sidecar_client'
```

**Step 3: Implement minimal SidecarClient**

Create `src/elspeth/orchestrator/sidecar_client.py`:

```python
"""Sidecar daemon client for Python orchestrator.

Communicates with Rust daemon via Unix socket using CBOR protocol.
All messages are HMAC-authenticated using session key. This module stays in
`elspeth.orchestrator` and must never be re-exported to plugin workers.

Protocol Notes:
- Orchestrator ↔ Daemon: CBOR (matches Rust serde_cbor)
- Orchestrator ↔ Worker: msgpack (Python IPC, separate module)
"""

import asyncio
from pathlib import Path
from typing import Optional

import cbor2


class SidecarError(Exception):
    """Sidecar daemon communication error."""

    pass


class SidecarClient:
    """Async client for sidecar daemon communication.

    Maintains persistent Unix socket connection with HMAC authentication.
    """

    def __init__(
        self,
        socket_path: str | Path = "/run/sidecar/auth.sock",
        session_key_path: str | Path = "/run/sidecar/.session",
    ):
        """Initialize client (does not connect).

        Args:
            socket_path: Path to daemon Unix socket
            session_key_path: Path to session key file
        """
        self.socket_path = Path(socket_path)
        self.session_key_path = Path(session_key_path)
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.session_key: Optional[bytes] = None

    async def connect(self) -> None:
        """Connect to daemon and load session key.

        Raises:
            SidecarError: If connection fails
            FileNotFoundError: If socket or session key missing
        """
        # Load session key
        if not self.session_key_path.exists():
            raise FileNotFoundError(f"Session key not found: {self.session_key_path}")

        self.session_key = self.session_key_path.read_bytes()
        if len(self.session_key) != 32:
            raise SidecarError(f"Invalid session key length: {len(self.session_key)}")

        # Connect to Unix socket
        try:
            self.reader, self.writer = await asyncio.open_unix_connection(
                str(self.socket_path)
            )
        except (FileNotFoundError, ConnectionRefusedError) as e:
            raise SidecarError(f"Failed to connect to daemon: {e}") from e

    async def close(self) -> None:
        """Close connection to daemon."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    async def authorize_construct(
        self, frame_id: bytes, level: int, data_digest: bytes
    ) -> bytes:
        """Request authorization grant for SecureDataFrame construction.

        Args:
            frame_id: 16-byte UUID
            level: Security level (0-4)
            data_digest: 32-byte BLAKE3 digest of canonical payload

        Returns:
            16-byte grant ID

        Raises:
            SidecarError: If authorization fails
        """
        raise NotImplementedError("authorize_construct not yet implemented")

    async def redeem_grant(self, grant_id: bytes) -> tuple[bytes, bytes, int]:
        """Redeem grant for seal.

        Args:
            grant_id: 16-byte grant handle

        Returns:
            (construction_ticket, seal, audit_id)

        Raises:
            SidecarError: If redemption fails
        """
        raise NotImplementedError("redeem_grant not yet implemented")

    async def consume_construction_ticket(self, ticket: bytes) -> None:
        """Consume construction ticket prior to SecureDataFrame instantiation."""
        raise NotImplementedError("consume_construction_ticket not yet implemented")

    async def compute_seal(
        self, frame_id: bytes, level: int, data_digest: bytes
    ) -> tuple[bytes, int]:
        """Compute seal for existing frame.

        Args:
            frame_id: 16-byte UUID
            level: Security level
            data_digest: 32-byte digest reflecting current payload

        Returns:
            (seal, audit_id) tuple

        Raises:
            SidecarError: If computation fails
        """
        raise NotImplementedError("compute_seal not yet implemented")

    async def verify_seal(
        self, frame_id: bytes, level: int, data_digest: bytes, seal: bytes
    ) -> tuple[bool, int]:
        """Verify seal integrity.

        Args:
            frame_id: 16-byte UUID
            level: Security level
            data_digest: Digest of payload being verified
            seal: 32-byte seal

        Returns:
            (valid, audit_id) tuple

        Raises:
            SidecarError: If verification request fails
        """
        raise NotImplementedError("verify_seal not yet implemented")
```

**Step 4: Add cbor2 to requirements**

```bash
# NOTE: This will be added to requirements-dev.lock later via pip-compile
echo "cbor2>=5.4.0" >> requirements-dev.in
```

**Step 5: Run test to verify it passes**

```bash
python -m pytest tests/orchestrator/test_sidecar_client.py -v
```

**Expected Output:**
```
test_sidecar_client_not_implemented PASSED
```

**Step 6: Commit**

```bash
git add src/elspeth/orchestrator/sidecar_client.py tests/orchestrator/test_sidecar_client.py requirements-dev.in
git commit -m "feat(sidecar): implement Python SidecarClient skeleton

- SidecarClient with connect(), authorize_construct(), redeem_grant()
- HMAC authentication placeholders
- Unix socket connection via asyncio
- NotImplementedError stubs for methods
- 1 passing test (skeleton verification)"
```

---

### Task 3.2: Issue and Enforce Construction Tickets

**Goal:** Replace raw `_CONSTRUCTION_TOKEN` usage with opaque construction tickets that only the daemon can mint and validate.

**Rust Side (Daemon):**
- Extend `Grant` struct to include a `construction_ticket: [u8; 32]` generated via `SystemRandom`.
- Update `GrantTable::redeem` to return both the original `GrantRequest` and the ticket.
- Store the ticket in a new `ConstructionTicketTable` (DashMap) that tracks single-use status.
- Update `protocol::Response::RedeemGrantReply` to include `construction_ticket` (already reflected in the enum above) and adjust serialization tests accordingly.
- Add new request variant `consume_construction_ticket` that the orchestrator calls right before object instantiation; the daemon verifies `ticket` is unused, marks it consumed, and replies with `ok`. This replaces the need to hand raw secrets to Python.
- Write tests ensuring tickets are one-shot, expire if not consumed within TTL, and cannot be guessed.

**Python Side (Orchestrator Client):**
- Implement `SidecarClient.consume_construction_ticket(ticket: bytes) -> None` which sends the new request type.
- Ensure tickets are never logged and are zeroed out in memory after consumption if practical.

**Documentation:** Update plan/runbook to describe tickets as the only way to construct frames.

---

### Task 3.3: Rewrite SecureDataFrame Creation Pipeline

**Files:**
- Update: `src/elspeth/core/security/secure_data.py`
- Add: `src/elspeth/orchestrator/secure_frame_factory.py`
- Update: associated tests under `tests/security/`

**Steps:**
1. **Remove legacy secrets**
   - Delete `_create_secure_factories()` and module-level `_get_construction_token` / `_compute_seal` exports.
   - Strip `_token` parameter from `SecureDataFrame.__new__`; replace with `_capability: ConstructionCapability`.
2. **ConstructionCapability abstraction**
   - Create `ConstructionCapability` object that wraps a construction ticket and a reference to the orchestrator’s `SidecarClient`.
   - Its `.consume()` method calls `consume_construction_ticket` and returns the seal used for instance initialization.
3. **New factory module**
   - Implement `secure_frame_factory.SecureFrameFactory` that orchestrator code uses to:
     - Call `authorize_construct` / `redeem_grant` to obtain `(ticket, seal, audit_id)`.
     - Build `ConstructionCapability` and invoke `SecureDataFrame._from_sidecar(capability, data, level, seal)`.
4. **SecureDataFrame integration**
   - Add `_from_sidecar` classmethod that:
     - Validates seal via daemon (using `SidecarClient.verify_seal`) before instantiation.
     - Calls `capability.consume()` to mark ticket used.
     - Sets `_seal` with daemon-provided bytes.
   - Harden `SecureDataFrame.__new__` so that it requires a `ConstructionCapability`, re-validates the MAC/nonce with the sidecar before object allocation, and rejects any capability that cannot be confirmed by the daemon.
   - Update `create_from_datasource`, `with_uplifted_security_level`, and `with_new_data` to delegate through the new factory (no direct daemon calls from plugin context).
5. **Testing**
   - Adapt existing tests to use a stub `SidecarClient` that emulates ticket issuance/consumption.
   - Add regression test ensuring plugins cannot call `_from_sidecar` without a valid capability (simulate by passing a fake capability and asserting `SecurityValidationError`).
6. **Docs**
   - Update ADRs and README snippets to describe the new ticket-based flow.

**Commit Example:**
```bash
git add src/elspeth/core/security/secure_data.py src/elspeth/orchestrator/secure_frame_factory.py tests/security
git commit -m "feat(security): gate SecureDataFrame construction on daemon-issued tickets"
```

---

### Task 3.4: Implement Canonical Digest Computation Pipeline

**Goal:** Implement the deterministic digest computation pipeline that produces BLAKE3 hashes of canonical Parquet representations, as specified in the v3 design.

**Files:**
- Create: `src/elspeth/core/security/digest.py`
- Create: `tests/security/test_digest_canonicalization.py`

**Step 1: Write failing test for digest determinism**

Create `tests/security/test_digest_canonicalization.py`:

```python
"""Tests for canonical digest computation."""

import pandas as pd
import pytest

from elspeth.core.security.digest import compute_canonical_digest


def test_digest_determinism_identical_frames():
    """Identical DataFrames produce identical digests."""
    df1 = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
    df2 = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

    digest1 = compute_canonical_digest(df1)
    digest2 = compute_canonical_digest(df2)

    assert digest1 == digest2
    assert len(digest1) == 32  # BLAKE3 produces 32-byte digests


def test_digest_determinism_reordered_columns():
    """Column order doesn't affect digest (sorted during canonicalization)."""
    df1 = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    df2 = pd.DataFrame({"b": [3, 4], "a": [1, 2]})

    digest1 = compute_canonical_digest(df1)
    digest2 = compute_canonical_digest(df2)

    assert digest1 == digest2


def test_digest_changes_on_data_mutation():
    """Digest changes when data is mutated."""
    df = pd.DataFrame({"col": [1, 2, 3]})
    digest1 = compute_canonical_digest(df)

    df.loc[0, "col"] = 999
    digest2 = compute_canonical_digest(df)

    assert digest1 != digest2


def test_digest_fails_on_unsupported_dtype():
    """Unsupported dtypes raise SecurityValidationError with clear message."""
    from elspeth.core.validation.base import SecurityValidationError

    # Create DataFrame with unsupported complex dtype
    df = pd.DataFrame({"complex": [complex(1, 2), complex(3, 4)]})

    with pytest.raises(SecurityValidationError, match="complex"):
        compute_canonical_digest(df)


def test_stable_sort_key_heterogeneous_labels():
    """_stable_sort_key handles mixed-type column names."""
    from elspeth.core.security.digest import _stable_sort_key

    # Mixed int/string labels
    labels = [1, "a", 2, "b"]
    sorted_labels = sorted(labels, key=_stable_sort_key)

    # Should produce consistent ordering (type name first, then value)
    assert sorted_labels == [1, 2, "a", "b"]
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/security/test_digest_canonicalization.py -v
```

**Expected Output:**
```
ModuleNotFoundError: No module named 'elspeth.core.security.digest'
```

**Step 3: Implement digest computation pipeline**

Create `src/elspeth/core/security/digest.py`:

```python
"""Canonical digest computation for SecureDataFrame.

Produces deterministic BLAKE3 digests of DataFrame payloads by:
1. Sorting rows and columns with stable ordering
2. Converting unsupported dtypes to Arrow-compatible representations
3. Streaming Parquet bytes directly into BLAKE3 hasher (zero-copy)
"""

import pandas as pd
from blake3 import blake3
from typing import Hashable

from elspeth.core.validation.base import SecurityValidationError


# Arrow-compatible dtypes that can be serialized deterministically
_SUPPORTED_ARROW_DTYPES = {
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float32", "float64",
    "bool",
    "object",  # Strings
    "datetime64[ns]",
    "timedelta64[ns]",
    "category",
}


def compute_canonical_digest(df: pd.DataFrame) -> bytes:
    """Compute BLAKE3 digest over canonical Parquet representation.

    Args:
        df: DataFrame to digest

    Returns:
        32-byte BLAKE3 digest

    Raises:
        SecurityValidationError: If DataFrame contains unsupported dtypes
    """
    hasher = blake3()
    sink = _Blake3Sink(hasher)

    try:
        # Sort rows and columns deterministically
        canonical_df = (
            df.sort_index(axis=0, key=_stable_sort_key)
            .sort_index(axis=1, key=_stable_sort_key)
        )

        # Convert unsupported dtypes to Arrow-compatible representations
        canonical_df = _as_type_safe(canonical_df)

        # Stream Parquet bytes into BLAKE3 hasher
        canonical_df.to_parquet(
            sink,
            engine="pyarrow",
            compression=None,
            index=True,
            coerce_timestamps="us",
            use_deprecated_int96_timestamps=False,
        )

    except Exception as e:
        raise SecurityValidationError(
            f"Failed to compute canonical digest: {e}"
        ) from e

    return hasher.digest()


def _stable_sort_key(label: Hashable) -> tuple:
    """Return total-orderable key for heterogeneous labels.

    Enables sorting of mixed-type column/index names (e.g., [1, "a", 2, "b"])
    by grouping by type first, then value.

    Args:
        label: Column or index label

    Returns:
        Tuple of (type_name, stringified_value)
    """
    from pathlib import Path
    from enum import Enum

    return (
        type(label).__name__,
        str(label) if isinstance(label, (Enum, Path)) else label,
    )


def _as_type_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Map unsupported dtypes into deterministic Arrow-friendly encodings.

    Args:
        df: DataFrame with potentially unsupported dtypes

    Returns:
        DataFrame with all columns using Arrow-compatible dtypes

    Raises:
        SecurityValidationError: If dtype cannot be safely converted
    """
    converted = {}

    for name, series in df.items():
        dtype_str = str(series.dtype)

        if any(supported in dtype_str for supported in _SUPPORTED_ARROW_DTYPES):
            converted[name] = series
        else:
            # Attempt string canonicalization for unsupported types
            try:
                converted[name] = series.astype(str)
            except Exception as e:
                raise SecurityValidationError(
                    f"Column '{name}' has unsupported dtype '{dtype_str}' "
                    f"that cannot be canonicalized. Error: {e}"
                ) from e

    return pd.DataFrame(converted, index=df.index)


class _Blake3Sink:
    """PyArrow writeable sink that streams bytes into a BLAKE3 hasher.

    Implements the minimal interface required by PyArrow's to_parquet().
    Enables zero-copy hashing by streaming Parquet bytes directly into
    the hasher without intermediate BytesIO allocation.
    """

    def __init__(self, hasher: blake3):
        """Initialize sink with BLAKE3 hasher.

        Args:
            hasher: BLAKE3 hasher instance
        """
        self._hasher = hasher

    def write(self, data: bytes) -> None:
        """Write bytes to hasher (PyArrow-compatible sink API).

        Args:
            data: Parquet bytes chunk
        """
        self._hasher.update(data)

    def close(self) -> None:
        """Close sink (no-op, hasher remains usable)."""
        pass
```

**Step 4: Add blake3 dependency**

```bash
# Add to requirements-dev.in
echo "blake3>=0.3.0" >> requirements-dev.in

# Compile lockfile (run later as part of bootstrap)
# python -m pip install pip-tools
# pip-compile requirements-dev.in --generate-hashes --output-file requirements-dev.lock
```

**Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/security/test_digest_canonicalization.py -v
```

**Expected Output:**
```
test_digest_determinism_identical_frames PASSED
test_digest_determinism_reordered_columns PASSED
test_digest_changes_on_data_mutation PASSED
test_digest_fails_on_unsupported_dtype PASSED
test_stable_sort_key_heterogeneous_labels PASSED

5 passed in 0.23s
```

**Step 6: Performance benchmark (optional but recommended)**

Add performance test to verify digest computation scales:

```python
def test_digest_performance_wide_frame():
    """Benchmark digest computation on wide DataFrame."""
    import timeit

    # Wide frame: 100 columns × 1000 rows
    df = pd.DataFrame({f"col_{i}": range(1000) for i in range(100)})

    time_seconds = timeit.timeit(
        lambda: compute_canonical_digest(df),
        number=10,
    )
    avg_ms = (time_seconds / 10) * 1000

    print(f"\n📊 Wide frame digest: {avg_ms:.2f}ms per digest")
    assert avg_ms < 100, f"Digest too slow: {avg_ms:.2f}ms"


def test_digest_performance_tall_frame():
    """Benchmark digest computation on tall DataFrame."""
    import timeit

    # Tall frame: 10 columns × 10,000 rows
    df = pd.DataFrame({f"col_{i}": range(10000) for i in range(10)})

    time_seconds = timeit.timeit(
        lambda: compute_canonical_digest(df),
        number=10,
    )
    avg_ms = (time_seconds / 10) * 1000

    print(f"\n📊 Tall frame digest: {avg_ms:.2f}ms per digest")
    assert avg_ms < 100, f"Digest too slow: {avg_ms:.2f}ms"
```

**Step 7: Integration with SidecarClient**

Update `sidecar_client.py` methods to use `compute_canonical_digest`:

```python
from elspeth.core.security.digest import compute_canonical_digest

async def authorize_construct(
    self, frame_id: bytes, level: int, df: pd.DataFrame
) -> bytes:
    """Request authorization grant for SecureDataFrame construction."""
    data_digest = compute_canonical_digest(df)
    # ... send AuthorizeConstruct with (frame_id, level, data_digest)
```

**Step 8: Commit**

```bash
git add src/elspeth/core/security/digest.py tests/security/test_digest_canonicalization.py requirements-dev.in
git commit -m "feat(security): implement canonical digest computation pipeline

- compute_canonical_digest() with BLAKE3 streaming
- _stable_sort_key() for heterogeneous column/index labels
- _as_type_safe() with dtype conversion and error handling
- _Blake3Sink for zero-copy PyArrow → BLAKE3 streaming
- 5+ passing tests for determinism, mutations, errors
- Performance benchmarks for wide/tall DataFrames"
```

**Estimated Time:** 3-4 hours

**Security Properties:**
- ✅ Deterministic: Same DataFrame → same digest (sorted rows/columns)
- ✅ Tamper-evident: Any data mutation changes digest
- ✅ Fail-safe: Unsupported dtypes raise clear errors
- ✅ Performance: Zero-copy streaming keeps memory flat

---

## Summary and Next Steps

**Plan complete and saved to `docs/plans/2025-10-29-sidecar-implementation.md`.**

This plan provides:

1. **Phase 0: System Tasks (for John)**
   - Install Rust toolchain via rustup
   - Verify Docker multi-stage build capability
   - Optional development tools (cargo-watch, rust-analyzer)

2. **Phase 1: Rust Daemon Foundation (6 tasks)**
   - ✅ Project structure (Cargo.toml, src/main.rs, src/lib.rs)
   - ✅ Crypto module (Secrets, BLAKE2s MAC seals)
   - ✅ Grant table (one-shot handles with TTL)
   - ✅ CBOR protocol messages
   - ✅ Config loading from TOML
   - ✅ Unix socket server skeleton

3. **Phase 2: Complete Rust Implementation (work in progress)**
   - Mutual-auth enforcement (HMAC validation, SO_PEERCRED, session key helper from Task 2.3)
   - Request dispatch table (authorize, redeem, consume_ticket, compute, verify)
   - Registered frame cache + background cleanup
   - Error handling, structured logging, benchmarks, integration tests

4. **Phase 3: Python Integration (upcoming)**
   - Plugin worker isolation under `appplugin` UID
   - Orchestrator-only SidecarClient + ticket consumption API
   - Canonical digest computation pipeline (BLAKE3 + Parquet streaming)
   - Ticket-backed SecureDataFrame factory rewrite (`_from_sidecar`, ConstructionCapability)
   - SecureFrameProxy + orchestrator ↔ worker RPC plumbing
   - Standalone mode guardrails and integration tests

5. **Phase 4: Docker Deployment**
   - Multi-stage build, supervisord updates, user setup, health checks, container tests

**Total Tasks:** updated dynamically (6 completed in Phase 1, remaining work tracked per phase above)

**Estimated Timeline:**
- Phase 0: 30 minutes (John, system setup)
- Phase 1: 4-6 hours (Rust foundation) - **6 tasks complete**
- Phase 2: 6-8 hours (Rust completion)
- Phase 3: 11-14 hours (Python integration, includes Task 3.4 digest pipeline)
- Phase 4: 4-6 hours (Docker deployment)

**Total: 25-34 hours** (3-4 days of focused work)

---

`★ Insight ─────────────────────────────────────`

**Test-Driven Security Development:** This plan follows strict TDD discipline (RED → GREEN → REFACTOR) for security-critical code. Each Rust component has tests written BEFORE implementation, ensuring:

1. **Seal forgery prevention** is validated by tests that attempt forgery and expect failure
2. **Grant lifecycle** (authorize → redeem → expire) is tested for all edge cases
3. **HMAC authentication** tests verify both success and failure paths
4. **Constant-time operations** use ring's verified implementations

**Why TDD matters for security:** Writing tests first forces us to think about attack vectors before implementing defenses. The test suite becomes a regression safety net - if future changes break security properties, tests fail immediately.

**Rust memory safety** eliminates entire vulnerability classes (buffer overflows, use-after-free) that plague C/C++ security code, while `ring` provides FIPS-validated cryptographic primitives.

`─────────────────────────────────────────────────`

---

## V3 Design Security Enhancements (2025-10-29)

**This implementation plan incorporates critical security upgrades from the v3 design iteration:**

### 1. Digest-Bound Seals

**Problem:** Original design bound seals only to `(frame_id, level)`. An attacker could swap DataFrame contents after construction without invalidating the seal.

**Solution:** Every seal operation includes `data_digest = BLAKE3(canonical_parquet_bytes)`:
```rust
seal = HMAC-BLAKE2s(_SEAL_KEY, frame_id || level || data_digest)
```

**Implementation Impact:**
- Rust crypto module computes seals over 3 components (not 2)
- Python orchestrator computes BLAKE3 digest on every frame mutation
- Protocol messages include `data_digest: bytes[32]` field
- Dependencies: Add `blake3` crate (Rust) and `blake3` package (Python)

### 2. Stable Frame Identifiers

**Problem:** Using Python `id()` pointers as frame identifiers creates reuse vulnerabilities after garbage collection.

**Solution:** Orchestrator generates stable 128-bit UUIDs via `uuid.uuid4()` and maintains FrameRegistry:
```python
frame_registry: Dict[UUID, FrameRegistryEntry] = {}
# FrameRegistryEntry = {frame, digest, level, created_at}
```

**Implementation Impact:**
- Daemon stores `RegisteredFrameTable: DashMap<Uuid, (level, digest)>`
- Grant redemption inserts into RegisteredFrameTable
- `ComputeSeal`/`VerifySeal` reject unknown frame_ids
- Dependencies: Add `uuid` crate with "v4" feature

### 3. FD_CLOEXEC Descriptor Hygiene

**Problem:** Plugin workers spawned via `fork()` inherit file descriptors, potentially leaking authenticated sidecar socket handles.

**Solution:**
- All Unix sockets opened with `O_CLOEXEC` flag
- Session key file opened with `FD_CLOEXEC` via `fcntl()`
- Orchestrator establishes sidecar connection AFTER spawning workers
- Or use `socketpair()` + explicit close in child process

**Implementation Impact:**
- Rust: Use `OFlag::O_CLOEXEC` when binding Unix sockets
- Python: Set `FD_CLOEXEC` on session key file descriptor
- Docker: Supervisord spawns processes in correct order (daemon → orchestrator → workers)

### 4. Protocol Message Updates

**Old Protocol:**
```rust
AuthorizeConstruct { data_id: u64, level: u32 }
ComputeSeal { data_id: u64, level: u32 }
VerifySeal { data_id: u64, level: u32, seal: [u8; 32] }
```

**New Protocol (v3):**
```rust
AuthorizeConstruct { frame_id: [u8; 16], level: u32, data_digest: [u8; 32] }
ComputeSeal { frame_id: [u8; 16], level: u32, data_digest: [u8; 32] }
VerifySeal { frame_id: [u8; 16], level: u32, data_digest: [u8; 32], seal: [u8; 32] }
```

**Implementation Impact:**
- All protocol messages use UUID frame_ids (not u64 pointers)
- Every seal operation includes digest parameter
- Grant state stores `(frame_id, level, digest)` tuple
- CBOR serialization handles 16-byte arrays natively

### Security Properties Gained

✅ **Post-creation tampering prevention:** Data swaps invalidate seals
✅ **Frame ID stability:** No pointer reuse vulnerabilities
✅ **Descriptor isolation:** Workers cannot inherit authenticated handles
✅ **Audit traceability:** Stable UUIDs enable long-term log correlation

**Estimated Additional Work:** +2-3 hours (mostly Python FrameRegistry and digest computation)

---

## Execution Options

**Two execution approaches:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration with quality gates

**2. Parallel Session (separate)** - Open new session with executing-plans skill, batch execution with checkpoints

**Which approach would you prefer?**
