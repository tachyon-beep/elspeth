"""Tests for security filter middleware (PII shield and classified material filter)."""

from __future__ import annotations

import pytest

from elspeth.core.llm.middleware import LLMRequest
from elspeth.plugins.llms.middleware import ClassifiedMaterialMiddleware, PIIShieldMiddleware

# =====================================================================
# PIIShieldMiddleware Tests
# =====================================================================


def test_pii_shield_detects_email_address() -> None:
    """Test that PII shield detects and blocks email addresses."""
    middleware = PIIShieldMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="You are a helpful assistant.",
        user_prompt="Contact me at john.doe@example.com for more info.",
        metadata={},
    )

    with pytest.raises(ValueError, match="email"):
        middleware.before_request(request)


def test_pii_shield_detects_us_ssn() -> None:
    """Test that PII shield detects US Social Security Numbers."""
    middleware = PIIShieldMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="My SSN is 123-45-6789.",
        metadata={},
    )

    with pytest.raises(ValueError, match="ssn_us"):
        middleware.before_request(request)


def test_pii_shield_detects_phone_number() -> None:
    """Test that PII shield detects US phone numbers."""
    middleware = PIIShieldMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="Call me at (555) 123-4567.",
        metadata={},
    )

    with pytest.raises(ValueError, match="phone_us"):
        middleware.before_request(request)


def test_pii_shield_detects_credit_card() -> None:
    """Test that PII shield detects credit card numbers (with checksum validation)."""
    middleware = PIIShieldMiddleware(on_violation="abort")
    # Using a valid Luhn checksum: 4532015112830366 (test Visa)
    request = LLMRequest(
        system_prompt="",
        user_prompt="My credit card is 4532 0151 1283 0366.",
        metadata={},
    )

    with pytest.raises(ValueError, match="credit_card"):
        middleware.before_request(request)


def test_pii_shield_detects_multiple_pii_types() -> None:
    """Test that PII shield detects multiple PII types in one prompt."""
    middleware = PIIShieldMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="Contact john@example.com or call 555-123-4567.",
        metadata={},
    )

    with pytest.raises(ValueError, match="Prompt contains PII"):
        middleware.before_request(request)


def test_pii_shield_masks_email_when_configured() -> None:
    """Test that PII shield masks email addresses with pseudonyms when on_violation=mask."""
    middleware = PIIShieldMiddleware(on_violation="mask", mask="[REDACTED]")
    request = LLMRequest(
        system_prompt="",
        user_prompt="Contact me at john.doe@example.com for more info.",
        metadata={},
    )

    result = middleware.before_request(request)

    # Email should be replaced with a deterministic pseudonym (EMAIL#HASH format)
    assert "john.doe@example.com" not in result.user_prompt
    assert "EMAIL#" in result.user_prompt
    assert "Contact me at" in result.user_prompt
    assert "for more info." in result.user_prompt


def test_pii_shield_logs_only_when_configured() -> None:
    """Test that PII shield only logs when on_violation=log."""
    middleware = PIIShieldMiddleware(on_violation="log")
    request = LLMRequest(
        system_prompt="",
        user_prompt="Contact john@example.com.",
        metadata={},
    )

    # Should not raise, should return unchanged request
    result = middleware.before_request(request)

    assert result.user_prompt == "Contact john@example.com."


def test_pii_shield_allows_clean_prompts() -> None:
    """Test that PII shield allows prompts without PII."""
    middleware = PIIShieldMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="What is the weather like today?",
        metadata={},
    )

    result = middleware.before_request(request)

    assert result.user_prompt == "What is the weather like today?"


def test_pii_shield_custom_patterns() -> None:
    """Test that PII shield supports custom regex patterns."""
    middleware = PIIShieldMiddleware(
        patterns=[
            {"name": "employee_id", "regex": r"\bEMP-\d{6}\b"},
        ],
        include_defaults=False,
        on_violation="abort",
    )
    request = LLMRequest(
        system_prompt="",
        user_prompt="Look up employee EMP-123456.",
        metadata={},
    )

    with pytest.raises(ValueError, match="employee_id"):
        middleware.before_request(request)


