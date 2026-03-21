# Audit Provenance Boundary Enforcement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move 9 audit provenance fields from pipeline rows to `success_reason["metadata"]`, remove PayloadStore from PluginContext, unify blob storage through the recorder.

**Architecture:** Split `populate_llm_metadata_fields()` into operational (row) and audit (success_reason) functions. Surface `Call` return from `AuditedHTTPClient.get_ssrf_safe()` so WebScrape gets blob hashes from the audit path. Add `recorder.store_payload()` for transform-produced artifacts. Remove `payload_store` from PluginContext entirely.

**Tech Stack:** Python dataclasses, pluggy transform system, pytest, `FrameworkBugError` offensive checks.

**Spec:** `docs/superpowers/specs/2026-03-21-audit-provenance-boundary-design.md`

**IMPORTANT — Task Ordering and Atomicity:**
Tasks 1-3 are foundational infrastructure. Tasks 4-7 migrate individual transforms. Task 8 removes the old wiring. Tasks 9-10 add enforcement and verify. Each task is independently committable, but the full test suite should not be run against integration tests until Task 8 is complete (PluginContext removal requires all transforms migrated first).

---

### Task 1: Add `recorder.store_payload()` method

**Files:**
- Modify: `src/elspeth/core/landscape/recorder.py`
- Create: `tests/unit/core/landscape/test_recorder_store_payload.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/landscape/test_recorder_store_payload.py`:

```python
"""Tests for LandscapeRecorder.store_payload()."""

import pytest

from elspeth.contracts.errors import FrameworkBugError
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder


class TestStorePayload:
    def test_stores_content_and_returns_sha256_hex(self):
        """store_payload() returns a 64-char hex string (SHA-256)."""
        db = LandscapeDB.in_memory()
        # Use the real FilesystemPayloadStore — it's lightweight and filesystem-based
        import tempfile
        from pathlib import Path

        from elspeth.core.payload_store import FilesystemPayloadStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemPayloadStore(Path(tmpdir))
            recorder = LandscapeRecorder(db, payload_store=store)

            content = b"test processed content for audit"
            result = recorder.store_payload(content, purpose="processed_content")

            # SHA-256 hex digest is 64 characters
            assert isinstance(result, str)
            assert len(result) == 64
            assert all(c in "0123456789abcdef" for c in result)

            # Content is retrievable
            retrieved = store.retrieve(result)
            assert retrieved == content

    def test_raises_framework_bug_error_when_no_payload_store(self):
        """store_payload() crashes with FrameworkBugError when payload_store is None."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db, payload_store=None)

        with pytest.raises(FrameworkBugError, match="store_payload.*payload_store"):
            recorder.store_payload(b"content", purpose="test")

    def test_store_payload_empty_bytes(self):
        """Empty content is valid — SHA-256 of empty is well-defined."""
        db = LandscapeDB.in_memory()
        import tempfile
        from pathlib import Path

        from elspeth.core.payload_store import FilesystemPayloadStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemPayloadStore(Path(tmpdir))
            recorder = LandscapeRecorder(db, payload_store=store)

            result = recorder.store_payload(b"", purpose="empty_test")
            assert len(result) == 64  # SHA-256 hex

    def test_purpose_label_is_documentation_only(self):
        """The purpose parameter does not affect storage — same content, same hash."""
        db = LandscapeDB.in_memory()
        import tempfile
        from pathlib import Path

        from elspeth.core.payload_store import FilesystemPayloadStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemPayloadStore(Path(tmpdir))
            recorder = LandscapeRecorder(db, payload_store=store)

            content = b"identical content"
            hash1 = recorder.store_payload(content, purpose="purpose_a")
            hash2 = recorder.store_payload(content, purpose="purpose_b")

            assert hash1 == hash2
```

- [ ] **Step 2: Run test — verify it fails (method does not exist yet)**

```bash
.venv/bin/python -m pytest tests/unit/core/landscape/test_recorder_store_payload.py -x
```

- [ ] **Step 3: Implement `store_payload()` on `LandscapeRecorder`**

Read `src/elspeth/core/landscape/recorder.py` and find the end of the `record_call` method (after the `return self._execution.record_call(...)` block, around line 461). Add the new method after `record_call`:

In `src/elspeth/core/landscape/recorder.py`, add this import at the top (inside the existing `from elspeth.contracts import ...` line or as a separate import):

```python
from elspeth.contracts.errors import FrameworkBugError
```

Then add the method to `LandscapeRecorder` (after `record_call`, before `begin_operation`):

```python
    def store_payload(self, content: bytes, *, purpose: str) -> str:
        """Store a transform-produced artifact in the payload store.

        For blobs that have no corresponding external call record — e.g.,
        post-extraction processed content. The purpose label is a code-level
        documentation convention — it is not persisted or emitted to telemetry.
        It exists solely to force callers to name what they're storing at the
        call site, making the intent visible in code review.

        Args:
            content: Raw bytes to store.
            purpose: Semantic label (e.g., "processed_content", "extracted_markdown").
                Not persisted — call-site documentation only.

        Returns:
            SHA-256 hex digest of stored content.

        Raises:
            FrameworkBugError: If recorder was constructed without a payload_store.
        """
        if self._payload_store is None:
            raise FrameworkBugError(
                f"store_payload(purpose={purpose!r}) called but recorder has no "
                f"payload_store. Orchestrator must configure LandscapeRecorder with "
                f"a payload_store when transforms that produce processed content "
                f"blobs are in the pipeline."
            )
        return self._payload_store.store(content)
```

- [ ] **Step 4: Run test — verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/core/landscape/test_recorder_store_payload.py -x
```

- [ ] **Step 5: Run ruff and mypy on the changed file**

```bash
.venv/bin/python -m ruff check src/elspeth/core/landscape/recorder.py
.venv/bin/python -m mypy src/elspeth/core/landscape/recorder.py
```

- [ ] **Step 6: Commit**

```
feat: add recorder.store_payload() for transform-produced artifacts

Adds a method to LandscapeRecorder that delegates blob storage to the
PayloadStore, with FrameworkBugError guard when no store is configured.
This enables transforms to store processed content blobs through the
recorder rather than accessing PayloadStore directly.
```

---

### Task 2: Surface `Call` return from `AuditedHTTPClient`

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/clients/http.py`
- Create: `tests/unit/plugins/infrastructure/clients/test_http_call_return.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/plugins/infrastructure/clients/test_http_call_return.py`:

```python
"""Tests for AuditedHTTPClient.get_ssrf_safe() Call return."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from elspeth.contracts.audit import Call
from elspeth.core.security.web import SSRFSafeRequest
from elspeth.plugins.infrastructure.clients.http import AuditedHTTPClient


class TestGetSsrfSafeCallReturn:
    """Verify get_ssrf_safe() returns a Call with request/response refs.

    Uses Mock() for the recorder — AuditedHTTPClient is what's being tested,
    not the recorder. The recorder mock returns a Call with known ref hashes.
    """

    def _make_mock_call(self) -> Call:
        """Create a mock Call with known request/response refs."""
        from datetime import UTC, datetime
        from elspeth.contracts import CallStatus, CallType
        return Call(
            call_id="test-call-id",
            call_index=0,
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_hash="test-request-hash",
            created_at=datetime.now(UTC),
            state_id="state-1",
            request_ref="test-request-ref-hash",
            response_hash="test-response-hash",
            response_ref="test-response-ref-hash",
            latency_ms=100.0,
        )

    def _make_client_with_mock_recorder(self) -> tuple[AuditedHTTPClient, MagicMock]:
        """Create AuditedHTTPClient with a mock recorder that returns a known Call."""
        mock_recorder = MagicMock()
        mock_call = self._make_mock_call()
        mock_recorder.record_call.return_value = mock_call
        mock_recorder.allocate_call_index.return_value = 0

        client = AuditedHTTPClient(
            recorder=mock_recorder,
            state_id="state-1",
            run_id="run-1",
            telemetry_emit=lambda event: None,
            timeout=5.0,
        )
        return client, mock_recorder

    def test_returns_three_tuple_with_call_on_success(self):
        """get_ssrf_safe() returns (Response, str, Call) on success."""
        client, mock_recorder = self._make_client_with_mock_recorder()

        # Mock the actual HTTP call
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html>test</html>"
        mock_response.text = "<html>test</html>"
        mock_response.url = httpx.URL("http://93.184.216.34/")
        mock_response.is_success = True

        safe_request = SSRFSafeRequest(
            original_url="http://example.com/",
            resolved_ip="93.184.216.34",
            pinned_url="http://93.184.216.34/",
            host_header="example.com",
            scheme="http",
        )

        with patch.object(client, "_http_client") as mock_http:
            mock_http.get.return_value = mock_response

            result = client.get_ssrf_safe(safe_request)

        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"
        response, final_url, call = result
        assert isinstance(response, MagicMock)  # our mock
        assert isinstance(final_url, str)
        assert isinstance(call, Call)
        assert call.request_ref == "test-request-ref-hash"
        assert call.response_ref == "test-response-ref-hash"

    def test_record_and_emit_returns_call(self):
        """_record_and_emit() returns a Call object."""
        client, mock_recorder = self._make_client_with_mock_recorder()

        from elspeth.contracts import CallStatus
        from elspeth.contracts.call_data import HTTPCallRequest

        request_dto = HTTPCallRequest(
            method="GET",
            url="http://example.com/",
            headers={},
        )

        result = client._record_and_emit(
            call_index=0,
            full_url="http://example.com/",
            request_data=request_dto.to_dict(),
            response=None,
            response_data=None,
            error_data=None,
            latency_ms=10.0,
            call_status=CallStatus.SUCCESS,
            request_payload=request_dto,
        )

        assert isinstance(result, Call)
        assert result.request_ref == "test-request-ref-hash"
```

