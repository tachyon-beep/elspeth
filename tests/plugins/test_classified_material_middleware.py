from __future__ import annotations

import pytest

from elspeth.core.base.protocols import LLMRequest
from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.transforms.llm.middleware.classified_material import ClassifiedMaterialMiddleware


def test_abort_on_secret_literal():
    mw = ClassifiedMaterialMiddleware(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_violation="abort",
    )
    req = LLMRequest(system_prompt="S", user_prompt="This contains SECRET marking", metadata={})
    with pytest.raises(ValueError):
        mw.before_request(req)


def test_mask_mode_masks_literal_case_insensitive():
    mw = ClassifiedMaterialMiddleware(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_violation="mask",
        mask="[MASK]",
    )
    req = LLMRequest(system_prompt="S", user_prompt="Leaked secret content", metadata={})
    out = mw.before_request(req)
    assert "[MASK]" in out.user_prompt or "secret" not in out.user_prompt.lower()


def test_severity_threshold_allows_medium_when_min_high():
    mw = ClassifiedMaterialMiddleware(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_violation="abort",
        severity_scoring=True,
        min_severity="HIGH",
    )
    # CONFIDENTIAL is medium severity; should not trigger when min is HIGH
    req = LLMRequest(system_prompt="S", user_prompt="Some confidential memo", metadata={})
    out = mw.before_request(req)
    assert out.user_prompt == req.user_prompt


def test_allcaps_confidence_blocks_lowercase_without_context():
    mw = ClassifiedMaterialMiddleware(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_violation="abort",
        require_allcaps_confidence=True,
        case_sensitive=True,
    )
    req = LLMRequest(system_prompt="S", user_prompt="this contains secret but no strong tokens", metadata={})
    out = mw.before_request(req)
    assert out.user_prompt == req.user_prompt


def test_false_positive_suppressed_inside_code_fence():
    mw = ClassifiedMaterialMiddleware(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_violation="abort",
        check_code_fences=True,
    )
    text = """
    ```
    Here is SECRET inside code fence
    ```
    """
    req = LLMRequest(system_prompt="S", user_prompt=text, metadata={})
    out = mw.before_request(req)
    assert out.user_prompt == req.user_prompt


def test_log_mode_with_regex_detection_returns_request():
    mw = ClassifiedMaterialMiddleware(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_violation="log",
    )
    req = LLMRequest(system_prompt="S", user_prompt="Information REL TO Canada only", metadata={})
    out = mw.before_request(req)
    assert out.user_prompt == req.user_prompt