def test_pii_shield_custom_patterns_with_defaults() -> None:
    """Test that custom patterns can be combined with defaults."""
    middleware = PIIShieldMiddleware(
        patterns=[
            {"name": "custom_id", "regex": r"\bCUST-\d{4}\b"},
        ],
        include_defaults=True,
        on_violation="abort",
    )

    # Should detect custom pattern
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="Customer CUST-1234 info.",
        metadata={},
    )
    with pytest.raises(ValueError, match="custom_id"):
        middleware.before_request(request1)

    # Should also detect default pattern (email)
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="Email test@example.com",
        metadata={},
    )
    with pytest.raises(ValueError, match="email"):
        middleware.before_request(request2)


def test_pii_shield_masks_multiple_occurrences() -> None:
    """Test that PII shield masks multiple occurrences with unique pseudonyms."""
    middleware = PIIShieldMiddleware(on_violation="mask", mask="[REDACTED]")
    request = LLMRequest(
        system_prompt="",
        user_prompt="Email alice@example.com or bob@example.org.",
        metadata={},
    )

    result = middleware.before_request(request)

    # Both emails should be replaced with deterministic pseudonyms (EMAIL#HASH format)
    assert result.user_prompt.count("EMAIL#") == 2
    assert "alice@example.com" not in result.user_prompt
    assert "bob@example.org" not in result.user_prompt


def test_pii_shield_handles_invalid_regex_gracefully() -> None:
    """Test that invalid regex patterns are skipped with warning."""
    middleware = PIIShieldMiddleware(
        patterns=[
            {"name": "invalid", "regex": r"(?P<invalid"},  # Invalid regex
            {"name": "valid", "regex": r"\bVALID\b"},
        ],
        include_defaults=False,
        on_violation="abort",
    )

    # Valid pattern should still work
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is VALID text.",
        metadata={},
    )
    with pytest.raises(ValueError, match="valid"):
        middleware.before_request(request)


def test_pii_shield_custom_mask_text() -> None:
    """Test that mask mode uses deterministic pseudonyms (mask parameter no longer used)."""
    middleware = PIIShieldMiddleware(on_violation="mask", mask="***PII***")
    request = LLMRequest(
        system_prompt="",
        user_prompt="Email: test@example.com",
        metadata={},
    )

    result = middleware.before_request(request)

    # Now uses pseudonyms instead of mask string
    assert "EMAIL#" in result.user_prompt
    assert "test@example.com" not in result.user_prompt


def test_pii_shield_custom_channel() -> None:
    """Test that custom logging channel is used."""
    middleware = PIIShieldMiddleware(channel="custom.pii.channel")

    assert middleware.channel == "custom.pii.channel"


# =====================================================================
# PIIShieldMiddleware Tests - Australian PII
# =====================================================================


def test_pii_shield_detects_australian_tfn() -> None:
    """Test that PII shield detects Australian Tax File Numbers.

    Note: TFN and ACN both use 9-digit format, so both may be detected.
    """
    middleware = PIIShieldMiddleware(on_violation="abort")

    # Test with spaces (will match both tfn_au and acn_au due to identical format)
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="My TFN is 123 456 789.",
        metadata={},
    )
    with pytest.raises(ValueError, match="Prompt contains PII"):
        middleware.before_request(request1)

    # Test with hyphens
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="Tax file number: 123-456-789",
        metadata={},
    )
    with pytest.raises(ValueError, match="Prompt contains PII"):
        middleware.before_request(request2)

    # Test without separators
    request3 = LLMRequest(
        system_prompt="",
        user_prompt="TFN: 123456789",
        metadata={},
    )
    with pytest.raises(ValueError, match="Prompt contains PII"):
        middleware.before_request(request3)


def test_pii_shield_detects_australian_abn() -> None:
    """Test that PII shield detects Australian Business Numbers (with checksum validation)."""
    middleware = PIIShieldMiddleware(on_violation="abort")

    # Test with valid ABN and context - Using real ABN: 51 824 753 556 (Atlassian)
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="Company ABN is 51 824 753 556.",
        metadata={},
    )
    with pytest.raises(ValueError, match="abn_au"):
        middleware.before_request(request1)

    # Test with hyphens
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="ABN: 51-824-753-556",
        metadata={},
    )
    with pytest.raises(ValueError, match="abn_au"):
        middleware.before_request(request2)