- [ ] **Step 2: Run test — verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/test_http_call_return.py -x
```

- [ ] **Step 3: Implement the changes**

Read `src/elspeth/plugins/infrastructure/clients/http.py` and make these changes:

**Change 1: `_record_and_emit()` returns `Call`**

Find the `_record_and_emit` method (around line 191). Change the return type and capture the return value:

Replace the current signature and body. The key changes:
1. Return type: `-> None` becomes `-> Call`
2. Capture the return value: `self._recorder.record_call(...)` becomes `call = self._recorder.record_call(...)`
3. Add `return call` at the end

The exact change — find this block (around line 205-224):

```python
    ) -> None:
        """Record call to audit trail and emit telemetry event.
```

Replace with:

```python
    ) -> Call:
        """Record call to audit trail and emit telemetry event.
```

Then find (around line 215):

```python
        self._recorder.record_call(
            state_id=self._state_id,
            call_index=call_index,
            call_type=CallType.HTTP,
            status=call_status,
            request_data=request_payload,
            response_data=response_payload,
            error=error_data,
            latency_ms=latency_ms,
        )
```

Replace with:

```python
        call = self._recorder.record_call(
            state_id=self._state_id,
            call_index=call_index,
            call_type=CallType.HTTP,
            status=call_status,
            request_data=request_payload,
            response_data=response_payload,
            error=error_data,
            latency_ms=latency_ms,
        )
```

And at the end of the method (after the telemetry try/except block, around line 259), add:

```python
        return call
```

**IMPORTANT:** Place `return call` as the LAST statement at the method level, AFTER the telemetry try/except block — not inside the except branch.

**Note:** After this change, `_execute_request()` (used by `post()` and `get()`) silently discards the `Call` return. This is harmless — Python does not warn on discarded returns. Verify `ruff` does not flag this.

Add the `Call` import. Find the `TYPE_CHECKING` block and add `Call` if not already imported:

```python
if TYPE_CHECKING:
    from elspeth.contracts import Call
```

**Change 2: `get_ssrf_safe()` returns `tuple[httpx.Response, str, Call]`**

Find the method signature (around line 466-474):

```python
    ) -> tuple[httpx.Response, str]:
```

Replace with:

```python
    ) -> tuple[httpx.Response, str, Call]:
```

Update the docstring Returns section accordingly.

Find the success-path `record_call` (around line 608-617):

```python
            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=call_status,
                request_data=request_dto,
                response_data=response_dto,
                error=error_data,
                latency_ms=latency_ms,
            )
```

Replace with:

```python
            call = self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=call_status,
                request_data=request_dto,
                response_data=response_dto,
                error=error_data,
                latency_ms=latency_ms,
            )
```

Find the success-path return (around line 651):

```python
            return response, final_hostname_url
```

Replace with:

```python
            return response, final_hostname_url, call
```

Find the error-path `record_call` (around line 661-672):

```python
            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=CallStatus.ERROR,
                request_data=request_dto,
                error=HTTPCallError(
                    type=type(e).__name__,
                    message=str(e),
                ),
                latency_ms=latency_ms,
            )
```

Replace with:

```python
            _ = self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=CallStatus.ERROR,
                request_data=request_dto,
                error=HTTPCallError(
                    type=type(e).__name__,
                    message=str(e),
                ),
                latency_ms=latency_ms,
            )
