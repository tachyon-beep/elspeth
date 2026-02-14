## Summary

`_analyze_prompt` accepts `documentsAnalysis: []` as clean in `"both"`/`"document"` modes, which is a fail-open response-validation gap.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py
- Line(s): 445-450, 468-470, 484-497, 499-502
- Function/Method: `AzurePromptShield._analyze_prompt`

## Evidence

The request sends one document in `"both"` and `"document"` modes:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py:445-450
if self._analysis_type == "user_prompt":
    request_body = {"userPrompt": text, "documents": []}
elif self._analysis_type == "document":
    request_body = {"userPrompt": "", "documents": [text]}
else:
    request_body = {"userPrompt": text, "documents": [text]}
```

But response validation only checks "is list" and per-item type; empty list passes:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py:468-497
doc_attack = False
documents_analysis = data.get("documentsAnalysis") if isinstance(data, dict) else None
if not isinstance(documents_analysis, list):
    raise MalformedResponseError(...)
for i, doc in enumerate(documents_analysis):
    ...
    if attack_detected:
        doc_attack = True
```

Then it returns "no attack":

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py:499-502
return {"user_prompt_attack": user_attack, "document_attack": doc_attack}
```

Verified by runtime repro in this repo: with a mocked 200 response containing
`{"userPromptAnalysis": {"attackDetected": False}, "documentsAnalysis": []}`,
the transform returns `status success` and does not flag malformed response.

## Root Cause Hypothesis

Boundary validation is type-focused but does not enforce cardinality/invariant checks that should match the request contract (one document submitted => one document analysis expected).

## Suggested Fix

In `_analyze_prompt`, enforce strict cardinality when document analysis is enabled:
- `"document"` or `"both"`: require `len(documentsAnalysis) == 1` (or at least `>=1`, if Azure contract explicitly allows multiple echoes for one input).
- If cardinality is unexpected, raise `MalformedResponseError` (fail closed).

## Impact

A structurally degraded external response can be treated as safe, allowing prompt-injection content to pass as `"validated"` in document-analysis paths. This is a security and audit-integrity risk.