def test_pii_shield_detects_australian_acn() -> None:
    """Test that PII shield detects Australian Company Numbers.

    Note: TFN and ACN both use 9-digit format, so both may be detected.
    """
    middleware = PIIShieldMiddleware(on_violation="abort")

    # Test with spaces (will match both tfn_au and acn_au due to identical format)
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="ACN: 123 456 789",
        metadata={},
    )
    with pytest.raises(ValueError, match="Prompt contains PII"):
        middleware.before_request(request1)

    # Test without separators
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="Company number 123456789",
        metadata={},
    )
    with pytest.raises(ValueError, match="Prompt contains PII"):
        middleware.before_request(request2)


def test_pii_shield_detects_australian_medicare() -> None:
    """Test that PII shield detects Australian Medicare numbers (with checksum validation)."""
    middleware = PIIShieldMiddleware(on_violation="abort")

    # Using valid Medicare number: 2000 00002 1 (checksum validated: weights [1,3,7,9,1,3,7,9], check digit = sum % 10)
    request = LLMRequest(
        system_prompt="",
        user_prompt="Medicare card: 2000 00002 1",
        metadata={},
    )
    with pytest.raises(ValueError, match="medicare_au"):
        middleware.before_request(request)


def test_pii_shield_detects_australian_phone() -> None:
    """Test that PII shield detects Australian landline phone numbers."""
    middleware = PIIShieldMiddleware(on_violation="abort")

    # Test with area code in brackets
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="Call me on (02) 1234 5678",
        metadata={},
    )
    with pytest.raises(ValueError, match="phone_au"):
        middleware.before_request(request1)

    # Test without brackets
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="Phone: 02 1234 5678",
        metadata={},
    )
    with pytest.raises(ValueError, match="phone_au"):
        middleware.before_request(request2)

    # Test with +61 prefix
    request3 = LLMRequest(
        system_prompt="",
        user_prompt="International: +61 2 1234 5678",
        metadata={},
    )
    with pytest.raises(ValueError, match="phone_au"):
        middleware.before_request(request3)


def test_pii_shield_detects_australian_mobile() -> None:
    """Test that PII shield detects Australian mobile phone numbers."""
    middleware = PIIShieldMiddleware(on_violation="abort")

    # Test standard format
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="Mobile: 0412 345 678",
        metadata={},
    )
    with pytest.raises(ValueError, match="mobile_au"):
        middleware.before_request(request1)

    # Test with +61 prefix
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="Call +61 412 345 678",
        metadata={},
    )
    with pytest.raises(ValueError, match="mobile_au"):
        middleware.before_request(request2)

    # Test without spaces
    request3 = LLMRequest(
        system_prompt="",
        user_prompt="SMS 0412345678",
        metadata={},
    )
    with pytest.raises(ValueError, match="mobile_au"):
        middleware.before_request(request3)


def test_pii_shield_detects_australian_passport() -> None:
    """Test that PII shield detects Australian passport numbers."""
    middleware = PIIShieldMiddleware(on_violation="abort")

    request = LLMRequest(
        system_prompt="",
        user_prompt="Passport number: N1234567",
        metadata={},
    )
    with pytest.raises(ValueError, match="passport_au"):
        middleware.before_request(request)


def test_pii_shield_detects_australian_drivers_license() -> None:
    """Test that PII shield detects Australian driver's license numbers."""
    middleware = PIIShieldMiddleware(on_violation="abort")

    # NSW license (8 digits)
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="NSW License: 12345678",
        metadata={},
    )
    with pytest.raises(ValueError, match="drivers_license_au_nsw"):
        middleware.before_request(request1)

    # VIC license (10 digits)
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="VIC License: 1234567890",
        metadata={},
    )
    with pytest.raises(ValueError, match="drivers_license_au_vic"):
        middleware.before_request(request2)

    # QLD license (9 digits)
    request3 = LLMRequest(
        system_prompt="",
        user_prompt="QLD License: 123456789",
        metadata={},
    )
    with pytest.raises(ValueError, match="drivers_license_au_qld"):
        middleware.before_request(request3)