```

- [ ] **Step 4: Update callers of `get_ssrf_safe()` to handle 3-tuple**

Read `src/elspeth/plugins/transforms/web_scrape.py` line 404. The current code:

```python
            response, final_hostname_url = client.get_ssrf_safe(
```

Replace with:

```python
            response, final_hostname_url, _call = client.get_ssrf_safe(
```

(The `_call` will be used in Task 7; for now, discard it to avoid breaking the test suite.)

- [ ] **Step 5: Run tests — verify they pass**

```bash
.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/test_http_call_return.py -x
.venv/bin/python -m pytest tests/unit/plugins/transforms/test_web_scrape.py -x
```

- [ ] **Step 6: Run ruff and mypy**

```bash
.venv/bin/python -m ruff check src/elspeth/plugins/infrastructure/clients/http.py src/elspeth/plugins/transforms/web_scrape.py
.venv/bin/python -m mypy src/elspeth/plugins/infrastructure/clients/http.py src/elspeth/plugins/transforms/web_scrape.py
```

- [ ] **Step 7: Commit**

```
feat: surface Call return from AuditedHTTPClient.get_ssrf_safe()

_record_and_emit() now returns the Call object. get_ssrf_safe() returns
a 3-tuple (Response, str, Call) so callers can access request_ref and
response_ref blob hashes from the audit path. Error path explicitly
discards the Call with _ = assignment.
```

---

### Task 3: Split `populate_llm_metadata_fields()` — LLM `__init__.py` changes

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/__init__.py`
- Create: `tests/unit/plugins/llm/test_audit_metadata_functions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/plugins/llm/test_audit_metadata_functions.py`:

```python
"""Tests for split LLM metadata functions."""

from elspeth.contracts.token_usage import TokenUsage


class TestPopulateLlmOperationalFields:
    def test_sets_usage_and_model_in_output(self):
        from elspeth.plugins.transforms.llm import populate_llm_operational_fields

        output: dict[str, object] = {}
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        populate_llm_operational_fields(
            output, "llm_response", usage=usage, model="gpt-4"
        )
        assert output["llm_response_usage"] == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }
        assert output["llm_response_model"] == "gpt-4"

    def test_usage_none_sets_none(self):
        from elspeth.plugins.transforms.llm import populate_llm_operational_fields

        output: dict[str, object] = {}
        populate_llm_operational_fields(
            output, "resp", usage=None, model="claude-3"
        )
        assert output["resp_usage"] is None
        assert output["resp_model"] == "claude-3"

    def test_does_not_set_audit_fields(self):
        from elspeth.plugins.transforms.llm import LLM_AUDIT_SUFFIXES, populate_llm_operational_fields

        output: dict[str, object] = {}
        populate_llm_operational_fields(
            output, "r", usage=None, model=None
        )
        for suffix in LLM_AUDIT_SUFFIXES:
            assert f"r{suffix}" not in output


class TestBuildLlmAuditMetadata:
    def test_returns_dict_with_all_six_audit_fields(self):
        from elspeth.plugins.transforms.llm import build_llm_audit_metadata

        result = build_llm_audit_metadata(
            "llm_response",
            template_hash="abc123",
            variables_hash="def456",
            template_source="/path/to/template.j2",
            lookup_hash="ghi789",
            lookup_source="/path/to/lookup.yaml",
            system_prompt_source="/path/to/system.txt",
        )
        assert result == {
            "llm_response_template_hash": "abc123",
            "llm_response_variables_hash": "def456",
            "llm_response_template_source": "/path/to/template.j2",
            "llm_response_lookup_hash": "ghi789",
            "llm_response_lookup_source": "/path/to/lookup.yaml",
            "llm_response_system_prompt_source": "/path/to/system.txt",
        }

    def test_handles_none_values(self):
        from elspeth.plugins.transforms.llm import build_llm_audit_metadata

        result = build_llm_audit_metadata(
            "r",
            template_hash="hash",
            variables_hash="hash2",
            template_source=None,
            lookup_hash=None,
            lookup_source=None,
            system_prompt_source=None,
        )
        assert result["r_template_source"] is None
        assert result["r_lookup_hash"] is None
        assert result["r_lookup_source"] is None
        assert result["r_system_prompt_source"] is None

    def test_uses_correct_prefix(self):
        from elspeth.plugins.transforms.llm import build_llm_audit_metadata

        result = build_llm_audit_metadata(
            "category_llm_response",
            template_hash="h", variables_hash="v",
            template_source=None, lookup_hash=None,
            lookup_source=None, system_prompt_source=None,
        )
        assert all(k.startswith("category_llm_response_") for k in result)
        assert len(result) == 6
```

- [ ] **Step 2: Run test — verify it fails (functions do not exist yet)**

```bash
.venv/bin/python -m pytest tests/unit/plugins/llm/test_audit_metadata_functions.py -x
```

- [ ] **Step 3: Implement the two new functions**

Read `src/elspeth/plugins/transforms/llm/__init__.py`. After the existing `populate_llm_metadata_fields` function (starts at line 125, ends around line 168), add the two new functions:

```python
def populate_llm_operational_fields(
    output: dict[str, object],
    field_prefix: str,
    *,
    usage: TokenUsage | None,
    model: str | None,
) -> None:
    """Populate operational metadata into the output row (stays in pipeline data).

    These fields have legitimate downstream use (budgeting, routing).
    Audit provenance fields go to success_reason["metadata"] via
    build_llm_audit_metadata() instead.

    Args:
        output: Mutable row dict to populate.
        field_prefix: Response field name (e.g., "llm_response").
        usage: Token usage (TokenUsage or None).
        model: Model identifier that actually responded.
    """
    output[f"{field_prefix}_usage"] = usage.to_dict() if usage is not None else None
    output[f"{field_prefix}_model"] = model


def build_llm_audit_metadata(
    field_prefix: str,
    *,
    template_hash: str,
    variables_hash: str,
    template_source: str | None,
    lookup_hash: str | None,
    lookup_source: str | None,
    system_prompt_source: str | None,
) -> dict[str, object]:
    """Build audit provenance dict for inclusion in success_reason["metadata"].

    Does NOT write to the output row — audit provenance lives in the Landscape only.

    Args:
        field_prefix: Response field name (e.g., "llm_response").
        template_hash: SHA-256 of prompt template.
        variables_hash: SHA-256 of rendered template variables.
        template_source: Config file path of template (None if inline).
        lookup_hash: SHA-256 of lookup data (None if no lookup).
        lookup_source: Config file path of lookup data (None if no lookup).
        system_prompt_source: Config file path of system prompt (None if inline).

    Returns:
        Dict of audit field names to values, ready to merge into
        success_reason["metadata"].
    """
    return {
        f"{field_prefix}_template_hash": template_hash,
        f"{field_prefix}_variables_hash": variables_hash,
        f"{field_prefix}_template_source": template_source,
        f"{field_prefix}_lookup_hash": lookup_hash,
        f"{field_prefix}_lookup_source": lookup_source,
        f"{field_prefix}_system_prompt_source": system_prompt_source,
    }
```

- [ ] **Step 4: Update `__all__`**

In the same file, find the `__all__` list (around line 292). Remove `"get_llm_audit_fields"` and `"populate_llm_metadata_fields"` from it. Add `"populate_llm_operational_fields"` and `"build_llm_audit_metadata"`.

The new `__all__` should be:

```python
__all__ = [
    "LLM_AUDIT_SUFFIXES",
    "LLM_GUARANTEED_SUFFIXES",
    "MULTI_QUERY_GUARANTEED_SUFFIXES",
    "_build_augmented_output_schema",
    "_build_multi_query_output_schema",
    "build_llm_audit_metadata",
    "get_llm_audit_fields",
    "get_llm_guaranteed_fields",
    "populate_llm_metadata_fields",
    "populate_llm_operational_fields",
]
```

**Note:** Keep `get_llm_audit_fields` and `populate_llm_metadata_fields` in `__all__` for now — they are still imported by call sites that will be migrated in Tasks 4-6. They will become dead code after all migrations complete; a follow-up cleanup can remove them.

- [ ] **Step 5: Remove `get_llm_audit_fields()` from output schema builders**

In `_build_augmented_output_schema()` (around line 207-210), find:

```python
    llm_field_names = [
        *get_llm_guaranteed_fields(response_field),
        *get_llm_audit_fields(response_field),
    ]
```

Replace with:

```python
    llm_field_names = [
        *get_llm_guaranteed_fields(response_field),
    ]
```

In `_build_multi_query_output_schema()` (around line 270), find:

```python
        llm_field_names = [prefix, *get_llm_guaranteed_fields(prefix), *get_llm_audit_fields(prefix)]
```

Replace with:

```python
        llm_field_names = [prefix, *get_llm_guaranteed_fields(prefix)]
```

- [ ] **Step 6: Add schema builder exclusion test**

Add to `tests/unit/plugins/llm/test_audit_metadata_functions.py`:

```python
class TestAugmentedSchemaExcludesAuditFields:
    def test_single_query_schema_excludes_audit_fields(self):
        """_build_augmented_output_schema output schema must NOT include audit field names."""
        from elspeth.plugins.transforms.llm import LLM_AUDIT_SUFFIXES, _build_augmented_output_schema

        # Read _build_augmented_output_schema to determine its signature and how to
        # extract field names from the returned schema. The schema is a Pydantic model
        # or SchemaContract — check the return type and use the appropriate accessor.
        # Example (adjust based on actual return type):
        schema = _build_augmented_output_schema(
            base_fields=[],  # adjust params based on actual signature
            response_field="llm_response",
            mode="observed",
        )
        # Extract field names from the schema — the exact method depends on the return type.
        # For SchemaContract: field_names = {f.normalized_name for f in schema.fields}
        # For Pydantic: field_names = set(schema.model_fields.keys())
        # Read the function to determine the correct accessor.
        for suffix in LLM_AUDIT_SUFFIXES:
            assert f"llm_response{suffix}" not in field_names, (
                f"Audit field 'llm_response{suffix}' should NOT be in output schema — "
                f"audit fields belong in success_reason['metadata']"
            )
```

**Note:** Read `_build_augmented_output_schema()` to determine its actual signature and how to extract field names from the returned schema before writing the final test.

- [ ] **Step 7: Run tests — verify the new tests pass**

```bash
.venv/bin/python -m pytest tests/unit/plugins/llm/test_audit_metadata_functions.py -x
```

- [ ] **Step 8: Run ruff and mypy**

```bash
.venv/bin/python -m ruff check src/elspeth/plugins/transforms/llm/__init__.py
.venv/bin/python -m mypy src/elspeth/plugins/transforms/llm/__init__.py
```

- [ ] **Step 9: Commit**

```
feat: split populate_llm_metadata_fields into operational and audit functions

Add populate_llm_operational_fields() for row data (_usage, _model) and
build_llm_audit_metadata() for success_reason dict (6 provenance fields).
Remove audit fields from output schema builders. Existing call sites
still use the old function — migration follows in subsequent tasks.
```

---

### Task 4: Migrate LLM SingleQueryStrategy

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/transform.py`
- Modify: `tests/unit/plugins/llm/test_transform.py`
- Modify: `tests/unit/plugins/llm/test_openrouter.py`
- Modify: `tests/unit/plugins/llm/test_azure.py`

- [ ] **Step 1: Update imports in `transform.py`**

Read `src/elspeth/plugins/transforms/llm/transform.py`. Find the import block (around line 36-42):

```python
from elspeth.plugins.transforms.llm import (
    _build_augmented_output_schema,
    _build_multi_query_output_schema,
    get_llm_audit_fields,
    get_llm_guaranteed_fields,
    populate_llm_metadata_fields,
)
```

Replace with:

```python
from elspeth.plugins.transforms.llm import (
    _build_augmented_output_schema,
    _build_multi_query_output_schema,
    build_llm_audit_metadata,
    get_llm_audit_fields,
    get_llm_guaranteed_fields,
    populate_llm_metadata_fields,
    populate_llm_operational_fields,
)
```

- [ ] **Step 2: Migrate `SingleQueryStrategy.execute()` — replace `populate_llm_metadata_fields` call**

Read `src/elspeth/plugins/transforms/llm/transform.py` around lines 310-340. Find:

```python
        # 6. Build output row
        output = row.to_dict()
        output[self.response_field] = content
        populate_llm_metadata_fields(
            output,
            self.response_field,
            usage=result.usage,
            model=result.model,
            template_hash=rendered.template_hash,
            variables_hash=rendered.variables_hash,
            template_source=rendered.template_source,
            lookup_hash=rendered.lookup_hash,
            lookup_source=rendered.lookup_source,
            system_prompt_source=self.system_prompt_source,
        )

        # 7. Propagate contract
        output_contract = propagate_contract(
            input_contract=row.contract,
            output_row=output,
            transform_adds_fields=True,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "enriched",
                "fields_added": [self.response_field],
                "metadata": {"model": result.model, **result.usage.to_dict()},
            },
        )
```

Replace with:

```python
        # 6. Build output row — operational fields only
        output = row.to_dict()
        output[self.response_field] = content
        populate_llm_operational_fields(
            output,
            self.response_field,
            usage=result.usage,
            model=result.model,
        )

        # 7. Build audit metadata (goes to success_reason, not the row)
        audit_metadata = build_llm_audit_metadata(
            self.response_field,
            template_hash=rendered.template_hash,
            variables_hash=rendered.variables_hash,
            template_source=rendered.template_source,
            lookup_hash=rendered.lookup_hash,
            lookup_source=rendered.lookup_source,
            system_prompt_source=self.system_prompt_source,
        )

        # 8. Propagate contract
        output_contract = propagate_contract(
            input_contract=row.contract,
            output_row=output,
            transform_adds_fields=True,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "enriched",
                "fields_added": [self.response_field],
                "metadata": {"model": result.model, **result.usage.to_dict(), **audit_metadata},
            },
        )
