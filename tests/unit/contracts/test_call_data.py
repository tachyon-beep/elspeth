"""Hash stability + construction tests for call data frozen dataclasses.

These tests guard the critical invariant: ``to_dict()`` must produce
byte-identical JSON (and therefore identical ``stable_hash()``) to the
old inline dict construction that it replaces.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.call_data import (
    CallPayload,
    HTTPCallError,
    HTTPCallRequest,
    HTTPCallResponse,
    LLMCallError,
    LLMCallRequest,
    LLMCallResponse,
    RawCallPayload,
)
from elspeth.contracts.token_usage import TokenUsage
from elspeth.core.canonical import stable_hash

# ---------------------------------------------------------------------------
# RawCallPayload
# ---------------------------------------------------------------------------


class TestRawCallPayload:
    """RawCallPayload wraps pre-serialized dicts and satisfies CallPayload."""

    def test_frozen(self) -> None:
        obj = RawCallPayload({"k": "v"})
        with pytest.raises(AttributeError):
            obj.data = {"other": "value"}  # type: ignore[misc]

    def test_to_dict_returns_copy(self) -> None:
        obj = RawCallPayload({"k": "v"})
        returned = obj.to_dict()
        returned["injected"] = "mutation"
        assert "injected" not in obj.to_dict()

    def test_to_dict_matches_input(self) -> None:
        original = {"type": "TestError", "message": "something failed"}
        obj = RawCallPayload(original)
        assert obj.to_dict() == original

    def test_satisfies_call_payload_protocol(self) -> None:
        assert isinstance(RawCallPayload({"k": "v"}), CallPayload)

    def test_hash_stability(self) -> None:
        original_dict = {"type": "TestError", "message": "something failed"}
        payload = RawCallPayload(original_dict)
        assert stable_hash(payload.to_dict()) == stable_hash(original_dict)


# ---------------------------------------------------------------------------
# LLMCallRequest
# ---------------------------------------------------------------------------


class TestLLMCallRequest:
    """LLMCallRequest.to_dict() produces identical hashes to old dict."""

    def test_basic_request_hash_stability(self) -> None:
        old_dict: dict[str, object] = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.0,
            "provider": "openai",
        }
        new_dict = LLMCallRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.0,
            provider="openai",
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_request_with_max_tokens_hash_stability(self) -> None:
        old_dict: dict[str, object] = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7,
            "provider": "azure",
        }
        old_dict["max_tokens"] = 100

        new_dict = LLMCallRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            provider="azure",
            max_tokens=100,
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_request_with_extra_kwargs_hash_stability(self) -> None:
        kwargs = {"top_p": 0.9, "frequency_penalty": 0.5}
        old_dict: dict[str, object] = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Test"}],
            "temperature": 0.0,
            "provider": "openai",
            **kwargs,
        }
        new_dict = LLMCallRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Test"}],
            temperature=0.0,
            provider="openai",
            extra_kwargs=kwargs,
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_max_tokens_none_excluded(self) -> None:
        d = LLMCallRequest(
            model="gpt-4",
            messages=[],
            temperature=0.0,
            provider="openai",
            max_tokens=None,
        ).to_dict()
        assert "max_tokens" not in d

    def test_frozen(self) -> None:
        obj = LLMCallRequest(
            model="gpt-4",
            messages=[],
            temperature=0.0,
            provider="openai",
        )
        with pytest.raises(AttributeError):
            obj.model = "gpt-3.5"  # type: ignore[misc]

    def test_pre_tupled_messages_inner_dicts_frozen(self) -> None:
        """Messages passed as a tuple must still have inner dicts deep-frozen."""
        from types import MappingProxyType

        inner = {"role": "user", "content": "Hello"}
        obj = LLMCallRequest(
            model="gpt-4",
            messages=(inner,),
            temperature=0.0,
            provider="openai",
        )
        # Inner message should be MappingProxyType, not a mutable dict
        assert isinstance(obj.messages[0], MappingProxyType)
        # Original dict should not have been mutated into proxy
        assert isinstance(inner, dict)

    def test_extra_kwargs_collision_raises(self) -> None:
        with pytest.raises(ValueError, match="reserved key"):
            LLMCallRequest(
                model="gpt-4",
                messages=[],
                temperature=0.0,
                provider="openai",
                extra_kwargs={"model": "overridden"},
            )

    def test_extra_kwargs_collision_multiple_keys(self) -> None:
        with pytest.raises(ValueError, match="reserved key"):
            LLMCallRequest(
                model="gpt-4",
                messages=[],
                temperature=0.0,
                provider="openai",
                extra_kwargs={"temperature": 99, "provider": "evil"},
            )

    def test_extra_kwargs_non_reserved_accepted(self) -> None:
        obj = LLMCallRequest(
            model="gpt-4",
            messages=[],
            temperature=0.0,
            provider="openai",
            extra_kwargs={"top_p": 0.9, "frequency_penalty": 0.5},
        )
        d = obj.to_dict()
        assert d["top_p"] == 0.9
        assert d["frequency_penalty"] == 0.5


# ---------------------------------------------------------------------------
# LLMCallResponse
# ---------------------------------------------------------------------------


class TestLLMCallResponse:
    """LLMCallResponse.to_dict() produces identical hashes to old dict."""

    def test_hash_stability(self) -> None:
        usage = TokenUsage.known(prompt_tokens=10, completion_tokens=20)
        raw = {"id": "chatcmpl-123", "choices": []}
        old_dict = {
            "content": "Hello world",
            "model": "gpt-4",
            "usage": usage.to_dict(),
            "raw_response": raw,
        }
        new_dict = LLMCallResponse(
            content="Hello world",
            model="gpt-4",
            usage=usage,
            raw_response=raw,
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_unknown_usage(self) -> None:
        usage = TokenUsage.unknown()
        d = LLMCallResponse(
            content="test",
            model="gpt-4",
            usage=usage,
            raw_response={},
        ).to_dict()
        assert d["usage"] == {}

    def test_frozen(self) -> None:
        obj = LLMCallResponse(
            content="test",
            model="gpt-4",
            usage=TokenUsage.unknown(),
            raw_response={},
        )
        with pytest.raises(AttributeError):
            obj.content = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LLMCallError
# ---------------------------------------------------------------------------


class TestLLMCallError:
    """LLMCallError.to_dict() produces identical hashes to old dict."""

    def test_retryable_error_hash_stability(self) -> None:
        old_dict = {
            "type": "RateLimitError",
            "message": "429 Too Many Requests",
            "retryable": True,
        }
        new_dict = LLMCallError(
            type="RateLimitError",
            message="429 Too Many Requests",
            retryable=True,
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_non_retryable_error_hash_stability(self) -> None:
        old_dict = {
            "type": "ContentPolicyError",
            "message": "Content policy violation",
            "retryable": False,
        }
        new_dict = LLMCallError(
            type="ContentPolicyError",
            message="Content policy violation",
            retryable=False,
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_frozen(self) -> None:
        obj = LLMCallError(type="err", message="msg", retryable=False)
        with pytest.raises(AttributeError):
            obj.type = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HTTPCallRequest
# ---------------------------------------------------------------------------


class TestHTTPCallRequest:
    """HTTPCallRequest.to_dict() produces identical hashes to old dict."""

    def test_standard_post_hash_stability(self) -> None:
        old_dict: dict[str, object] = {
            "method": "POST",
            "url": "https://api.example.com/v1/data",
            "headers": {"Content-Type": "application/json"},
        }
        old_dict["json"] = {"key": "value"}

        new_dict = HTTPCallRequest(
            method="POST",
            url="https://api.example.com/v1/data",
            headers={"Content-Type": "application/json"},
            json={"key": "value"},
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_standard_get_hash_stability(self) -> None:
        old_dict: dict[str, object] = {
            "method": "GET",
            "url": "https://api.example.com/v1/data",
            "headers": {"Accept": "application/json"},
        }
        old_dict["params"] = {"page": 1}

        new_dict = HTTPCallRequest(
            method="GET",
            url="https://api.example.com/v1/data",
            headers={"Accept": "application/json"},
            params={"page": 1},
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_ssrf_request_hash_stability(self) -> None:
        old_dict = {
            "method": "GET",
            "url": "https://example.com/page",
            "resolved_ip": "93.184.216.34",
            "headers": {"Host": "example.com"},
        }
        new_dict = HTTPCallRequest(
            method="GET",
            url="https://example.com/page",
            headers={"Host": "example.com"},
            resolved_ip="93.184.216.34",
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_redirect_hop_hash_stability(self) -> None:
        old_dict = {
            "method": "GET",
            "url": "https://new.example.com/page",
            "resolved_ip": "1.2.3.4",
            "hop_number": 1,
            "redirect_from": "https://old.example.com/page",
            "headers": {"Host": "new.example.com"},
        }
        new_dict = HTTPCallRequest(
            method="GET",
            url="https://new.example.com/page",
            headers={"Host": "new.example.com"},
            resolved_ip="1.2.3.4",
            hop_number=1,
            redirect_from="https://old.example.com/page",
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_standard_post_always_includes_json(self) -> None:
        d = HTTPCallRequest(
            method="POST",
            url="https://example.com",
            headers={},
            json=None,
        ).to_dict()
        assert "json" in d
        assert d["json"] is None

    def test_standard_get_always_includes_params(self) -> None:
        d = HTTPCallRequest(
            method="GET",
            url="https://example.com",
            headers={},
            params=None,
        ).to_dict()
        assert "params" in d
        assert d["params"] is None

    def test_ssrf_request_excludes_json_params(self) -> None:
        d = HTTPCallRequest(
            method="GET",
            url="https://example.com",
            headers={},
            resolved_ip="1.2.3.4",
        ).to_dict()
        assert "json" not in d
        assert "params" not in d

    def test_frozen(self) -> None:
        obj = HTTPCallRequest(method="GET", url="https://x.com", headers={})
        with pytest.raises(AttributeError):
            obj.method = "POST"  # type: ignore[misc]

    def test_hop_number_without_resolved_ip_raises(self) -> None:
        with pytest.raises(ValueError, match="hop_number requires resolved_ip"):
            HTTPCallRequest(
                method="GET",
                url="https://example.com",
                headers={},
                hop_number=1,
            )

    def test_redirect_from_without_hop_number_raises(self) -> None:
        with pytest.raises(ValueError, match="redirect_from requires hop_number"):
            HTTPCallRequest(
                method="GET",
                url="https://example.com",
                headers={},
                resolved_ip="1.2.3.4",
                redirect_from="https://old.example.com",
            )

    def test_valid_redirect_hop_accepted(self) -> None:
        obj = HTTPCallRequest(
            method="GET",
            url="https://new.example.com",
            headers={},
            resolved_ip="1.2.3.4",
            hop_number=1,
            redirect_from="https://old.example.com",
        )
        assert obj.hop_number == 1


# ---------------------------------------------------------------------------
# HTTPCallResponse
# ---------------------------------------------------------------------------


class TestHTTPCallResponse:
    """HTTPCallResponse.to_dict() produces identical hashes to old dict."""

    def test_standard_response_hash_stability(self) -> None:
        old_dict = {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_size": 42,
            "body": {"result": "ok"},
        }
        new_dict = HTTPCallResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body_size=42,
            body={"result": "ok"},
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_ssrf_response_with_redirects_hash_stability(self) -> None:
        old_dict: dict[str, object] = {
            "status_code": 200,
            "headers": {"content-type": "text/html"},
            "body_size": 1024,
            "body": "<html>...</html>",
        }
        old_dict["redirect_count"] = 2

        new_dict = HTTPCallResponse(
            status_code=200,
            headers={"content-type": "text/html"},
            body_size=1024,
            body="<html>...</html>",
            redirect_count=2,
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_redirect_hop_response_hash_stability(self) -> None:
        old_dict = {
            "status_code": 301,
            "headers": {"location": "https://new.example.com"},
        }
        new_dict = HTTPCallResponse(
            status_code=301,
            headers={"location": "https://new.example.com"},
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_redirect_count_zero_excluded(self) -> None:
        d = HTTPCallResponse(
            status_code=200,
            headers={},
            body_size=0,
            body="",
        ).to_dict()
        assert "redirect_count" not in d

    def test_body_fields_excluded_when_body_size_none(self) -> None:
        d = HTTPCallResponse(
            status_code=301,
            headers={},
        ).to_dict()
        assert "body_size" not in d
        assert "body" not in d

    def test_frozen(self) -> None:
        obj = HTTPCallResponse(status_code=200, headers={})
        with pytest.raises(AttributeError):
            obj.status_code = 404  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HTTPCallError
# ---------------------------------------------------------------------------


class TestHTTPCallError:
    """HTTPCallError.to_dict() produces identical hashes to old dict."""

    def test_http_error_hash_stability(self) -> None:
        old_dict = {
            "type": "HTTPError",
            "message": "HTTP 404",
            "status_code": 404,
        }
        new_dict = HTTPCallError(
            type="HTTPError",
            message="HTTP 404",
            status_code=404,
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_network_error_hash_stability(self) -> None:
        old_dict = {
            "type": "ConnectTimeout",
            "message": "Connection timed out",
        }
        new_dict = HTTPCallError(
            type="ConnectTimeout",
            message="Connection timed out",
        ).to_dict()
        assert new_dict == old_dict
        assert stable_hash(new_dict) == stable_hash(old_dict)

    def test_status_code_none_excluded(self) -> None:
        d = HTTPCallError(
            type="TimeoutError",
            message="timed out",
        ).to_dict()
        assert "status_code" not in d

    def test_frozen(self) -> None:
        obj = HTTPCallError(type="err", message="msg")
        with pytest.raises(AttributeError):
            obj.type = "other"  # type: ignore[misc]
