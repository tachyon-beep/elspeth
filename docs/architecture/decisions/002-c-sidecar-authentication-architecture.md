# ADR-002-C: Sidecar Authentication and Authorization Architecture

## Status

**Accepted** (2025-10-30)

**Implementation Status**: Complete
- HMAC-SHA256 authentication implemented (sidecar/src/protocol.rs, server.rs)
- Capability-based grant system implemented (sidecar/src/grants.rs)
- Construction ticket validation implemented (CVE-ADR-002-A-010 fixed in commit f4d5e1d)
- Authentication failure metrics implemented (commit a56da72)

**Related Documents**:
- [ADR-002: Multi-Level Security Enforcement](002-security-architecture.md) – Parent ADR for MLS architecture
- [ADR-002-A: Trusted Container Model](002-security-architecture.md#trusted-container-model) – SecureDataFrame immutability
- [sidecar/SECURITY.md](../../../sidecar/SECURITY.md) – Comprehensive security documentation
- [CVE-ADR-002-A-009](002-security-architecture.md#cve-adr-002-a-009) – Python introspection attack mitigation
- [CVE-ADR-002-A-010](002-security-architecture.md#cve-adr-002-a-010) – Construction ticket forgery fix

---

## Context

### Problem Statement

The sidecar security daemon (ADR-002 implementation detail) isolates secrets (construction_token, seal_key) in a separate Rust process to prevent Python introspection attacks (CVE-ADR-002-A-009). This creates a fundamental authentication and authorization challenge:

**How do we secure inter-process communication between the Python orchestrator and Rust daemon while preventing:**
1. **Request tampering** – Malicious plugins modifying IPC messages
2. **Replay attacks** – Re-using captured requests to bypass authorization
3. **Ticket forgery** – Creating fake construction tickets to bypass grant flow
4. **Timing side-channels** – Extracting secrets through authentication timing analysis

Traditional approaches like session tokens with timestamp-based replay protection have limitations in this threat model.

### Threat Model

**Attacker Capabilities**:
- Full Python introspection access (can inspect any Python object via `__dict__`, `gc.get_objects()`, debugger hooks)
- Can read session key file (`/var/lib/sidecar/session.key`, mode 0640, readable by orchestrator group)
- Can connect to Unix socket (if UID 1000/appuser)
- **Cannot** access secrets in Rust process (OS process boundary prevents introspection)
- **Cannot** connect as plugin worker (UID 1002 lacks socket permissions)

**Attack Vectors**:
1. Malicious plugin captures valid HMAC-authenticated request, replays it to daemon
2. Plugin with session key forges request by computing valid HMAC for arbitrary operation
3. Plugin forges construction ticket (32 random bytes) to bypass authorize→redeem flow
4. Timing analysis on HMAC verification reveals session key bits

**Security Goals**:
1. Prevent request tampering (integrity)
2. Prevent meaningful replay attacks (freshness with acceptable window)
3. Prevent ticket forgery (authenticity)
4. Prevent timing side-channels (constant-time operations)
5. Enable operational monitoring (authentication failure metrics)

---

## Decision

### Authentication: HMAC-SHA256

**Implementation**: Request authentication via HMAC-SHA256 keyed message authentication codes.

**Rationale**:
- **Integrity**: Attackers without the session key cannot modify requests (tampering detected immediately)
- **Constant-Time**: `ring::hmac::verify()` uses constant-time comparison preventing timing attacks
- **Standard Algorithm**: HMAC-SHA256 is NIST-approved (FIPS 198-1), widely audited, well-understood
- **Performance**: ~1μs per verification on modern CPUs (negligible overhead for IPC operations)

**Security Property**:
> Without the session key, an attacker cannot create valid HMACs. Even with full knowledge of valid request/HMAC pairs, computing a HMAC for a new request requires the 256-bit session key (2^256 brute-force security).

**Alternative Considered: Mutual TLS**
- **Rejected**: Requires certificate management infrastructure (PKI, rotation, revocation)
- **Complexity**: mTLS adds ~500 LOC for cert handling vs. ~50 LOC for HMAC
- **Performance**: TLS handshake costs ~5-10ms vs. <1μs for HMAC
- **Verdict**: HMAC provides equivalent security with dramatically simpler implementation

### Authorization: Capability-Based Grants

**Implementation**: One-shot grant system with time-bound authorization tokens.

**Grant Lifecycle**:
```
1. authorize_construct(frame_id, level, data_digest)
   → daemon issues: (grant_id: 16 bytes random, expires_at: now + 30s)

2. redeem_grant(grant_id)
   → daemon consumes grant (one-shot), returns:
      - construction_ticket: 32 bytes random
      - initial_seal: 32 bytes BLAKE2s-MAC
   → daemon records ticket in issued_tickets map

3. consume_construction_ticket(ticket)
   → daemon validates: ticket ∈ issued_tickets
   → daemon marks consumed (one-shot)
   → daemon removes from issued_tickets
```

**Security Properties**:
1. **Unforgeable**: Grant IDs and tickets are cryptographically random (ring::SystemRandom)
2. **One-Shot**: Grants can only be redeemed once, tickets can only be consumed once
3. **Time-Bound**: Grants expire after 30 seconds (prevents long-lived credentials)
4. **Provenance**: Tickets must be issued by daemon (prevents forgery - CVE-ADR-002-A-010)

**Why Not Timestamp-Based Replay Protection?**

Traditional replay protection tracks seen request IDs + timestamps, rejecting duplicates within a time window. This approach is **unnecessary** given the capability model:

**Replay Attack Analysis**:

| Scenario | Traditional Auth | Capability-Based Grant |
|----------|------------------|------------------------|
| **Attacker replays `authorize_construct`** | If timestamp fresh, succeeds → security breach | Succeeds but returns **different** grant_id (random) → original client unaffected → no security impact |
| **Attacker replays `redeem_grant`** | If timestamp fresh, succeeds → security breach | Fails: grant already redeemed (one-shot) → security preserved |
| **Attacker replays `consume_ticket`** | If timestamp fresh, succeeds → security breach | Fails: ticket already consumed (one-shot) → security preserved |

**Key Insight**:
> Because each `authorize_construct()` returns a **unique random grant_id**, replaying the authorization request doesn't compromise the original client's grant. The attacker gets their own independent grant (which they could have obtained directly anyway). This is fundamentally different from session token replay where replaying steals the victim's authentication.

**Attack Window**:
- Duration: 30 seconds (grant TTL)
- Impact: Denial of service to one frame creation (attacker redeems victim's grant before victim does)
- **NOT** privilege escalation (attacker cannot access victim's frame_id or data)

**Verdict**: One-shot grants with TTL provide equivalent security to timestamp-based replay protection with simpler implementation (no timestamp validation, no request ID tracking).

**Alternative Considered: Nonce-Based Challenge-Response**
- Client requests nonce from daemon
- Client includes nonce in next request
- Daemon validates nonce hasn't been used

**Rejected**:
- Requires stateful nonce tracking (memory/performance overhead)
- Two round trips per operation (latency penalty)
- Nonce expiry requires garbage collection (complexity)
- **Verdict**: Capability grants already provide one-shot semantics; adding nonces is redundant

---

## Implementation Details

### HMAC Request Canonicalization

**Challenge**: CBOR serialization is not canonically unique (map key ordering, integer encoding choices).

**Solution**: Explicit canonicalization function per request type (protocol.rs:canonical_bytes_without_auth).

**Example (authorize_construct)**:
```rust
// Canonicalize as: (frame_id: [u8; 16], level: u32, data_digest: [u8; 32])
canonical = (request.frame_id, request.level, request.data_digest);
canonical_bytes = cbor2::dumps(canonical);  // Deterministic tuple encoding
```

**Security Property**: Same request always produces same canonical bytes → HMAC verification is deterministic.

**Attack Prevention**: Attacker cannot create two different requests with same HMAC by exploiting CBOR encoding flexibility.

### Ticket Forgery Prevention (CVE-ADR-002-A-010)

**Original Vulnerability** (commit f4d5e1d):
- `ConstructionTicketTable` only tracked **consumed** tickets
- Daemon accepted any previously unseen 32-byte value as valid ticket
- Attacker could forge ticket = random_bytes(32) → bypass authorize→redeem flow

**Fix**:
- Added `issued_tickets: DashMap<[u8; 32], Instant>` to track tickets created during grant redemption
- Modified `consume()` to validate ticket ∈ issued_tickets (prevents forgery)
- Added `issue()` method called in `handle_redeem_grant()` to record tickets

**Dual-Map Validation**:
```rust
pub async fn consume(&self, ticket: &[u8; 32]) -> Result<(), String> {
    // Phase 1: Authenticity - was ticket issued by daemon?
    if !self.issued_tickets.contains_key(ticket) {
        return Err("never issued");
    }

    // Phase 2: Freshness - was ticket already consumed?
    if self.consumed_tickets.contains_key(ticket) {
        return Err("already consumed");
    }

    // Mark consumed, remove from issued set
    self.consumed_tickets.insert(*ticket, expires_at);
    self.issued_tickets.remove(ticket);
    Ok(())
}
```

**Security Property**: Only tickets generated by daemon during grant redemption can be consumed.

### Constant-Time Operations

**HMAC Verification** (server.rs:258):
```rust
match ring::hmac::verify(&key, &canonical_bytes, provided_auth) {
    Ok(()) => Ok(true),
    Err(_) => {
        self.auth_failures.fetch_add(1, Ordering::Relaxed);
        Ok(false)
    }
}
```

**Security Property**: `ring::hmac::verify()` uses constant-time byte comparison → prevents timing side-channels.

**Seal Comparison** (crypto.rs):
- BLAKE2s-MAC verification uses constant-time comparison internally
- Prevents timing analysis revealing seal_key bits

---

## Operational Monitoring

### Authentication Failure Metrics

**Metric**: `auth_failures: Arc<AtomicU64>` exposed in health check response.

**Purpose**: Detect misconfigured clients or active attacks.

**Monitoring Thresholds**:
- **Normal**: 0-2 failures during startup (daemon initialization race)
- **Warning**: 5+ failures/minute (potential misconfiguration - check session key paths)
- **Critical**: 50+ failures/minute (potential active attack - investigate logs, consider key rotation)

**Response Actions**:
1. Check client logs for session key path mismatches
2. Verify session key file permissions (`ls -l /var/lib/sidecar/session.key`)
3. Inspect daemon logs for UID validation failures
4. Review recent configuration changes
5. Consider rotating session key if compromise suspected

**Logging Example** (server.rs:203):
```rust
warn!(
    "HMAC validation failed for request type: {:?}",
    std::mem::discriminant(&request)
);
```

**Security Property**: Failed authentications are logged and counted without revealing session key or request contents.

---

## Security Analysis

### Attack Resistance

| Attack | Mitigation | Effectiveness |
|--------|------------|---------------|
| **Request tampering** | HMAC-SHA256 integrity | ✅ Cryptographically secure (2^128 collision resistance) |
| **Replay attacks** | One-shot grants + 30s TTL | ✅ Replay impact: DOS to one frame creation (low severity) |
| **Ticket forgery** | Issued ticket validation | ✅ Only daemon-generated tickets accepted |
| **Timing side-channels** | Constant-time HMAC verify | ✅ `ring::hmac::verify()` prevents timing analysis |
| **Session key theft** | Unix socket permissions 0600, session key 0640 | ⚠️ Orchestrator can read session key (design requirement) |
| **Denial of service** | Grant TTL expiry, Unix socket backlog | ⚠️ Mitigated but not eliminated (out of scope) |

### Design Trade-offs

**Accepted Risk: Orchestrator Access to Session Key**

The orchestrator (UID 1000) can read the session key (`/var/lib/sidecar/session.key`, mode 0640). This is **intentional** and **required** for HMAC computation.

**Threat Model Boundary**:
- If orchestrator is compromised (attacker has UID 1000), the session key is accessible
- **However**: Secrets (construction_token, seal_key) remain isolated in Rust process
- Attacker with session key can forge authenticated requests BUT cannot directly read secrets from Rust process memory

**Mitigation Layers**:
1. **Plugin Isolation**: Plugin workers (UID 1002) cannot access session key (different group)
2. **SO_PEERCRED Validation**: Daemon validates peer UID before processing requests
3. **Grant Authorization**: Even with valid HMAC, attacker must follow grant lifecycle
4. **Audit Logging**: All operations logged for forensic analysis (Phase 3 feature)

**Design Principle**: Session key compromise allows **request forgery** but not **secret disclosure**. This maintains the core security goal (CVE-ADR-002-A-009 mitigation).

---

## Alternatives Considered

### 1. Mutual TLS with Client Certificates

**Approach**: Use TLS with client cert authentication for Unix socket communication.

**Advantages**:
- Industry-standard authentication mechanism
- Supports certificate revocation (CRL/OCSP)
- Encryption + authentication in one protocol

**Disadvantages**:
- Requires PKI infrastructure (cert generation, storage, rotation)
- Certificate lifecycle management (renewal, revocation, expiry monitoring)
- ~500-1000 LOC implementation complexity vs. ~50 LOC for HMAC
- TLS handshake latency (~5-10ms vs. <1μs for HMAC)
- Over-engineered for localhost IPC (encryption unnecessary on Unix socket)

**Verdict**: **Rejected** – Complexity cost not justified for localhost IPC. HMAC provides equivalent authentication security with simpler implementation.

### 2. Shared Memory with Semaphore-Based Locking

**Approach**: Use POSIX shared memory for IPC, semaphores for access control.

**Advantages**:
- Zero-copy data transfer (highest performance)
- No serialization overhead

**Disadvantages**:
- No built-in authentication (must layer on top)
- Race condition risks (semaphore bugs → data corruption)
- Platform-specific (Linux vs. macOS differences)
- Difficult to audit (memory access patterns hard to log)
- Incompatible with containerized deployment (shared memory across containers)

**Verdict**: **Rejected** – Security auditability more important than performance optimization. Unix sockets provide sufficient performance (<100μs per request) with better isolation guarantees.

### 3. Timestamp-Based Replay Protection

**Approach**: Track request IDs + timestamps, reject duplicates within time window.

**Advantages**:
- Traditional authentication pattern (well-understood)
- Explicit replay protection mechanism

**Disadvantages**:
- Requires stateful tracking of seen requests (memory overhead, garbage collection)
- Clock synchronization dependency (orchestrator and daemon clocks must align)
- Doesn't prevent grant ID uniqueness issues (see Replay Attack Analysis above)
- Added complexity without security benefit (one-shot grants already prevent replay)

**Verdict**: **Rejected** – Capability-based grants provide equivalent replay protection through one-shot semantics. Adding timestamps would be redundant complexity.

### 4. JWT (JSON Web Tokens) for Authorization

**Approach**: Daemon issues JWTs with embedded claims (frame_id, level, expiry).

**Advantages**:
- Self-contained authorization (no server-side state)
- Standard format (RFC 7519)

**Disadvantages**:
- JSON serialization overhead vs. binary CBOR
- Cannot revoke before expiry (stateless design limitation)
- Larger token size (~200 bytes JWT vs. 16 bytes grant_id)
- Clock synchronization required (exp claim validation)
- Over-engineered for single-daemon architecture (JWTs shine in distributed systems)

**Verdict**: **Rejected** – Grant IDs with server-side validation provide equivalent functionality with smaller tokens and revocation capability (one-shot redemption).

---

## Compliance Mapping

### Australian ISM Controls

| ISM Control | Requirement | Implementation |
|-------------|-------------|----------------|
| **ISM-0380** | Access control based on valid clearances | SO_PEERCRED validates peer UID before processing requests |
| **ISM-1407** | Cryptographic key management | Session key stored with mode 0640, generated via ring::SystemRandom |
| **ISM-1552** | Authentication mechanisms | HMAC-SHA256 with constant-time verification |
| **ISM-1084** | Event logging and monitoring | Authentication failures logged and counted (auth_failures metric) |
| **ISM-1433** | Secure error handling | HMAC failures return generic errors without key material disclosure |

### NIST Compliance

- **FIPS 198-1**: HMAC-SHA256 algorithm (keyed-hash message authentication)
- **FIPS 140-2**: `ring` cryptography library provides validated implementations
- **NIST SP 800-57**: 256-bit symmetric keys (session key length)

---

## Future Enhancements

### Phase 3: Audit Logging

**Planned Enhancement**: Structured audit logs for all authentication events.

**Log Format** (JSONL):
```json
{
  "timestamp": "2025-10-30T14:23:45.123Z",
  "event": "auth_failure",
  "peer_uid": 1000,
  "request_type": "authorize_construct",
  "reason": "invalid_hmac",
  "session_key_hash": "sha256:abc123..."  // For key rotation correlation
}
```

**Benefits**:
- Forensic analysis of security incidents
- Automated alerting on suspicious patterns
- Compliance evidence for ISM-1084

### Potential: Session Key Rotation

**Design Consideration**: Support session key rotation without daemon restart.

**Approach**:
1. Daemon maintains `current_key` + `previous_key` (grace period for client updates)
2. Health check exposes `key_version` field
3. Clients detect version mismatch, reload session key from file
4. Old key expired after grace period (e.g., 5 minutes)

**Trade-off**: Adds complexity for marginal security benefit (session key compromise requires orchestrator compromise, which is already catastrophic). **Deferred** until specific compliance requirement emerges.

---

## References

- **HMAC Specification**: RFC 2104 - Keyed-Hashing for Message Authentication
- **Ring Cryptography Library**: https://github.com/briansmith/ring
- **Bell-LaPadula Model**: "Secure Computer System: Unified Exposition and Multics Interpretation" (1976)
- **Object-Capability Security**: Mark Miller, "Robust Composition: Towards a Unified Approach to Access Control and Concurrency Control" (2006)
- **ISM**: Australian Government Information Security Manual (2024 edition)
- **NIST FIPS 198-1**: The Keyed-Hash Message Authentication Code (HMAC)

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-10-27 | Use HMAC-SHA256 for authentication | Standard algorithm, constant-time, simple implementation |
| 2025-10-27 | Use capability-based grants | One-shot semantics eliminate need for timestamp replay protection |
| 2025-10-30 | Add ticket forgery prevention | CVE-ADR-002-A-010 fix - validate tickets were issued by daemon |
| 2025-10-30 | Add auth_failures metric | Operational visibility per security review recommendation |

---

**Last Updated**: 2025-10-30
**Author**: ELSPETH Security Architecture Team
**Status**: Accepted and Implemented
**Next Review**: 2026-04-30 (6 months)