```

- [ ] **Step 3: Remove audit fields from single-query `declared_output_fields`**

Read `src/elspeth/plugins/transforms/llm/transform.py` around lines 1018-1021. Find:

```python
            # Single-query emits unprefixed fields
            guaranteed = get_llm_guaranteed_fields(self._response_field)
            audit = get_llm_audit_fields(self._response_field)
            self.declared_output_fields = frozenset([*guaranteed, *audit])
```

Replace with:

```python
            # Single-query emits unprefixed fields (operational only — audit goes to success_reason)
            guaranteed = get_llm_guaranteed_fields(self._response_field)
            self.declared_output_fields = frozenset(guaranteed)
```

- [ ] **Step 4: Remove audit fields from single-query `SchemaConfig`**

Find (around lines 1031-1037):

```python
            base_guaranteed = schema_config.guaranteed_fields or ()
            base_audit = schema_config.audit_fields or ()
            self._output_schema_config = SchemaConfig(
                mode=schema_config.mode,
                fields=schema_config.fields,
                guaranteed_fields=tuple(set(base_guaranteed) | set(guaranteed)),
                audit_fields=tuple(set(base_audit) | set(audit)),
                required_fields=schema_config.required_fields,
            )
```

Replace with:

```python
            base_guaranteed = schema_config.guaranteed_fields or ()
            self._output_schema_config = SchemaConfig(
                mode=schema_config.mode,
                fields=schema_config.fields,
                guaranteed_fields=tuple(set(base_guaranteed) | set(guaranteed)),
                required_fields=schema_config.required_fields,
            )
```

- [ ] **Step 5: Update tests**

For each test file, read it first, then make these changes:

**`tests/unit/plugins/llm/test_transform.py`:** Find assertions checking for audit fields in `result.row` (like `template_hash in result.row.to_dict()`) and move them to check `result.success_reason["metadata"]` instead. Find assertions about `declared_output_fields` containing audit fields and remove them. Find assertions about `_output_schema_config.audit_fields` and change them to assert `None` or empty.

**`tests/unit/plugins/llm/test_openrouter.py`:** Find assertions like `"template_hash" in result.row` (around lines 363-364, 689) and change to assert `"template_hash"` is in `result.success_reason["metadata"]`. Note: error-path `template_hash` in `result.reason` (around line 389) STAYS — error reasons are already audit trail.

**`tests/unit/plugins/llm/test_azure.py`:** Find assertions like `"template_hash" in result.row` (around lines 328, 577) and change to assert template_hash is in `result.success_reason["metadata"]`.

The pattern for each assertion migration:

Old:
```python
assert f"{response_field}_template_hash" in result.row.to_dict()
```

New:
```python
assert f"{response_field}_template_hash" in result.success_reason["metadata"]
```

Old:
```python
assert f"{response_field}_template_hash" in transform.declared_output_fields
```

Remove entirely (field no longer declared).

- [ ] **Step 6: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py tests/unit/plugins/llm/test_openrouter.py tests/unit/plugins/llm/test_azure.py -x
```

- [ ] **Step 7: Run ruff and mypy**

```bash
.venv/bin/python -m ruff check src/elspeth/plugins/transforms/llm/transform.py
.venv/bin/python -m mypy src/elspeth/plugins/transforms/llm/transform.py
```

- [ ] **Step 8: Commit**

```
feat: migrate LLM single-query audit fields from row to success_reason

SingleQueryStrategy now uses populate_llm_operational_fields() for row
data and build_llm_audit_metadata() for success_reason["metadata"].
Six provenance fields (_template_hash, _variables_hash, etc.) are no
longer in pipeline rows or declared_output_fields.
```

---

### Task 5: Migrate LLM MultiQueryStrategy

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/transform.py`
- Modify: `tests/unit/plugins/llm/test_multi_query.py`
- Modify: `tests/unit/plugins/llm/test_azure_multi_query.py`
- Modify: `tests/unit/plugins/llm/test_openrouter_multi_query.py`

- [ ] **Step 1: Extend `_QuerySuccess` with `audit_metadata`**

Read `src/elspeth/plugins/transforms/llm/transform.py` around lines 402-411. Find:

```python
    @dataclass(frozen=True, slots=True)
    class _QuerySuccess:
        """Partial output fields from a successful single-query execution.

        Tagged success type replacing bare ``dict`` in the union return of
        ``_execute_one_query``, so callers can exhaustively match on
        ``_QuerySuccess | TransformResult`` instead of ``dict | TransformResult``.
        """

        fields: dict[str, Any]
```

Replace with:

```python
    @dataclass(frozen=True, slots=True)
    class _QuerySuccess:
        """Partial output fields from a successful single-query execution.

        Tagged success type replacing bare ``dict`` in the union return of
        ``_execute_one_query``, so callers can exhaustively match on
        ``_QuerySuccess | TransformResult`` instead of ``dict | TransformResult``.
        """

        fields: dict[str, Any]
        audit_metadata: dict[str, object]
```

- [ ] **Step 2: Update `_execute_one_query()` to use new functions**

Find the `populate_llm_metadata_fields` call inside `_execute_one_query` (around lines 653-664):

```python
        populate_llm_metadata_fields(
            partial,
            f"{spec.name}_{self.response_field}",
            usage=result.usage,
            model=result.model,
            template_hash=rendered.template_hash,
            variables_hash=rendered.variables_hash,
            template_source=rendered.template_source,
            lookup_hash=rendered.lookup_hash,
            lookup_source=rendered.lookup_source,
            system_prompt_source=self.system_prompt_source,
        )

        return self._QuerySuccess(fields=partial)
```

Replace with:

```python
        populate_llm_operational_fields(
            partial,
            f"{spec.name}_{self.response_field}",
            usage=result.usage,
            model=result.model,
        )

        audit_metadata = build_llm_audit_metadata(
            f"{spec.name}_{self.response_field}",
            template_hash=rendered.template_hash,
            variables_hash=rendered.variables_hash,
            template_source=rendered.template_source,
            lookup_hash=rendered.lookup_hash,
            lookup_source=rendered.lookup_source,
            system_prompt_source=self.system_prompt_source,
        )

        return self._QuerySuccess(fields=partial, audit_metadata=audit_metadata)
```

- [ ] **Step 3: Update `_execute_sequential()` to collect audit metadata**

Find the sequential accumulation (around lines 682-740). After `accumulated_outputs.update(result.fields)` (around line 722), add audit metadata accumulation.

Find:

```python
            accumulated_outputs.update(result.fields)

        # All queries succeeded — build output row
        output = {**row.to_dict(), **accumulated_outputs}
```

Replace with:

```python
            accumulated_outputs.update(result.fields)
            accumulated_audit.update(result.audit_metadata)

        # All queries succeeded — build output row
        output = {**row.to_dict(), **accumulated_outputs}
```

Also add the `accumulated_audit` initialization. Find (around line 682):

```python
        accumulated_outputs: dict[str, Any] = {}
```

Replace with:

```python
        accumulated_outputs: dict[str, Any] = {}
        accumulated_audit: dict[str, object] = {}
```

Find the success_reason at the end of `_execute_sequential` (around lines 732-740):

```python
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
                "fields_added": list(accumulated_outputs.keys()),
                "metadata": {"model": self.model},
            },
        )
```

Replace with:

```python
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
                "fields_added": list(accumulated_outputs.keys()),
                "metadata": {"model": self.model, **accumulated_audit},
            },
        )
```

- [ ] **Step 4: Update `_execute_parallel()` to reconstruct audit metadata after pool return**

In `_execute_parallel`, the pool wraps `_QuerySuccess` in `TransformResult`. The `_process_fn` inner function does NOT carry audit metadata through `TransformResult.success_reason` (that would leak `_audit_metadata` keys into the Landscape's `node_states.success_reason_json`).

Instead, `build_llm_audit_metadata()` is cheap (string formatting of config-derived values). After the pool returns all results, reconstruct audit metadata from the query specs in the outer scope.

The `_process_fn` success branch (around lines 805-808) does NOT change — leave it as-is:

```python
            return TransformResult.success(
                PipelineRow(result.fields, observed),
                success_reason={"action": "query_completed", "metadata": {"query_name": work["spec"].name}},
            )
```

Then in the parallel success merge section (around lines 829-850), find:

```python
        # Merge all successful partial outputs
        accumulated_outputs: dict[str, Any] = {}
        for result in query_results:
            if result.row is not None:
                accumulated_outputs.update(result.row.to_dict())

        output = {**row.to_dict(), **accumulated_outputs}
        output_contract = propagate_contract(
            input_contract=row.contract,
            output_row=output,
            transform_adds_fields=True,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
                "fields_added": list(accumulated_outputs.keys()),
                "metadata": {"model": self.model},
            },
        )
