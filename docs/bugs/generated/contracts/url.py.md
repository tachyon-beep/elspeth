## Summary

`SanitizedWebhookUrl.__post_init__()` still accepts username-only and empty-password Basic Auth URLs, so a directly constructed `SanitizedWebhookUrl` can carry secrets into webhook artifact URIs.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/url.py`
- Line(s): `210-216`
- Function/Method: `SanitizedWebhookUrl.__post_init__`

## Evidence

`SanitizedWebhookUrl.__post_init__()` only rejects `parsed.password`:

```python
parsed = urlparse(self.sanitized_url)
if parsed.password:
    raise ValueError(...)
```

Source: [/home/john/elspeth/src/elspeth/contracts/url.py](/home/john/elspeth/src/elspeth/contracts/url.py#L210)

That misses two credential-bearing cases that `from_raw_url()` explicitly treats as sensitive:

```python
has_basic_auth = parsed.username is not None or parsed.password is not None
...
if has_basic_auth:
    # Remove both username and password
```

Source: [/home/john/elspeth/src/elspeth/contracts/url.py](/home/john/elspeth/src/elspeth/contracts/url.py#L293)

So the factory and the constructor disagree about what counts as unsanitized. I verified the constructor currently accepts both cases:

- `SanitizedWebhookUrl("https://token@example.com/hook", None)` succeeds
- `SanitizedWebhookUrl("https://token:@example.com/hook", None)` succeeds

Those instances then pass straight through `ArtifactDescriptor.for_webhook()`, which only checks `isinstance(url, SanitizedWebhookUrl)` before persisting `url.sanitized_url` into the artifact URI:

```python
if not isinstance(url, SanitizedWebhookUrl):
    raise TypeError(...)
...
path_or_uri=f"webhook://{url.sanitized_url}"
```

Source: [/home/john/elspeth/src/elspeth/contracts/results.py](/home/john/elspeth/src/elspeth/contracts/results.py#L443)

I confirmed this produces an audit-facing URI containing the token:
`webhook://https://token@example.com/hook`

Existing tests cover factory sanitization of username-only Basic Auth, not direct-constructor invariants:
[/home/john/elspeth/tests/unit/core/security/test_url.py](/home/john/elspeth/tests/unit/core/security/test_url.py#L257)
[/home/john/elspeth/tests/unit/core/security/test_url.py](/home/john/elspeth/tests/unit/core/security/test_url.py#L877)

## Root Cause Hypothesis

The previous hardening fix added constructor checks for password-bearing URLs and sensitive query/fragment params, but the invariant was implemented with `if parsed.password:` rather than the same `username is not None or password is not None` rule used by the sanitizer. That leaves username-only auth and empty-password auth outside the constructor guard.

## Suggested Fix

Make `SanitizedWebhookUrl.__post_init__()` reject any userinfo, not just truthy passwords.

Example shape:

```python
parsed = urlparse(self.sanitized_url)
if parsed.username is not None or parsed.password is not None:
    raise ValueError(
        "SanitizedWebhookUrl cannot contain Basic Auth credentials in the URL. "
        "Use SanitizedWebhookUrl.from_raw_url() to sanitize first."
    )
```

Add regression tests for direct construction with:

- `https://token@example.com/hook`
- `https://token:@example.com/hook`

## Impact

A caller can create a real `SanitizedWebhookUrl` instance whose `sanitized_url` still contains a bearer token in the username field, and the audit trail will accept and store it as a supposedly safe artifact location. That breaks the “secret-safe storage” contract for this type and undermines the audit guarantee that artifact URLs never contain webhook credentials.
---
## Summary

`SanitizedDatabaseUrl.__post_init__()` treats an empty password as “no password,” so direct construction allows credential-bearing database URLs like `postgresql://user:@host/db` to bypass the sanitization invariant.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/url.py`
- Line(s): `102-108`
- Function/Method: `SanitizedDatabaseUrl.__post_init__`

## Evidence

The constructor invariant is:

```python
parsed = urlparse(self.sanitized_url)
if parsed.password:
    raise ValueError(...)
```

Source: [/home/john/elspeth/src/elspeth/contracts/url.py](/home/john/elspeth/src/elspeth/contracts/url.py#L102)

But `urlparse("postgresql://user:@host/db").password` is `""`, not `None`, so this truthiness check does not fire. The factory handles that exact case correctly by using `is None` instead:

```python
if parsed.password is None:
    return cls(sanitized_url=url, fingerprint=None)
```

Source: [/home/john/elspeth/src/elspeth/contracts/url.py](/home/john/elspeth/src/elspeth/contracts/url.py#L138)

The test suite already documents that empty passwords must be sanitized:

- `test_empty_password_sanitized`
- `test_empty_password_fingerprint`

Source: [/home/john/elspeth/tests/unit/core/security/test_url.py](/home/john/elspeth/tests/unit/core/security/test_url.py#L100)

Despite that contract, direct construction currently succeeds:

- `SanitizedDatabaseUrl("postgresql://user:@host/db", None)` succeeds

That instance is then accepted by `ArtifactDescriptor.for_database()`, which persists `url.sanitized_url` after only an `isinstance` check:

```python
path_or_uri=f"db://{table}@{url.sanitized_url}"
```

Source: [/home/john/elspeth/src/elspeth/contracts/results.py](/home/john/elspeth/src/elspeth/contracts/results.py#L412)

I confirmed the resulting artifact URI is:
`db://t@postgresql://user:@host/db`

## Root Cause Hypothesis

The factory was fixed for the empty-password edge case, but the constructor invariant still uses a falsy check instead of a presence check. That leaves the dataclass open to the exact credential form the factory considers unsanitized.

## Suggested Fix

Change the constructor guard to reject any present password field, including `""`.

Example shape:

```python
parsed = urlparse(self.sanitized_url)
if parsed.password is not None:
    raise ValueError(
        "SanitizedDatabaseUrl cannot contain a password in the URL. "
        "Use SanitizedDatabaseUrl.from_raw_url() to sanitize first."
    )
```

Add a regression test that direct construction with `postgresql://user:@host/db` raises.

## Impact

This does not leak a non-empty secret, but it does let a credential-bearing DSN bypass a type whose contract says passwords have been removed. That weakens the audit-safe invariant and allows malformed “sanitized” database artifact URIs to be recorded as if they had passed sanitization.
