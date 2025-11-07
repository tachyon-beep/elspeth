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