```

Replace with:

```python
        # Merge all successful partial outputs
        accumulated_outputs: dict[str, Any] = {}
        for result in query_results:
            if result.row is not None:
                accumulated_outputs.update(result.row.to_dict())

        # Reconstruct audit metadata from query specs (cheap — config-derived values)
        # Template hashes are per-spec constants available in the outer scope.
        # Rendering happened inside _execute_one_query, but the template_hash and
        # template_source come from self.template (config), and system_prompt_source
        # from self.system_prompt_source. The per-query rendered.variables_hash and
        # rendered.lookup_hash are row-dependent, so we reconstruct from the specs.
        #
        # NOTE: The sequential path gets per-row hashes from _QuerySuccess.audit_metadata.
        # The parallel path cannot access _QuerySuccess (pool returns TransformResult).
        # Since build_llm_audit_metadata() needs rendered.template_hash etc. from inside
        # _execute_one_query, we use _QuerySuccess.audit_metadata on the sequential path
        # and reconstruct here by re-calling build_llm_audit_metadata per spec.
        # The template, lookup_hash, lookup_source, template_source, and system_prompt_source
        # are all config-level (same for every row). Only variables_hash is row-specific
        # and is already captured in the sequential path. For the parallel path, we
        # re-render to get the hashes — read _execute_one_query to find where
        # rendered.template_hash etc. come from.
        #
        # IMPLEMENTATION: Re-render the template for each spec to get the hashes.
        # This is the same work _execute_one_query does, but the LLM call is the
        # expensive part, not template rendering. Alternatively, extend _process_fn
        # to stash audit_metadata in a parallel dict keyed by query index (not in
        # success_reason). Choose whichever approach is cleaner when reading the code.
        accumulated_audit: dict[str, object] = {}
        for spec in self.query_specs:
            prefix = f"{spec.name}_{self.response_field}"
            rendered = self.template.render(row.to_dict(), spec.input_fields)
            accumulated_audit.update(build_llm_audit_metadata(
                prefix,
                template_hash=rendered.template_hash,
                variables_hash=rendered.variables_hash,
                template_source=rendered.template_source,
                lookup_hash=rendered.lookup_hash,
                lookup_source=rendered.lookup_source,
                system_prompt_source=self.system_prompt_source,
            ))

        output = {**row.to_dict(), **accumulated_outputs}
        output_contract = propagate_contract(
            input_contract=row.contract,
            output_row=output,
            transform_adds_fields=True,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
                "fields_added": list(accumulated_outputs.keys()),
                "metadata": {"model": self.model, **accumulated_audit},
            },
        )
```

**Design rationale:** The previous design stashed `_audit_metadata` in `success_reason` as a private key for transport across the pool boundary. This violated CLAUDE.md (the `if "_audit_metadata" in result.success_reason` check is defensive programming) and leaked the key into `node_states.success_reason_json` in the Landscape. Instead, we reconstruct audit metadata after pool return by re-rendering templates (cheap — string formatting). The LLM API call is the expensive part, not template rendering.

- [ ] **Step 5: Remove audit fields from multi-query `declared_output_fields`**

Find (around lines 965-976):

```python
            # Multi-query emits prefixed fields — compute all field sets
            prefixed_guaranteed: set[str] = set()
            prefixed_audit: set[str] = set()
            for spec in query_specs:
                prefix = f"{spec.name}_{self._response_field}"
                prefixed_guaranteed.add(prefix)
                prefixed_guaranteed.update(get_llm_guaranteed_fields(prefix))
                prefixed_audit.update(get_llm_audit_fields(prefix))
                if spec.output_fields:
                    for field in spec.output_fields:
                        prefixed_guaranteed.add(f"{spec.name}_{field.suffix}")
            self.declared_output_fields = frozenset(prefixed_guaranteed | prefixed_audit)
```

Replace with:

```python
            # Multi-query emits prefixed fields — operational only (audit goes to success_reason)
            prefixed_guaranteed: set[str] = set()
            for spec in query_specs:
                prefix = f"{spec.name}_{self._response_field}"
                prefixed_guaranteed.add(prefix)
                prefixed_guaranteed.update(get_llm_guaranteed_fields(prefix))
                if spec.output_fields:
                    for field in spec.output_fields:
                        prefixed_guaranteed.add(f"{spec.name}_{field.suffix}")
            self.declared_output_fields = frozenset(prefixed_guaranteed)
```

- [ ] **Step 6: Remove audit fields from multi-query `SchemaConfig`**

Find (around lines 984-992):

```python
            base_guaranteed = schema_config.guaranteed_fields or ()
            base_audit = schema_config.audit_fields or ()
            self._output_schema_config = SchemaConfig(
                mode=schema_config.mode,
                fields=schema_config.fields,
                guaranteed_fields=tuple(set(base_guaranteed) | prefixed_guaranteed),
                audit_fields=tuple(set(base_audit) | prefixed_audit),
                required_fields=schema_config.required_fields,
            )
```

Replace with:

```python
            base_guaranteed = schema_config.guaranteed_fields or ()
            self._output_schema_config = SchemaConfig(
                mode=schema_config.mode,
                fields=schema_config.fields,
                guaranteed_fields=tuple(set(base_guaranteed) | prefixed_guaranteed),
                required_fields=schema_config.required_fields,
            )
```

**IMPORTANT:** The `LLM_AUDIT_SUFFIXES` iteration in `multi_query.py` line 232-235 (inside `resolve_queries()`) STAYS. It validates that user-defined query field names don't collide with system suffixes — this collision check is still needed even though audit fields leave the row.

- [ ] **Step 7: Update tests**

**`tests/unit/plugins/llm/test_multi_query.py`:** Remove audit field assertions from `declared_output_fields` (around line 162). Assert audit metadata in `result.success_reason["metadata"]` per query.

**`tests/unit/plugins/llm/test_azure_multi_query.py`:** Remove `declared_output_fields` assertions for audit fields (around lines 886-887). Assert audit metadata in success_reason.

**`tests/unit/plugins/llm/test_openrouter_multi_query.py`:** Remove `template_hash in output` assertions (around lines 728-729). Assert in success_reason.

- [ ] **Step 8: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py tests/unit/plugins/llm/test_multi_query.py tests/unit/plugins/llm/test_azure_multi_query.py tests/unit/plugins/llm/test_openrouter_multi_query.py -x
```

- [ ] **Step 9: Run ruff and mypy**

```bash
.venv/bin/python -m ruff check src/elspeth/plugins/transforms/llm/transform.py
.venv/bin/python -m mypy src/elspeth/plugins/transforms/llm/transform.py
```

- [ ] **Step 10: Commit**

```
feat: migrate LLM multi-query audit fields from row to success_reason

Extends _QuerySuccess with audit_metadata field. Per-query provenance
dicts are collected in _execute_sequential/_execute_parallel and merged
into success_reason["metadata"]. Audit fields removed from
declared_output_fields and SchemaConfig.audit_fields for multi-query.
```

---

### Task 6: Migrate LLM batch transforms

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/openrouter_batch.py`
- Modify: `src/elspeth/plugins/transforms/llm/azure_batch.py`
- Modify: `tests/unit/plugins/llm/test_openrouter_batch.py`
- Modify: `tests/unit/plugins/llm/test_azure_batch.py`

- [ ] **Step 1: Migrate `openrouter_batch.py`**

Read `src/elspeth/plugins/transforms/llm/openrouter_batch.py`. Update imports:

Find the import from llm `__init__`:

```python
from elspeth.plugins.transforms.llm import (
    _build_augmented_output_schema,
    get_llm_audit_fields,
    get_llm_guaranteed_fields,
    populate_llm_metadata_fields,
)
```

Replace with:

```python
from elspeth.plugins.transforms.llm import (
    _build_augmented_output_schema,
    get_llm_guaranteed_fields,
    populate_llm_operational_fields,
)
```

Note: `build_llm_audit_metadata` is NOT imported — batch transforms rely on per-row `calls` table records for audit provenance, not accumulated audit dicts.

Update `declared_output_fields` (around line 181):

```python
        self.declared_output_fields = frozenset([*get_llm_guaranteed_fields(cfg.response_field), *get_llm_audit_fields(cfg.response_field)])
```

Replace with:

```python
        self.declared_output_fields = frozenset(get_llm_guaranteed_fields(cfg.response_field))
```

Update `_output_schema_config` (around lines 223-237):

```python
        guaranteed = get_llm_guaranteed_fields(self._response_field)
        audit = get_llm_audit_fields(self._response_field)

        # Merge with any existing fields from base schema
        base_guaranteed = schema_config.guaranteed_fields or ()
        base_audit = schema_config.audit_fields or ()

        self._output_schema_config = SchemaConfig(
            mode=schema_config.mode,
            fields=schema_config.fields,
            guaranteed_fields=tuple(set(base_guaranteed) | set(guaranteed)),
            audit_fields=tuple(set(base_audit) | set(audit)),
            required_fields=schema_config.required_fields,
        )
```

Replace with:

```python
        guaranteed = get_llm_guaranteed_fields(self._response_field)

        # Merge with any existing fields from base schema
        base_guaranteed = schema_config.guaranteed_fields or ()

        self._output_schema_config = SchemaConfig(
            mode=schema_config.mode,
            fields=schema_config.fields,
            guaranteed_fields=tuple(set(base_guaranteed) | set(guaranteed)),
            required_fields=schema_config.required_fields,
        )
