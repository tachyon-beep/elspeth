## Summary

Webhook fingerprint generation is collision-prone because multiple secret sets are flattened with `"|".join(...)`, causing distinct secrets to map to the same fingerprint.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `src/elspeth/contracts/url.py`
- Line(s): 210-212
- Function/Method: `SanitizedWebhookUrl.from_raw_url`

## Evidence

Current fingerprint input construction:

```python
combined = "|".join(sorted(sensitive_values))
fingerprint = secret_fingerprint(combined)
```

This is ambiguous. Reproduction (executed with `ELSPETH_FINGERPRINT_KEY=test-key`):

- URL A: `https://example.com/hook?token=a|b`
- URL B: `https://example.com/hook?token=a&api_key=b`

Both returned the same fingerprint:
`c192c9abe0b1172fb8107d3a3783b401f1ab39329c31872d0a6e4debfb5db1a2`

## Root Cause Hypothesis

Delimiter-based concatenation without escaping/length-prefixing loses structural boundaries between values, creating hash preimage ambiguity.

## Suggested Fix

Serialize `sensitive_values` unambiguously before hashing, for example:

- length-prefixed encoding, or
- deterministic JSON array encoding of sorted values.

Then hash that canonical representation instead of delimiter-joined text.

## Impact

Audit traceability can be wrong: different token combinations may appear identical in `url_fingerprint`, weakening “same secret used” attribution and forensic accuracy.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/url.py.md`
- Finding index in source report: 2
- Beads: pending