def test_pii_shield_masks_australian_pii() -> None:
    """Test that Australian PII is masked correctly (with pseudonyms)."""
    middleware = PIIShieldMiddleware(on_violation="mask", mask="[REDACTED]")

    # Using valid ABN with context
    request = LLMRequest(
        system_prompt="",
        user_prompt="Contact via 0412 345 678 or ABN 51 824 753 556.",
        metadata={},
    )

    result = middleware.before_request(request)

    # Both mobile and ABN should be masked with pseudonyms (not the old mask string)
    assert "0412 345 678" not in result.user_prompt
    assert "51 824 753 556" not in result.user_prompt
    # Check that pseudonyms are generated (format: TYPE#HASH)
    assert "#" in result.user_prompt


def test_pii_shield_detects_mixed_australian_and_us_pii() -> None:
    """Test that both Australian and US PII can be detected together."""
    middleware = PIIShieldMiddleware(on_violation="abort")

    request = LLMRequest(
        system_prompt="",
        user_prompt="Email john@example.com, TFN 123 456 789, SSN 123-45-6789.",
        metadata={},
    )

    # Should detect all three types
    with pytest.raises(ValueError, match="Prompt contains PII"):
        middleware.before_request(request)


def test_pii_shield_australian_patterns_can_be_disabled() -> None:
    """Test that default patterns (including Australian) can be disabled."""
    middleware = PIIShieldMiddleware(
        patterns=[
            {"name": "custom_id", "regex": r"\bCUST-\d{4}\b"},
        ],
        include_defaults=False,
        on_violation="abort",
    )

    # Should NOT detect Australian TFN when defaults disabled
    request = LLMRequest(
        system_prompt="",
        user_prompt="TFN: 123 456 789",
        metadata={},
    )

    result = middleware.before_request(request)
    assert result.user_prompt == "TFN: 123 456 789"


# =====================================================================
# ClassifiedMaterialMiddleware Tests
# =====================================================================


def test_classified_material_detects_secret() -> None:
    """Test that classified material middleware detects SECRET marking."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This document is marked SECRET.",
        metadata={},
    )

    with pytest.raises(ValueError, match="SECRET"):
        middleware.before_request(request)


def test_classified_material_detects_top_secret() -> None:
    """Test that classified material middleware detects TOP SECRET marking."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="TOP SECRET: Need to know basis only.",
        metadata={},
    )

    with pytest.raises(ValueError, match="TOP SECRET"):
        middleware.before_request(request)


def test_classified_material_detects_protected() -> None:
    """Test that classified material middleware detects PROTECTED marking."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is PROTECTED information.",
        metadata={},
    )

    with pytest.raises(ValueError, match="PROTECTED"):
        middleware.before_request(request)


def test_classified_material_detects_cabinet_codeword() -> None:
    """Test that classified material middleware detects CABINET CODEWORD marking."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="PROTECTED: CABINET CODEWORD - Eyes only.",
        metadata={},
    )

    with pytest.raises(ValueError, match="PROTECTED: CABINET CODEWORD"):
        middleware.before_request(request)


def test_classified_material_case_insensitive_by_default() -> None:
    """Test that classification detection is case-insensitive by default."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is secret information.",  # lowercase
        metadata={},
    )

    with pytest.raises(ValueError, match="SECRET"):
        middleware.before_request(request)


def test_classified_material_case_sensitive_when_configured() -> None:
    """Test that case-sensitive mode only matches exact case."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort", case_sensitive=True)

    # Should match uppercase
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="This is SECRET information.",
        metadata={},
    )
    with pytest.raises(ValueError, match="SECRET"):
        middleware.before_request(request1)

    # Should NOT match lowercase
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="This is secret information.",
        metadata={},
    )
    result = middleware.before_request(request2)
    assert result.user_prompt == "This is secret information."


def test_classified_material_masks_markings() -> None:
    """Test that classified material middleware masks markings when on_violation=mask."""
    middleware = ClassifiedMaterialMiddleware(on_violation="mask", mask="[REDACTED]")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This document is marked SECRET and CONFIDENTIAL.",
        metadata={},
    )

    result = middleware.before_request(request)

    assert "[REDACTED]" in result.user_prompt
    assert "SECRET" not in result.user_prompt.upper()
    assert "CONFIDENTIAL" not in result.user_prompt.upper()