```

Update the per-row `populate_llm_metadata_fields` call (around lines 717-728). Find:

```python
        populate_llm_metadata_fields(
            output,
            self._response_field,
            usage=usage,
            model=response_model,
            template_hash=rendered.template_hash,
            variables_hash=rendered.variables_hash,
            template_source=rendered.template_source,
            lookup_hash=rendered.lookup_hash,
            lookup_source=rendered.lookup_source,
            system_prompt_source=self._system_prompt_source,
        )

        return _RowSuccess(row=output)
```

Replace with:

```python
        populate_llm_operational_fields(
            output,
            self._response_field,
            usage=usage,
            model=response_model,
        )

        return _RowSuccess(row=output)
```

**Do NOT add `audit_metadata` to `_RowSuccess`.** Do NOT change `_RowSuccess` — leave it as-is with only the `row` field. Batch transforms process potentially thousands of rows. Accumulating per-row audit dicts into a single `success_reason["metadata"]` creates an unbounded blob in `node_states.success_reason_json`.

Per-row audit provenance is already recorded in the `calls` table via `AuditedHTTPClient.record_call()`. Each LLM API call gets a `Call` row with `request_ref` (hashed request including the rendered prompt) and `response_ref` (hashed response). The `calls` table provides per-row provenance without any additional work.

The batch-level `success_reason["metadata"]` should contain only **aggregate stats** (batch_size, total tokens, etc.) — not per-row audit fields. Find the `success_reason` construction in `_process_batch` and update it to include only aggregate metadata:

```python
            success_reason={
                "action": "enriched",
                "fields_added": [self._response_field],
                "metadata": {
                    "batch_size": len(output_rows),
                },
            },
```

(Adjust based on what aggregate stats are already available in the batch processing loop.)

- [ ] **Step 2: Migrate `azure_batch.py` — same pattern**

Read `src/elspeth/plugins/transforms/llm/azure_batch.py` and apply the same changes:

1. Update imports (same as openrouter_batch — `populate_llm_operational_fields` only, no `build_llm_audit_metadata`)
2. Update `declared_output_fields` (around line 163)
3. Update `_output_schema_config` (around lines 197-211)
4. Update the per-row `populate_llm_metadata_fields` call (around lines 1366-1377) — replace with `populate_llm_operational_fields` only
5. Update the batch success_reason to contain only aggregate stats (batch_size), not per-row audit metadata

For Azure batch, `populate_llm_metadata_fields` is called inline during result processing (not in a `_RowSuccess`). Apply the same principle as OpenRouter batch: per-row audit provenance is already in the `calls` table, so do NOT accumulate per-row audit dicts.

Find the `populate_llm_metadata_fields` call (around line 1366):

```python
                populate_llm_metadata_fields(
                    output_row,
                    self._response_field,
                    usage=usage,
                    model=body.get("model"),
                    template_hash=self._template.template_hash,
                    variables_hash=variables_hash,
                    template_source=self._template.template_source,
                    lookup_hash=self._template.lookup_hash,
                    lookup_source=self._template.lookup_source,
                    system_prompt_source=self._system_prompt_source,
                )
```

Replace with:

```python
                populate_llm_operational_fields(
                    output_row,
                    self._response_field,
                    usage=usage,
                    model=body.get("model"),
                )
```

Do NOT add `build_llm_audit_metadata()` calls per row. Do NOT accumulate `audit_metadata_by_row`. The batch success_reason should contain only aggregate stats:

```python
            success_reason={
                "action": "enriched",
                "fields_added": [self._response_field],
                "metadata": {
                    "batch_size": len(output_rows),
                },
            },
```

Per-row provenance is already recorded in the `calls` table by `AuditedHTTPClient.record_call()` — each API call gets `request_ref`/`response_ref` hashes.

- [ ] **Step 3: Update tests**

**`tests/unit/plugins/llm/test_openrouter_batch.py`:** Remove audit field assertions from rows (around lines 561, 797). Assert in success_reason.

**`tests/unit/plugins/llm/test_azure_batch.py`:** Remove `declared_output_fields` assertion for `template_hash` (around lines 1692-1696). Assert in success_reason.

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/plugins/llm/test_openrouter_batch.py tests/unit/plugins/llm/test_azure_batch.py -x
```

- [ ] **Step 5: Run ruff and mypy**

```bash
.venv/bin/python -m ruff check src/elspeth/plugins/transforms/llm/openrouter_batch.py src/elspeth/plugins/transforms/llm/azure_batch.py
.venv/bin/python -m mypy src/elspeth/plugins/transforms/llm/openrouter_batch.py src/elspeth/plugins/transforms/llm/azure_batch.py
```

- [ ] **Step 6: Commit**

```
feat: migrate LLM batch transform audit fields from row to success_reason

OpenRouter and Azure batch transforms now use
populate_llm_operational_fields() and build_llm_audit_metadata().
Audit provenance goes to success_reason["metadata"] per row.
```

---

### Task 7: Migrate WebScrape transform

**Files:**
- Modify: `src/elspeth/plugins/transforms/web_scrape.py`
- Modify: `tests/unit/plugins/transforms/test_web_scrape.py`
- Modify: `tests/unit/plugins/transforms/test_web_scrape_security.py`
- Modify: `tests/unit/contracts/transform_contracts/test_web_scrape_contract.py`

- [ ] **Step 1: Define `WEBSCRAPE_AUDIT_FIELDS` constant**

Read `src/elspeth/plugins/transforms/web_scrape.py`. Near the top of the file (after the imports, before the class definition), add:

```python
# Audit-only fields — provenance metadata that lives in success_reason["metadata"],
# not in pipeline rows. See spec: 2026-03-21-audit-provenance-boundary-design.md
WEBSCRAPE_AUDIT_FIELDS: tuple[str, ...] = (
    "fetch_request_hash",
    "fetch_response_raw_hash",
    "fetch_response_processed_hash",
)
```

- [ ] **Step 2: Remove `self._payload_store` from `on_start()`**

Find (around line 262):

```python
        self._payload_store = ctx.payload_store
```

Remove this line entirely.

- [ ] **Step 3: Change `_fetch_url()` return type to include `Call`**

Find (around line 366):

```python
    def _fetch_url(self, safe_request: SSRFSafeRequest, ctx: TransformContext) -> tuple[httpx.Response, str]:
```

Replace with:

```python
    def _fetch_url(self, safe_request: SSRFSafeRequest, ctx: TransformContext) -> tuple[httpx.Response, str, Call]:
```

Add `Call` as a **runtime import** (not inside `TYPE_CHECKING`). This file does not use `from __future__ import annotations`, so the `Call` type in the return annotation is evaluated at runtime and must be importable.

Add to the existing imports at the top of the file:

```python
from elspeth.contracts.audit import Call
```

Also add the `FrameworkBugError` import if not already present:

```python
from elspeth.contracts.errors import FrameworkBugError
```

Find the return in `_fetch_url` (around line 427):

```python
            return response, final_hostname_url
```

This was already changed in Task 2 to capture `_call`. Now change it to return the call:

```python
            return response, final_hostname_url, call
```

And update the `client.get_ssrf_safe` call (around line 404) from the Task 2 temporary `_call`:

```python
            response, final_hostname_url, _call = client.get_ssrf_safe(
```

Replace with:

```python
            response, final_hostname_url, call = client.get_ssrf_safe(
```

- [ ] **Step 4: Update `process()` — get hashes from `Call` and `recorder.store_payload()`**

Find the current code (around lines 296-364):

```python
            response, final_hostname_url = self._fetch_url(safe_request, ctx)
```

Replace with:

```python
            response, final_hostname_url, call = self._fetch_url(safe_request, ctx)
```

Find the payload store usage block (around lines 333-350):

```python
        # Store payloads for forensic recovery (captured in on_start)
        if self._payload_store is None:
            raise RuntimeError("WebScrapeTransform requires payload_store (not wired by executor)")
        request_hash = self._payload_store.store(f"GET {url}".encode())
        response_raw_hash = self._payload_store.store(response.content)
        response_processed_hash = self._payload_store.store(content.encode())

        # Enrich row with scraped data
        # Use explicit to_dict() conversion (PipelineRow guaranteed by engine)
        output = row.to_dict()
        output[self._content_field] = content
        output[self._fingerprint_field] = fingerprint
        output["fetch_status"] = response.status_code
        output["fetch_url_final"] = final_hostname_url
        output["fetch_url_final_ip"] = str(response.url)
        output["fetch_request_hash"] = request_hash
        output["fetch_response_raw_hash"] = response_raw_hash
        output["fetch_response_processed_hash"] = response_processed_hash
```

Replace with:

