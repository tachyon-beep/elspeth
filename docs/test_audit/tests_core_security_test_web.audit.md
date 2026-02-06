# Test Audit: tests/core/security/test_web.py

**Lines:** 99
**Test count:** 9
**Audit status:** ISSUES_FOUND

## Summary

This is a concise test suite for SSRF prevention functionality covering URL scheme validation and IP validation. While the tests cover the core happy paths and error cases, there are notable coverage gaps for additional private IP ranges and IPv6 scenarios. The tests use mocking appropriately to control DNS resolution behavior.

## Findings

### 🟡 Warning

1. **Lines 59-65: Missing private IP range coverage** - Only Class A private IPs (10.0.0.0/8) are tested. Missing tests for:
   - Class B private (172.16.0.0/12)
   - Class C private (192.168.0.0/16)
   - Link-local (169.254.0.0/16, excluding metadata endpoint which is tested)

   If the implementation has bugs for these ranges, they would go undetected.

2. **Lines 43-56: No IPv6 SSRF tests** - The suite only tests IPv4 addresses. Missing tests for:
   - IPv6 loopback (::1)
   - IPv6 private ranges (fc00::/7, fe80::/10)
   - IPv6-mapped IPv4 addresses (::ffff:127.0.0.1) which can bypass IPv4 checks

   These are common SSRF bypass vectors.

3. **Lines 77-90: Timeout test uses real sleep** - The `slow_dns` mock sleeps for 10 seconds but timeout is set to 0.1s. While this works, the test may be slower than necessary if the timeout mechanism has issues. Consider verifying the actual duration doesn't exceed expected bounds.

### 🔵 Info

1. **Lines 19-34: Scheme validation tests** - Good coverage of allowed (HTTP, HTTPS) and blocked (file, ftp) schemes. Could consider adding tests for other dangerous schemes like `gopher://`, `dict://`, or `data:` URLs if the implementation should block them.

2. **Lines 93-99: DNS failure handling** - Correctly tests that DNS resolution failures are wrapped as `NetworkError` rather than leaking raw socket exceptions.

## Verdict

**KEEP** - The core functionality is tested, but recommend adding tests for additional private IP ranges and IPv6 SSRF bypass scenarios to strengthen security coverage.