def test_classified_material_logs_only_when_configured() -> None:
    """Test that classified material middleware only logs when on_violation=log."""
    middleware = ClassifiedMaterialMiddleware(on_violation="log")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is SECRET.",
        metadata={},
    )

    # Should not raise, should return unchanged request
    result = middleware.before_request(request)

    assert result.user_prompt == "This is SECRET."


def test_classified_material_allows_clean_prompts() -> None:
    """Test that classified material middleware allows prompts without markings."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is unclassified public information.",
        metadata={},
    )

    result = middleware.before_request(request)

    assert result.user_prompt == "This is unclassified public information."


def test_classified_material_custom_markings() -> None:
    """Test that classified material middleware supports custom markings."""
    middleware = ClassifiedMaterialMiddleware(
        classification_markings=["ACME INTERNAL", "PROPRIETARY"],
        include_defaults=False,
        on_violation="abort",
    )
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is ACME INTERNAL data.",
        metadata={},
    )

    with pytest.raises(ValueError, match="ACME INTERNAL"):
        middleware.before_request(request)


def test_classified_material_custom_markings_with_defaults() -> None:
    """Test that custom markings can be combined with defaults."""
    middleware = ClassifiedMaterialMiddleware(
        classification_markings=["CUSTOM MARKING"],
        include_defaults=True,
        on_violation="abort",
    )

    # Should detect custom marking
    request1 = LLMRequest(
        system_prompt="",
        user_prompt="This is CUSTOM MARKING data.",
        metadata={},
    )
    with pytest.raises(ValueError, match="CUSTOM MARKING"):
        middleware.before_request(request1)

    # Should also detect default marking
    request2 = LLMRequest(
        system_prompt="",
        user_prompt="This is SECRET data.",
        metadata={},
    )
    with pytest.raises(ValueError, match="SECRET"):
        middleware.before_request(request2)


def test_classified_material_detects_ts_sci() -> None:
    """Test that classified material middleware detects TS//SCI marking."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="Classification: TS//SCI",
        metadata={},
    )

    with pytest.raises(ValueError, match="TS//SCI"):
        middleware.before_request(request)


def test_classified_material_detects_noforn() -> None:
    """Test that classified material middleware detects NOFORN marking."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort")
    request = LLMRequest(
        system_prompt="",
        user_prompt="SECRET//NOFORN - US personnel only.",
        metadata={},
    )

    with pytest.raises(ValueError):
        middleware.before_request(request)


def test_classified_material_custom_mask_text() -> None:
    """Test that custom mask text is applied."""
    middleware = ClassifiedMaterialMiddleware(on_violation="mask", mask="***CLASSIFIED***")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is SECRET data.",
        metadata={},
    )

    result = middleware.before_request(request)

    assert "***CLASSIFIED***" in result.user_prompt


def test_classified_material_custom_channel() -> None:
    """Test that custom logging channel is used."""
    middleware = ClassifiedMaterialMiddleware(channel="custom.classification.channel")

    assert middleware.channel == "custom.classification.channel"


def test_classified_material_masks_multiple_markings() -> None:
    """Test that multiple classification markings are masked."""
    middleware = ClassifiedMaterialMiddleware(on_violation="mask", mask="[REDACTED]")
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is SECRET and CONFIDENTIAL and TOP SECRET.",
        metadata={},
    )

    result = middleware.before_request(request)

    # All three markings should be masked
    assert result.user_prompt.count("[REDACTED]") == 3
    assert "SECRET" not in result.user_prompt.upper() or "[REDACTED]" in result.user_prompt


def test_classified_material_detects_official_sensitive() -> None:
    """Test that OFFICIAL-SENSITIVE marking is detected when include_optional=True."""
    middleware = ClassifiedMaterialMiddleware(on_violation="abort", include_optional=True)
    request = LLMRequest(
        system_prompt="",
        user_prompt="This is OFFICIAL-SENSITIVE information.",
        metadata={},
    )

    with pytest.raises(ValueError, match="OFFICIAL"):
        middleware.before_request(request)