```python
        # Hashes from audit trail — request and response blobs are already stored
        # by AuditedHTTPClient via recorder.record_call()
        if call.request_ref is None or call.response_ref is None:
            raise FrameworkBugError(
                "AuditedHTTPClient returned a Call with no request_ref/response_ref — "
                "LandscapeRecorder must be configured with a payload_store for "
                "hash-based audit provenance in WebScrapeTransform."
            )
        request_hash = call.request_ref
        response_raw_hash = call.response_ref

        # Store processed content via recorder (transform-produced artifact)
        response_processed_hash = self._recorder.store_payload(
            content.encode(), purpose="processed_content"
        )

        # Enrich row with scraped data — operational fields only
        # Use explicit to_dict() conversion (PipelineRow guaranteed by engine)
        output = row.to_dict()
        output[self._content_field] = content
        output[self._fingerprint_field] = fingerprint
        output["fetch_status"] = response.status_code
        output["fetch_url_final"] = final_hostname_url
        output["fetch_url_final_ip"] = safe_request.resolved_ip
```

- [ ] **Step 5: Move hash fields to `success_reason["metadata"]`**

Find the success return (around lines 358-364):

```python
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "enriched",
                "fields_added": [self._content_field, self._fingerprint_field],
            },
        )
```

Replace with:

```python
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "enriched",
                "fields_added": [self._content_field, self._fingerprint_field],
                "metadata": {
                    "fetch_request_hash": request_hash,
                    "fetch_response_raw_hash": response_raw_hash,
                    "fetch_response_processed_hash": response_processed_hash,
                },
            },
        )
```

- [ ] **Step 6: Remove hash fields from `declared_output_fields`**

Find (around lines 200-211):

```python
        self.declared_output_fields = frozenset(
            [
                cfg.content_field,
                cfg.fingerprint_field,
                "fetch_status",
                "fetch_url_final",
                "fetch_url_final_ip",
                "fetch_request_hash",
                "fetch_response_raw_hash",
                "fetch_response_processed_hash",
            ]
        )
```

Replace with:

```python
        self.declared_output_fields = frozenset(
            [
                cfg.content_field,
                cfg.fingerprint_field,
                "fetch_status",
                "fetch_url_final",
                "fetch_url_final_ip",
            ]
        )
```

- [ ] **Step 7: Update tests**

**`tests/unit/plugins/transforms/test_web_scrape.py`:**
- Remove assertions for hash fields in output rows (e.g., `assert "fetch_request_hash" in result.row.to_dict()`)
- Add assertions for hash fields in `result.success_reason["metadata"]`
- Remove `payload_store.store()` mock calls and expectations
- Remove `payload_store.exists()` mock calls
- Remove hash fields from `declared_output_fields` assertions
- Update `fetch_url_final_ip` assertions — the value is now `safe_request.resolved_ip` (an IP address string), not `str(response.url)` (a URL string)
- **IMPORTANT:** Configure the mock recorder to return a proper `Call` object. After this change, `process()` reads `call.request_ref` on the object returned by `landscape.record_call()`. A bare `Mock().record_call()` returns another `Mock`, whose `.request_ref` is a `Mock` object, not a string. In each test fixture that creates `mock_ctx.landscape`, add:

```python
from datetime import UTC, datetime
from elspeth.contracts.audit import Call
from elspeth.contracts import CallStatus, CallType

mock_call = Call(
    call_id="test-call-id",
    call_index=0,
    call_type=CallType.HTTP,
    status=CallStatus.SUCCESS,
    request_hash="test-request-hash",
    created_at=datetime.now(UTC),
    state_id="test-state",
    request_ref="test-request-ref-hash",
    response_hash="test-response-hash",
    response_ref="test-response-ref-hash",
    latency_ms=100.0,
)
mock_ctx.landscape.record_call.return_value = mock_call
mock_ctx.landscape.allocate_call_index.return_value = 0
mock_ctx.landscape.store_payload.return_value = "test-processed-hash"
```

**`tests/unit/plugins/transforms/test_web_scrape_security.py`:**
- Remove hash field assertions from rows and `declared_output_fields` (if any exist — the security tests focus on SSRF blocking, so hash assertions may only appear in mock setup via `payload_store`; remove those mock setup lines)

**`tests/unit/contracts/transform_contracts/test_web_scrape_contract.py`:**
- Remove `payload_store` from the `ctx` fixture (around line 93-103 where `mock_payload_store` is created and passed to `PluginContext`)
- Check for any hash field assertions in output field contract tests and remove them (note: this file is only ~105 lines and may not have hash field assertions — the hash field assertions are in `tests/unit/plugins/transforms/test_web_scrape_security.py` if anywhere)

- [ ] **Step 8: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/plugins/transforms/test_web_scrape.py tests/unit/plugins/transforms/test_web_scrape_security.py tests/unit/contracts/transform_contracts/test_web_scrape_contract.py -x
```

- [ ] **Step 9: Run ruff and mypy**

```bash
.venv/bin/python -m ruff check src/elspeth/plugins/transforms/web_scrape.py
.venv/bin/python -m mypy src/elspeth/plugins/transforms/web_scrape.py
```

- [ ] **Step 10: Commit**

```
feat: migrate WebScrape hash fields from row to success_reason

WebScrape now gets request/response hashes from Call.request_ref and
Call.response_ref. Processed content stored via recorder.store_payload().
All three hashes go to success_reason["metadata"]. Direct PayloadStore
access removed. fetch_url_final_ip fixed to use safe_request.resolved_ip.
```

---

### Task 8: Remove PayloadStore from PluginContext

**Files:**
- Modify: `src/elspeth/contracts/plugin_context.py`
- Modify: `src/elspeth/contracts/contexts.py`
- Modify: `src/elspeth/engine/orchestrator/core.py`
- Update tests that mock `ctx.payload_store`

- [ ] **Step 1: Remove from `PluginContext` dataclass**

Read `src/elspeth/contracts/plugin_context.py`. Find (around line 84):

```python
    payload_store: PayloadStore | None = None
```

Remove this line.

Update the docstring (around lines 64-68). Find:

```python
    """Context passed to every plugin operation.

    Provides access to:
    - Run metadata (run_id, config)
    - Audit trail (landscape, payload_store)
    - External call recording (record_call)
```

Replace with:

```python
    """Context passed to every plugin operation.

    Provides access to:
    - Run metadata (run_id, config)
    - Audit trail (landscape)
    - External call recording (record_call)
```

Remove the `PayloadStore` from the `TYPE_CHECKING` import if it's only used for `payload_store`. Check if `PayloadStore` is imported elsewhere in the file first.

- [ ] **Step 2: Remove from `LifecycleContext` protocol**

Read `src/elspeth/contracts/contexts.py`. Find (around lines 198-199):

```python
    @property
    def payload_store(self) -> PayloadStore | None: ...
```

Remove these two lines. Also remove the `PayloadStore` import if no longer needed.

- [ ] **Step 3: Remove from orchestrator's `PluginContext` construction**

Read `src/elspeth/engine/orchestrator/core.py` around lines 1485-1493. Find:

```python
        ctx = PluginContext(
            run_id=run_id,
            config=config.config,
            landscape=recorder,
            payload_store=payload_store,
            rate_limit_registry=self._rate_limit_registry,
            concurrency_config=self._concurrency_config,
            _batch_checkpoints=batch_checkpoints or {},
            telemetry_emit=self._emit_telemetry,
        )
```

Replace with:

```python
        ctx = PluginContext(
            run_id=run_id,
            config=config.config,
            landscape=recorder,
            rate_limit_registry=self._rate_limit_registry,
            concurrency_config=self._concurrency_config,
            _batch_checkpoints=batch_checkpoints or {},
            telemetry_emit=self._emit_telemetry,
        )
```

- [ ] **Step 4: Find and update all tests that mock `ctx.payload_store`**

Search for `payload_store` references in tests:

```bash
grep -rn "payload_store" tests/ --include="*.py"
```

For each test file found:
- Remove `payload_store=` from `PluginContext` construction in test fixtures
- Remove mock `PayloadStore` objects passed to contexts
- If the test verified `payload_store.store()` was called, remove those assertions (already handled in Task 7 for WebScrape tests)

**Note:** Task 7 already updated `test_web_scrape.py` and `test_web_scrape_security.py` to remove `payload_store` usage from assertion paths. Task 8's grep may still find `payload_store` references in mock setup — these are the construction-site references that Task 8 must remove.

- [ ] **Step 5: Run the full unit test suite**

```bash
.venv/bin/python -m pytest tests/unit/ -x
```

- [ ] **Step 6: Run ruff and mypy on changed files**

```bash
.venv/bin/python -m ruff check src/elspeth/contracts/plugin_context.py src/elspeth/contracts/contexts.py src/elspeth/engine/orchestrator/core.py
.venv/bin/python -m mypy src/elspeth/contracts/ src/elspeth/engine/orchestrator/core.py
```

- [ ] **Step 7: Commit**

```
refactor: remove payload_store from PluginContext

No plugin needs direct PayloadStore access after the audit provenance
boundary migration. Transforms store blobs through
recorder.store_payload() and get hashes from Call.request_ref/response_ref.
```

---

### Task 9: AGENTS.md + enforcement + test updates

**Files:**
- Create: `src/elspeth/plugins/transforms/AGENTS.md`
- Modify: `tests/unit/plugins/llm/test_llm_success_reason.py`
- Modify: `tests/unit/contracts/test_schema_config.py`

- [ ] **Step 1: Create `AGENTS.md`**

Create `src/elspeth/plugins/transforms/AGENTS.md`:

```markdown
# Transforms — Pipeline Data vs Audit Provenance

