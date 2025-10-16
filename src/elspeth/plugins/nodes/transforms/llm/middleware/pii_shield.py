"""PIIShieldMiddleware - LLM middleware plugin."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any, Sequence

from elspeth.core.protocols import LLMMiddleware, LLMRequest
from elspeth.core.registries.middleware import register_middleware
from elspeth.core.security.pii_validators import (
    canonicalize_identifier,
    validate_abn,
    validate_acn,
    validate_bsb,
    validate_luhn,
    validate_medicare,
    validate_tfn,
)

logger = logging.getLogger(__name__)

_PII_SHIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "regex": {"type": "string"},
                    "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "validator": {"type": "string"},
                    "requires_context": {"type": "boolean"},
                    "context_tokens": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "regex"],
            },
        },
        "on_violation": {"type": "string", "enum": ["abort", "mask", "log"]},
        "mask": {"type": "string"},
        "channel": {"type": "string"},
        "include_defaults": {"type": "boolean"},
        "severity_scoring": {"type": "boolean"},
        "min_severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "checksum_validation": {"type": "boolean"},
        "context_boosting": {"type": "boolean"},
        "context_suppression": {"type": "boolean"},
        "blind_review_mode": {"type": "boolean"},
        "redaction_salt": {"type": "string"},
        "bsb_account_window": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": True,
}


class PIIShieldMiddleware(LLMMiddleware):
    """Enhanced PII detection with blind review, checksum validation, and severity scoring.

    Features:
    - Checksum validation for Australian identifiers (TFN, ABN, ACN, Medicare)
    - Luhn algorithm validation for credit cards
    - Severity classification (HIGH/MEDIUM/LOW)
    - Context boosting (proximity to strong tokens like "tfn", "medicare")
    - Context suppression (URLs, code blocks, hex strings)
    - Redaction with deterministic pseudonym generation (SHA-256)
    - Structured output for blind review routing
    - BSB+Account combo detection
    - ARBN pattern detection
    """

    name = "pii_shield"

    # Strong context tokens that boost confidence
    STRONG_TOKENS = [
        "tfn",
        "tax file",
        "tax file number",
        "abn",
        "business number",
        "australian business",
        "acn",
        "company number",
        "australian company",
        "medicare",
        "medicare number",
        "medicare card",
        "ssn",
        "social security",
        "social security number",
        "bsb",
        "bank state branch",
        "account",
        "account number",
        "acct",
        "credit card",
        "card number",
        "visa",
        "mastercard",
        "amex",
        "passport",
        "passport number",
        "driver",
        "driver's license",
        "licence",
        "license",
    ]

    # Suppression patterns (high false-positive contexts)
    SUPPRESSION_PATTERNS = [
        re.compile(r"https?://"),  # URLs
        re.compile(r"www\."),  # URLs
        re.compile(r"0x[0-9a-fA-F]+"),  # Hex strings
        re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),  # UUIDs
    ]

    # Enhanced PII patterns with severity classification
    DEFAULT_PATTERNS = [
        # ============== HIGH SEVERITY ==============
        # Australian Government Identifiers (with checksum validation)
        {
            "name": "tfn_au",
            "regex": r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b",
            "severity": "HIGH",
            "validator": "tfn",
            "requires_context": True,
        },
        {
            "name": "abn_au",
            "regex": r"\b\d{2}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{3}\b",
            "severity": "HIGH",
            "validator": "abn",
            "requires_context": True,
        },
        {
            "name": "acn_au",
            "regex": r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b",
            "severity": "HIGH",
            "validator": "acn",
            "requires_context": True,
        },
        {
            "name": "medicare_au",
            "regex": r"\b\d{4}[-\s]?\d{5}[-\s]?\d{1}\b",
            "severity": "HIGH",
            "validator": "medicare",
            "requires_context": True,
        },
        {
            "name": "arbn_au",
            "regex": r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b",  # Same as ACN format
            "severity": "HIGH",
            "validator": "acn",
            "requires_context": True,
            "context_tokens": ["arbn", "australian registered body"],
        },
        # Credit cards (with Luhn validation)
        {
            "name": "credit_card",
            "regex": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
            "severity": "HIGH",
            "validator": "luhn",
            "requires_context": True,
        },
        # US Social Security
        {
            "name": "ssn_us",
            "regex": r"\b\d{3}-\d{2}-\d{4}\b",
            "severity": "HIGH",
            "requires_context": False,
        },
        {
            "name": "ssn_us_no_dash",
            "regex": r"\b\d{9}\b",
            "severity": "HIGH",
            "requires_context": True,
        },
        # ============== MEDIUM SEVERITY ==============
        # Contact information
        {
            "name": "email",
            "regex": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "severity": "MEDIUM",
            "requires_context": False,
        },
        {
            "name": "phone_us",
            "regex": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
            "severity": "MEDIUM",
            "requires_context": False,
        },
        {
            "name": "phone_au",
            "regex": r"(?:\+61[-.\s]?[2-478]|\(0?[2-478]\)|0[2-478])[-.\s]?\d{4}[-.\s]?\d{4}",
            "severity": "MEDIUM",
            "requires_context": False,
        },
        {
            "name": "mobile_au",
            "regex": r"\b(?:\+?61[-.\s]?)?0?4\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b",
            "severity": "MEDIUM",
            "requires_context": False,
        },
        # Identity documents
        {
            "name": "passport_us",
            "regex": r"\b[A-Z]{1,2}\d{6,9}\b",
            "severity": "MEDIUM",
            "requires_context": True,
        },
        {
            "name": "passport_au",
            "regex": r"\b[A-Z]\d{7}\b",
            "severity": "MEDIUM",
            "requires_context": True,
        },
        {
            "name": "uk_ni_number",
            "regex": r"\b[A-Z]{2}\d{6}[A-D]\b",
            "severity": "MEDIUM",
            "requires_context": False,
        },
        # Driver's licenses (ambiguous patterns)
        {
            "name": "drivers_license_au_nsw",
            "regex": r"\b\d{8}\b",
            "severity": "MEDIUM",
            "requires_context": True,
        },
        {
            "name": "drivers_license_au_vic",
            "regex": r"\b\d{10}\b",
            "severity": "MEDIUM",
            "requires_context": True,
        },
        {
            "name": "drivers_license_au_qld",
            "regex": r"\b\d{9}\b",
            "severity": "MEDIUM",
            "requires_context": True,
        },
        # Banking (BSB)
        {
            "name": "bsb_au",
            "regex": r"\b\d{3}[-\s]?\d{3}\b",
            "severity": "MEDIUM",
            "validator": "bsb",
            "requires_context": True,
        },
        # ============== LOW SEVERITY ==============
        {
            "name": "ip_address",
            "regex": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "severity": "LOW",
            "requires_context": False,
        },
    ]

    def __init__(
        self,
        *,
        patterns: Sequence[dict[str, Any]] | None = None,
        on_violation: str = "abort",
        mask: str = "[PII REDACTED]",
        channel: str | None = None,
        include_defaults: bool = True,
        severity_scoring: bool = True,
        min_severity: str = "LOW",
        checksum_validation: bool = True,
        context_boosting: bool = True,
        context_suppression: bool = True,
        blind_review_mode: bool = False,
        redaction_salt: str | None = None,
        bsb_account_window: int = 80,
    ):
        """Initialize enhanced PII shield middleware.

        Args:
            patterns: Custom PII patterns (dicts with 'name', 'regex', 'severity', etc.)
            on_violation: Action on detection - 'abort', 'mask', or 'log'
            mask: Replacement text when masking (not used in blind review)
            channel: Logging channel name
            include_defaults: Whether to include default PII patterns
            severity_scoring: Enable severity classification
            min_severity: Minimum severity to trigger violation (HIGH/MEDIUM/LOW)
            checksum_validation: Validate Australian identifiers with checksums
            context_boosting: Use proximity to strong tokens to boost confidence
            context_suppression: Suppress matches in URLs, code blocks, etc.
            blind_review_mode: Enable blind review routing (HIGH+MEDIUM → manual)
            redaction_salt: Salt for deterministic pseudonym generation
            bsb_account_window: Max distance (chars) for BSB+Account combo detection
        """
        mode = (on_violation or "abort").lower()
        if mode not in {"abort", "mask", "log"}:
            mode = "abort"
        self.mode = mode
        self.mask = mask
        self.channel = channel or "elspeth.pii_shield"
        self.severity_scoring = severity_scoring
        self.min_severity = min_severity.upper() if min_severity else "HIGH"
        self.checksum_validation = checksum_validation
        self.context_boosting = context_boosting
        self.context_suppression = context_suppression
        self.blind_review_mode = blind_review_mode
        self.redaction_salt = redaction_salt or os.environ.get("PII_REDACTION_SALT", "elspeth-default-salt")
        self.bsb_account_window = bsb_account_window

        # Build pattern list
        all_patterns = []
        if include_defaults:
            all_patterns.extend(self.DEFAULT_PATTERNS)
        if patterns:
            all_patterns.extend(patterns)

        # Compile regex patterns with metadata
        self.patterns: list[tuple[str, re.Pattern[str], dict[str, Any]]] = []
        for pattern_def in all_patterns:
            try:
                # Cast pattern_def values from object to proper types
                regex_str = str(pattern_def["regex"])
                name_str = str(pattern_def["name"])
                compiled = re.compile(regex_str)
                metadata: dict[str, Any] = {
                    "severity": pattern_def.get("severity", "HIGH"),
                    "validator": pattern_def.get("validator"),
                    "requires_context": pattern_def.get("requires_context", False),
                    "context_tokens": pattern_def.get("context_tokens", []),
                }
                self.patterns.append((name_str, compiled, metadata))
            except re.error as exc:
                logger.warning(
                    "[%s] Invalid regex pattern '%s': %s",
                    self.channel,
                    pattern_def.get("name", "unknown"),
                    exc,
                )

    def _validate_checksum(self, pii_type: str, value: str) -> bool:
        """Validate PII value using checksum algorithms.

        Returns:
            True if checksum is valid, False otherwise
        """
        if not self.checksum_validation:
            return True  # Assume valid if validation disabled

        value_clean = canonicalize_identifier(value)

        if pii_type == "tfn":
            return validate_tfn(value_clean)
        elif pii_type == "abn":
            return validate_abn(value_clean)
        elif pii_type == "acn":
            return validate_acn(value_clean)
        elif pii_type == "medicare":
            return validate_medicare(value_clean)
        elif pii_type == "luhn":
            return validate_luhn(value_clean)
        elif pii_type == "bsb":
            return validate_bsb(value_clean)

        return True  # No validator, assume valid

    def _check_context_boost(self, text: str, match_start: int, match_end: int) -> bool:
        """Check if match has strong context tokens nearby (±40 chars).

        Returns:
            True if strong context found, False otherwise
        """
        if not self.context_boosting:
            return False

        # Extract context window (±40 chars)
        context_start = max(0, match_start - 40)
        context_end = min(len(text), match_end + 40)
        context = text[context_start:context_end].lower()

        # Check for strong tokens
        for token in self.STRONG_TOKENS:
            if token in context:
                return True

        return False

    def _check_context_suppression(self, text: str, match_start: int, match_end: int) -> bool:
        """Check if match is in suppression context (URLs, code, hex).

        Returns:
            True if match should be suppressed, False otherwise
        """
        if not self.context_suppression:
            return False

        # Check if inside markdown code fence
        before_text = text[:match_start]
        fence_count = before_text.count("```")
        if fence_count % 2 == 1:
            return True

        # Check if inside inline code
        if "`" in before_text:
            last_backtick = before_text.rfind("`")
            if last_backtick > before_text.rfind(" "):
                after_text = text[match_end:]
                if "`" in after_text:
                    return True

        # Check suppression patterns
        context_start = max(0, match_start - 20)
        context_end = min(len(text), match_end + 20)
        context = text[context_start:context_end]

        for pattern in self.SUPPRESSION_PATTERNS:
            if pattern.search(context):
                return True

        return False

    def _generate_pseudonym(self, pii_type: str, value: str) -> str:
        """Generate deterministic pseudonym for PII value.

        Returns:
            Pseudonym like "ABN#Q2tbSg" or "TFN#7xY9Kp"
        """
        # Hash value with salt
        hash_input = f"{self.redaction_salt}:{value}".encode("utf-8")
        hash_digest = hashlib.sha256(hash_input).digest()

        # Take first 6 bytes, encode as base64, strip padding
        import base64

        token = base64.b64encode(hash_digest[:6]).decode("ascii").rstrip("=")

        # Format as type#token
        type_abbrev = pii_type.upper().replace("_AU", "").replace("_US", "")
        return f"{type_abbrev}#{token}"

    def _detect_bsb_account_combo(self, text: str) -> list[tuple[int, int, str, str]]:
        """Detect BSB+Account number combinations within window.

        Returns:
            List of (start, end, bsb_value, account_value) tuples
        """
        combos = []

        # Find all BSB matches
        bsb_pattern = re.compile(r"\b\d{3}[-\s]?\d{3}\b")
        bsb_matches = list(bsb_pattern.finditer(text))

        # Find account number patterns (6-10 digits)
        account_pattern = re.compile(r"\b\d{6,10}\b")
        account_matches = list(account_pattern.finditer(text))

        # Check for BSB+Account pairs within window
        for bsb_match in bsb_matches:
            for account_match in account_matches:
                distance = abs(bsb_match.start() - account_match.start())
                if distance <= self.bsb_account_window:
                    # Found a combo
                    start = min(bsb_match.start(), account_match.start())
                    end = max(bsb_match.end(), account_match.end())
                    bsb_value = bsb_match.group(0)
                    account_value = account_match.group(0)
                    combos.append((start, end, bsb_value, account_value))

        return combos

    def before_request(self, request: LLMRequest) -> LLMRequest:
        """Scan prompt for PII with enhanced detection and blind review routing."""
        text = request.user_prompt

        # Detection results with metadata
        findings: list[dict[str, Any]] = []

        # 1. Pattern-based detection
        for name, pattern, metadata in self.patterns:
            for match in pattern.finditer(text):
                match_value = match.group(0)
                match_start = match.start()
                match_end = match.end()

                # Check context suppression
                if self._check_context_suppression(text, match_start, match_end):
                    continue

                # Check if context boosting required
                requires_context = metadata["requires_context"]
                has_context = self._check_context_boost(text, match_start, match_end)

                if requires_context and not has_context:
                    # Check for pattern-specific context tokens
                    context_tokens = metadata.get("context_tokens", [])
                    if context_tokens:
                        context_window = text[max(0, match_start - 40) : min(len(text), match_end + 40)].lower()
                        if not any(token in context_window for token in context_tokens):
                            continue  # Skip without context
                    else:
                        continue  # Skip without context

                # Checksum validation
                validator = metadata.get("validator")
                if validator:
                    if not self._validate_checksum(validator, match_value):
                        continue  # Skip invalid checksum

                # Valid detection - record finding
                severity = metadata["severity"] if self.severity_scoring else "HIGH"
                pseudonym = self._generate_pseudonym(name, match_value)

                findings.append(
                    {
                        "type": name,
                        "severity": severity,
                        "offset": match_start,
                        "length": len(match_value),
                        "value": match_value,
                        "hash": pseudonym,
                    }
                )

        # 2. BSB+Account combo detection
        combos = self._detect_bsb_account_combo(text)
        for start, end, bsb_val, acct_val in combos:
            # Check if already detected individually
            already_detected = any(f["offset"] == start or f["offset"] == end for f in findings)
            if not already_detected:
                combo_value = f"{bsb_val}+{acct_val}"
                pseudonym = self._generate_pseudonym("bsb_account", combo_value)
                findings.append(
                    {
                        "type": "bsb_account_combo",
                        "severity": "HIGH",
                        "offset": start,
                        "length": end - start,
                        "value": combo_value,
                        "hash": pseudonym,
                    }
                )

        # 3. Calculate severity counts and max severity
        if findings:
            severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            for finding in findings:
                severity_counts[finding["severity"]] += 1

            max_severity = "LOW"
            if severity_counts["HIGH"] > 0:
                max_severity = "HIGH"
            elif severity_counts["MEDIUM"] > 0:
                max_severity = "MEDIUM"

            # Check if severity meets threshold
            severity_levels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            if severity_levels[max_severity] < severity_levels[self.min_severity]:
                # Below threshold, don't trigger violation
                logger.debug(
                    "[%s] Detected PII below threshold: %d findings (severity=%s, min=%s)",
                    self.channel,
                    len(findings),
                    max_severity,
                    self.min_severity,
                )
                return request

            # 4. Generate redacted preview (for blind review)
            redacted_preview = text
            # Sort findings by offset (descending) to avoid offset issues
            for finding in sorted(findings, key=lambda f: f["offset"], reverse=True):
                start = finding["offset"]
                end = start + finding["length"]
                redacted_preview = redacted_preview[:start] + finding["hash"] + redacted_preview[end:]

            # 5. Create structured output for routing
            routing_output = {
                "route": "manual_review" if self.blind_review_mode else "blocked",
                "severity": max_severity,
                "counts": severity_counts,
                "findings": [
                    {
                        "type": f["type"],
                        "severity": f["severity"],
                        "offset": f["offset"],
                        "length": f["length"],
                        "hash": f["hash"],
                    }
                    for f in findings
                ],
                "redacted_preview": redacted_preview[:500],  # Truncate for logging
                "meta": {
                    "engine": "pii-tripwire/1.3",
                    "blind_mode": self.blind_review_mode,
                    "checksum_validation": self.checksum_validation,
                    "context_boosting": self.context_boosting,
                },
            }

            # 6. Log detection with severity
            pii_types = {f["type"] for f in findings}
            logger.warning(
                "[%s] Detected PII in prompt: %s (%d findings, severity=%s)",
                self.channel,
                ", ".join(sorted(pii_types)),
                len(findings),
                max_severity,
            )

            # Log structured output for blind review queue
            if self.blind_review_mode:
                logger.info("[%s] Blind review routing: %s", self.channel, routing_output)

            # 7. Take action based on mode
            if self.mode == "abort":
                # In blind review mode, only abort on HIGH severity
                if self.blind_review_mode and max_severity != "HIGH":
                    # Route to manual review instead of aborting
                    logger.info(
                        "[%s] Routing to manual review (severity=%s): %s",
                        self.channel,
                        max_severity,
                        routing_output,
                    )
                    return request

                raise ValueError(f"Prompt contains PII (severity={max_severity}): {', '.join(sorted(pii_types))}")

            if self.mode == "mask":
                # Return redacted version
                return request.clone(user_prompt=redacted_preview)

        return request


register_middleware(
    "pii_shield",
    lambda options, context: PIIShieldMiddleware(
        patterns=options.get("patterns"),
        on_violation=options.get("on_violation", "abort"),
        mask=options.get("mask", "[PII REDACTED]"),
        channel=options.get("channel"),
        include_defaults=options.get("include_defaults", True),
        severity_scoring=options.get("severity_scoring", True),
        min_severity=options.get("min_severity", "LOW"),
        checksum_validation=options.get("checksum_validation", True),
        context_boosting=options.get("context_boosting", True),
        context_suppression=options.get("context_suppression", True),
        blind_review_mode=options.get("blind_review_mode", False),
        redaction_salt=options.get("redaction_salt"),
        bsb_account_window=options.get("bsb_account_window", 80),
    ),
    schema=_PII_SHIELD_SCHEMA,
)


__all__ = ["PIIShieldMiddleware"]