## The Decision Test

> Would a pipeline operator or downstream transform ever make a decision based on this value?

- **Yes** → Output row field (via `declared_output_fields`)
- **No** → Audit trail (via `success_reason["metadata"]`)

## Examples

| Field | Location | Why |
|-------|----------|-----|
| `fetch_status = 403` | Row | A gate might route forbidden pages to review |
| `llm_response_model = "gpt-4"` | Row | Multi-model routing, cost filtering |
| `llm_response_usage` | Row | Budget tracking, cost routing |
| `template_hash = abc123` | Audit | Forensic reconstruction only |
| `variables_hash` | Audit | Forensic reconstruction only |
| `fetch_request_hash` | Audit | Blob reference for forensic recovery |

## Where Audit Provenance Goes

```python
return TransformResult.success(
    PipelineRow(output, contract),
    success_reason={
        "action": "enriched",
        "metadata": {
            "template_hash": rendered.template_hash,
            "variables_hash": rendered.variables_hash,
            # ... other provenance fields
        },
    },
)
```

Persisted in `node_states.success_reason_json`. Retrievable via `elspeth explain`.

## Blob Storage

Transforms that produce processed content (not from an external call) store blobs
via `recorder.store_payload(content, purpose="descriptive_label")`.

Request/response blobs from external calls are already stored by `AuditedHTTPClient`
via `recorder.record_call()`. Access hashes from the returned `Call` object:
`call.request_ref`, `call.response_ref`.

**Scope constraint:** If `recorder.store_payload()` appears in more than 2-3
transforms, the Shifting the Burden archetype is reforming and the design needs
revisiting.

## Constants

Each transform with audit-only fields defines a constant tuple:
- `LLM_AUDIT_SUFFIXES` in `plugins/transforms/llm/__init__.py`
- `WEBSCRAPE_AUDIT_FIELDS` in `plugins/transforms/web_scrape.py`
```

- [ ] **Step 2: Update `test_llm_success_reason.py`**

Read `tests/unit/plugins/llm/test_llm_success_reason.py`. The file already has `single_query_result` and `multi_query_result` fixtures (using `SingleQueryStrategy` and `MultiQueryStrategy` with mocked providers). Add these tests to the existing `TestSingleQuerySuccessReason` class:

```python
    def test_success_reason_contains_audit_metadata(
        self,
        single_query_result: TransformResult,
    ) -> None:
        """Audit provenance fields live in success_reason['metadata'], not the row."""
        assert single_query_result.success_reason is not None
        metadata = single_query_result.success_reason["metadata"]
        response_field = "llm_response"
        # All 6 audit fields present
        assert f"{response_field}_template_hash" in metadata
        assert f"{response_field}_variables_hash" in metadata
        assert f"{response_field}_template_source" in metadata
        assert f"{response_field}_lookup_hash" in metadata
        assert f"{response_field}_lookup_source" in metadata
        assert f"{response_field}_system_prompt_source" in metadata

    def test_audit_fields_not_in_row(
        self,
        single_query_result: TransformResult,
    ) -> None:
        """Audit provenance fields must NOT be in the pipeline row."""
        assert single_query_result.row is not None
        row_data = single_query_result.row.to_dict()
        response_field = "llm_response"
        from elspeth.plugins.transforms.llm import LLM_AUDIT_SUFFIXES
        for suffix in LLM_AUDIT_SUFFIXES:
            assert f"{response_field}{suffix}" not in row_data, (
                f"Audit field '{response_field}{suffix}' found in row — "
                f"should be in success_reason['metadata'] only"
            )
```

And add to `TestMultiQuerySuccessReason`:

```python
    def test_success_reason_contains_audit_metadata(
        self,
        multi_query_result: TransformResult,
    ) -> None:
        """Multi-query audit provenance fields live in success_reason['metadata']."""
        assert multi_query_result.success_reason is not None
        metadata = multi_query_result.success_reason["metadata"]
        # Multi-query uses prefixed fields: {query_name}_{response_field}_{suffix}
        for query_name in ("sentiment", "topic"):
            prefix = f"{query_name}_llm_response"
            assert f"{prefix}_template_hash" in metadata
            assert f"{prefix}_variables_hash" in metadata
```

- [ ] **Step 3: Update `test_schema_config.py`**

Read `tests/unit/contracts/test_schema_config.py`. Add assertion that LLM transforms produce `audit_fields=None` (or empty):

```python
def test_llm_output_schema_config_has_no_audit_fields():
    """After audit provenance boundary enforcement, LLM audit_fields is None."""
    # ... set up an LLM transform instance
    assert transform._output_schema_config.audit_fields is None or transform._output_schema_config.audit_fields == ()
```

Read the existing test file to determine how to instantiate the transform for this assertion.

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/plugins/llm/test_llm_success_reason.py tests/unit/contracts/test_schema_config.py -x
```

- [ ] **Step 5: Note on integration test**

**Follow-up task (not in this plan):** Create an integration test: end-to-end pipeline with ChaosLLM verifying audit fields in `success_reason`, not in output rows. Use the existing `chaosllm_sentiment` example config adapted for test. This plan is already large enough; the integration test is deferred.

- [ ] **Step 6: Commit**

```
docs: add AGENTS.md for transforms boundary rules; update assertion tests

Creates pipeline-data vs audit-provenance documentation for AI assistants
and reviewers. Updates test_llm_success_reason.py with 6 audit field
assertions in metadata. Updates test_schema_config.py with audit_fields=None.
```

---

### Task 10: Example pipelines + final verification

**Files:**
- Modify: `examples/chaosweb/settings.yaml` (if it exists and references hash fields)
- Modify: `docs/superpowers/specs/2026-03-21-audit-provenance-boundary-design.md`

- [ ] **Step 1: Check and update example pipeline configs**

Search for hash field references in example configs:

```bash
grep -rn "fetch_request_hash\|fetch_response_raw_hash\|fetch_response_processed_hash\|template_hash\|variables_hash" examples/ --include="*.yaml" --include="*.yml"
```

For each match found in sink schemas or field lists, remove the hash field references.

Also search for `fetch_url_final_ip` references in examples and tests that may pattern-match on the old URL format (now an IP string):

```bash
grep -rn "fetch_url_final_ip" examples/ src/elspeth/ tests/
```

**Note:** The spec's CI naming convention check (flag `*_hash`, `*_source`, `*_ref` in `declared_output_fields`) is deferred to a separate follow-up task — not part of this plan.

- [ ] **Step 2: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -x
```

- [ ] **Step 3: Run mypy**

```bash
.venv/bin/python -m mypy src/
```

- [ ] **Step 4: Run ruff**

```bash
.venv/bin/python -m ruff check src/
```

- [ ] **Step 5: Run tier model enforcer**

```bash
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
```

- [ ] **Step 6: Verify no stale test assertions on template_hash in output rows**

```bash
grep -rn "template_hash" tests/property/ tests/integration/config/
```

Check whether `test_template_properties.py` or `test_template_resolver_integration.py` assert on `template_hash` in output rows (which would now fail). Update any found.

- [ ] **Step 7: Run example pipelines (if available)**

```bash
# Check if examples have execution scripts
ls examples/*/settings.yaml
# Run any that exist and have the necessary test data
```

- [ ] **Step 8: Update spec status**

Read `docs/superpowers/specs/2026-03-21-audit-provenance-boundary-design.md`. Find:

```
**Status:** Draft
```

Replace with:

```
**Status:** Implemented
```

- [ ] **Step 9: Clean up dead code**

After all migrations are complete, check if `populate_llm_metadata_fields` and `get_llm_audit_fields` still have any callers:

```bash
grep -rn "populate_llm_metadata_fields\|get_llm_audit_fields" src/ --include="*.py"
```

If no callers remain outside of `__init__.py` itself:
- Remove `populate_llm_metadata_fields` function from `__init__.py`
- Remove `get_llm_audit_fields` from `__all__` (keep the function as internal helper if `build_llm_audit_metadata` or collision checking uses the suffixes)
- Remove `populate_llm_metadata_fields` from `__all__`

- [ ] **Step 10: Note on `elspeth explain` TUI**

Do NOT attempt to verify that `elspeth explain` retrieves provenance from `success_reason` metadata — the TUI currently has no code to surface `success_reason` data. Instead, create a filigree follow-up task: "Update elspeth explain TUI to display provenance from success_reason metadata".

- [ ] **Step 11: Note on pre-migration runs**

Pre-migration runs will not contain audit metadata in `success_reason_json`. This is expected — the data was previously in the row, not in the audit metadata slot. `elspeth explain` for old runs will show provenance from row fields (if preserved by sinks); new runs show provenance from `success_reason_json`.

- [ ] **Step 12: Final commit**

```
chore: final verification and cleanup for audit provenance boundary

Update spec status to Implemented. Remove dead code from LLM __init__.
Update example pipeline configs. All tests, mypy, ruff, and tier model
enforcer pass.
```
