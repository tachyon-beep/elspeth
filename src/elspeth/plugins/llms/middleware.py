"""Default LLM middleware implementations."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import unicodedata
from collections import deque
from typing import Any, Dict, Sequence

import requests

from elspeth.core.llm.middleware import LLMMiddleware, LLMRequest
from elspeth.core.llm.registry import register_middleware
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


_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "include_prompts": {"type": "boolean"},
        "channel": {"type": "string"},
    },
    "additionalProperties": True,
}

_PROMPT_SHIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "denied_terms": {"type": "array", "items": {"type": "string"}},
        "mask": {"type": "string"},
        "on_violation": {"type": "string", "enum": ["abort", "mask", "log"]},
        "channel": {"type": "string"},
    },
    "additionalProperties": True,
}

_HEALTH_SCHEMA = {
    "type": "object",
    "properties": {
        "heartbeat_interval": {"type": "number", "minimum": 0.0},
        "stats_window": {"type": "integer", "minimum": 1},
        "channel": {"type": "string"},
        "include_latency": {"type": "boolean"},
    },
    "additionalProperties": True,
}

_CONTENT_SAFETY_SCHEMA = {
    "type": "object",
    "properties": {
        "endpoint": {"type": "string"},
        "key": {"type": "string"},
        "key_env": {"type": "string"},
        "api_version": {"type": "string"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "severity_threshold": {"type": "integer", "minimum": 0, "maximum": 7},
        "on_violation": {"type": "string", "enum": ["abort", "mask", "log"]},
        "mask": {"type": "string"},
        "channel": {"type": "string"},
        "on_error": {"type": "string", "enum": ["abort", "skip"]},
    },
    "required": ["endpoint"],
    "additionalProperties": True,
}

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

_CLASSIFIED_MATERIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "classification_markings": {"type": "array", "items": {"type": "string"}},
        "on_violation": {"type": "string", "enum": ["abort", "mask", "log"]},
        "mask": {"type": "string"},
        "channel": {"type": "string"},
        "case_sensitive": {"type": "boolean"},
        "include_defaults": {"type": "boolean"},
        "include_optional": {"type": "boolean"},
        "fuzzy_matching": {"type": "boolean"},
        "severity_scoring": {"type": "boolean"},
        "min_severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "check_code_fences": {"type": "boolean"},
        "require_allcaps_confidence": {"type": "boolean"},
    },
    "additionalProperties": True,
}


class AuditMiddleware(LLMMiddleware):
    name = "audit_logger"

    def __init__(self, *, include_prompts: bool = False, channel: str | None = None):
        self.include_prompts = include_prompts
        self.channel = channel or "elspeth.audit"

    def before_request(self, request: LLMRequest) -> LLMRequest:
        payload = {"metadata": request.metadata}
        if self.include_prompts:
            payload.update({"system": request.system_prompt, "user": request.user_prompt})
        logger.info("[%s] LLM request metadata=%s", self.channel, payload)
        return request

    def after_response(self, request: LLMRequest, response: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("[%s] LLM response metrics=%s", self.channel, response.get("metrics"))
        if self.include_prompts:
            logger.debug("[%s] LLM response content=%s", self.channel, response.get("content"))
        return response


class PromptShieldMiddleware(LLMMiddleware):
    name = "prompt_shield"

    def __init__(
        self,
        *,
        denied_terms: Sequence[str] | None = None,
        mask: str = "[REDACTED]",
        on_violation: str = "abort",
        channel: str | None = None,
    ):
        self.denied_terms = [term.lower() for term in denied_terms or []]
        self.mask = mask
        mode = (on_violation or "abort").lower()
        if mode not in {"abort", "mask", "log"}:
            mode = "abort"
        self.mode = mode
        self.channel = channel or "elspeth.prompt_shield"

    def before_request(self, request: LLMRequest) -> LLMRequest:
        lowered = request.user_prompt.lower()
        for term in self.denied_terms:
            if term and term in lowered:
                logger.warning("[%s] Prompt contains blocked term '%s'", self.channel, term)
                if self.mode == "abort":
                    raise ValueError(f"Prompt contains blocked term '{term}'")
                if self.mode == "mask":
                    masked = request.user_prompt.replace(term, self.mask)
                    return request.clone(user_prompt=masked)
                break
        return request


class HealthMonitorMiddleware(LLMMiddleware):
    """Emit heartbeat logs summarising middleware activity."""

    name = "health_monitor"

    def __init__(
        self,
        *,
        heartbeat_interval: float = 60.0,
        stats_window: int = 50,
        channel: str | None = None,
        include_latency: bool = True,
    ) -> None:
        if heartbeat_interval < 0:
            raise ValueError("heartbeat_interval must be non-negative")
        self.interval = float(heartbeat_interval)
        self.window = max(int(stats_window), 1)
        self.channel = channel or "elspeth.health"
        self.include_latency = include_latency
        self._lock = threading.Lock()
        self._latencies: deque[float] = deque(maxlen=self.window)
        self._inflight: Dict[int, float] = {}
        self._total_requests = 0
        self._total_failures = 0
        self._last_heartbeat = time.monotonic()

    def before_request(self, request: LLMRequest) -> LLMRequest:
        start = time.monotonic()
        with self._lock:
            self._inflight[id(request)] = start
        return request

    def after_response(self, request: LLMRequest, response: Dict[str, Any]) -> Dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            start = self._inflight.pop(id(request), None)
            self._total_requests += 1
            if isinstance(response, dict) and response.get("error"):
                self._total_failures += 1
            if start is not None and self.include_latency:
                self._latencies.append(now - start)
            if self.interval == 0 or now - self._last_heartbeat >= self.interval:
                self._emit(now)
        return response

    def _emit(self, now: float) -> None:
        data: Dict[str, Any] = {
            "requests": self._total_requests,
            "failures": self._total_failures,
        }
        if self._total_requests:
            data["failure_rate"] = self._total_failures / self._total_requests
        if self.include_latency and self._latencies:
            latencies = list(self._latencies)
            count = len(latencies)
            total = sum(latencies)
            data.update(
                {
                    "latency_count": count,
                    "latency_avg": total / count,
                    "latency_min": min(latencies),
                    "latency_max": max(latencies),
                }
            )
        logger.info("[%s] health heartbeat %s", self.channel, data)
        self._last_heartbeat = now


class AzureContentSafetyMiddleware(LLMMiddleware):
    """Use Azure Content Safety service to screen prompts before submission."""

    name = "azure_content_safety"

    def __init__(
        self,
        *,
        endpoint: str,
        key: str | None = None,
        key_env: str | None = None,
        api_version: str | None = None,
        categories: Sequence[str] | None = None,
        severity_threshold: int = 4,
        on_violation: str = "abort",
        mask: str = "[CONTENT BLOCKED]",
        channel: str | None = None,
        on_error: str = "abort",
    ) -> None:
        if not endpoint:
            raise ValueError("Azure Content Safety requires an endpoint")
        self.endpoint = endpoint.rstrip("/")
        key_value = key or (os.environ.get(key_env) if key_env else None)
        if not key_value:
            raise ValueError("Azure Content Safety requires an API key or key_env")
        self.key = key_value
        self.api_version = api_version or "2023-10-01"
        self.categories = list(categories or ["Hate", "Violence", "SelfHarm", "Sexual"])
        self.threshold = max(0, min(int(severity_threshold), 7))
        mode = (on_violation or "abort").lower()
        if mode not in {"abort", "mask", "log"}:
            mode = "abort"
        self.mode = mode
        self.mask = mask
        self.channel = channel or "elspeth.azure_content_safety"
        handler = (on_error or "abort").lower()
        if handler not in {"abort", "skip"}:
            handler = "abort"
        self.on_error = handler

    def before_request(self, request: LLMRequest) -> LLMRequest:
        try:
            result = self._analyze_text(request.user_prompt)
        except Exception as exc:  # pragma: no cover - network failure path
            if self.on_error == "skip":
                logger.warning("[%s] Content Safety call failed; skipping (%s)", self.channel, exc)
                return request
            raise

        if result.get("flagged"):
            logger.warning("[%s] Prompt flagged by Azure Content Safety: %s", self.channel, result)
            if self.mode == "abort":
                raise ValueError("Prompt blocked by Azure Content Safety")
            if self.mode == "mask":
                return request.clone(user_prompt=self.mask)
        return request

    def _analyze_text(self, text: str) -> Dict[str, Any]:
        url = f"{self.endpoint}/contentsafety/text:analyze?api-version={self.api_version}"
        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self.key,
        }
        payload = {
            "text": text,
            "categories": self.categories,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        flagged = False
        max_severity = 0
        for item in data.get("results", data.get("categories", [])):
            severity = int(item.get("severity", 0))
            max_severity = max(max_severity, severity)
            if severity >= self.threshold:
                flagged = True
        return {"flagged": flagged, "max_severity": max_severity, "raw": data}


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
        patterns: Sequence[Dict[str, Any]] | None = None,
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
        self.patterns: list[tuple[str, re.Pattern[str], Dict[str, Any]]] = []
        for pattern_def in all_patterns:
            try:
                compiled = re.compile(pattern_def["regex"])
                metadata = {
                    "severity": pattern_def.get("severity", "HIGH"),
                    "validator": pattern_def.get("validator"),
                    "requires_context": pattern_def.get("requires_context", False),
                    "context_tokens": pattern_def.get("context_tokens", []),
                }
                self.patterns.append((pattern_def["name"], compiled, metadata))
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
        findings: list[Dict[str, Any]] = []

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


class ClassifiedMaterialMiddleware(LLMMiddleware):
    """Detect and block classified material markings in prompts with advanced fuzzy matching.

    Features:
    - Unicode normalization (NFKC) and homoglyph detection
    - Fuzzy regex matching for spacing variants (A.U.S.T.E.O)
    - Severity scoring (HIGH/MEDIUM/LOW)
    - False-positive dampers (code fence detection, all-caps requirement)
    - REL TO country-list parsing
    """

    name = "classified_material"

    # High-signal literal markings (case-insensitive after normalization)
    DEFAULT_MARKINGS = [
        # Australian Government (current PSPF-era)
        "PROTECTED",
        "SECRET",
        "TOP SECRET",
        # Cabinet handling (AU)
        "CABINET",
        "CABINET CODEWORD",
        "PROTECTED: CABINET",
        "PROTECTED: CABINET CODEWORD",
        "CABINET-IN-CONFIDENCE",
        "CABINET IN CONFIDENCE",
        "NATIONAL CABINET",
        "CABINET SENSITIVE",
        # AU caveats / releasability
        "AUSTEO",  # Australian Eyes Only
        "AGAO",  # Australian Government Access Only
        "REL TO",  # Releasable To (check countries with regex)
        "REL AUS",
        "REL FVEY",
        "FVEY",  # Five Eyes
        # Coalition / US control systems & caveats
        "TS//SCI",
        "TS/SCI",
        "SCI",
        "NOFORN",
        "ORCON",
        "RELIDO",
        # Note: SI, HCS, TK are handled by regex patterns with context requirements
        # US/UK legacy or still-seen
        "CONFIDENTIAL",
        "RESTRICTED",
        "FOUO",  # US legacy
        "CUI",  # US unclassified controlled
        # "Eyes only" phrasings
        "UK EYES ONLY",
        "CANADIAN EYES ONLY",
        "US EYES ONLY",
        "AUS EYES ONLY",
        "NZ EYES ONLY",
        # NATO
        "COSMIC TOP SECRET",
        "NATO SECRET",
        "NATO CONFIDENTIAL",
        "NATO RESTRICTED",
    ]

    # Optional low-signal markings (can be noisy)
    OPTIONAL_LOW_SIGNAL = [
        "OFFICIAL: Sensitive",  # AU official-level caveat (OSENS)
        "OFFICIAL-SENSITIVE",  # UK variant
        "SENSITIVE BUT UNCLASSIFIED",
        "SBU",
        "LAW ENFORCEMENT SENSITIVE",
        "LES",
    ]

    # Homoglyph map (common unicode lookalikes to ASCII)
    HOMOGLYPHS = {
        # Cyrillic to Latin
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        # Greek to Latin
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Ζ": "Z",
        "Η": "H",
        "Ι": "I",
        "Κ": "K",
        "Μ": "M",
        "Ν": "N",
        "Ο": "O",
        "Ρ": "P",
        "Τ": "T",
        "Υ": "Y",
        "Χ": "X",
    }

    # REL TO country code canonicalization
    REL_TO_CANON = {
        "aus": "AUS",
        "australia": "AUS",
        "can": "CAN",
        "canada": "CAN",
        "gbr": "GBR",
        "uk": "GBR",
        "united kingdom": "GBR",
        "great britain": "GBR",
        "nzl": "NZL",
        "new zealand": "NZL",
        "usa": "USA",
        "us": "USA",
        "united states": "USA",
        "fvey": "FVEY",
        "five eyes": "FVEY",
    }

    # Fuzzy regex patterns
    REGEX_PATTERNS = {
        # Banner structure: "classification // caveat // codeword"
        "banner_segments": r"\b(top\s*secret|secret|protected)\s*//\s*[\w-]{2,}(?:\s*//\s*[\w-]{2,})*",
        # AU caveats (tolerant to spacing/punctuation)
        "austeo": r"\ba\s*[\.:\s]*u\s*[\.:\s]*s\s*[\.:\s]*t\s*[\.:\s]*e\s*[\.:\s]*o\b",
        "agao": r"\ba\s*[\.:\s]*g\s*[\.:\s]*a\s*[\.:\s]*o\b",
        # Eyes-only (generic)
        "eyes_only": r"\b([a-z]{2,3}|uk|us|usa|aus|gbr|nzl|can|ca)\s+eyes\s+only\b",
        # REL TO with country list
        "rel_to_line": r"\brel(?:easable)?\s*to\b\s*([a-z ,/()]+)",
        "rel_to_token": r"\b(aus|australia|can|canada|gbr|uk|united\s*kingdom|nzl|new\s*zealand|usa|us|united\s*states|fvey|five\s*eyes)\b",
        # US/coalition caveats
        "noforn": r"\bn\s*[\.:\s]*o\s*[\.:\s]*f\s*[\.:\s]*o\s*[\.:\s]*r\s*[\.:\s]*n\b",
        "orcon": r"\bo\s*[\.:\s]*r\s*[\.:\s]*c\s*[\.:\s]*o\s*[\.:\s]*n\b",
        "sci": r"\bts\s*[/]*\s*[/]*\s*sci\b|\bsensitive\s*compartmented\s*information\b",
        # SCI control systems - require proximity to classification markers to avoid false positives
        "si": r"(?:ts|secret|top\s*secret)[\s/]*(?://)?[\s/]*si(?:\b|//)",
        "hcs": r"(?:ts|secret|top\s*secret)[\s/]*(?://)?[\s/]*hcs(?:\b|//)",
        "tk": r"(?:ts|secret|top\s*secret)[\s/]*(?://)?[\s/]*tk(?:\b|//)",
        # Cabinet handling
        "cabinet": r"\bcabinet(?:[-\s]in[-\s]confidence|[-\s]codeword|[-\s]sensitive)?\b",
        "national_cabinet": r"\bnational\s*cabinet\b",
    }

    def __init__(
        self,
        *,
        classification_markings: Sequence[str] | None = None,
        on_violation: str = "abort",
        mask: str = "[CLASSIFIED]",
        channel: str | None = None,
        case_sensitive: bool = False,
        include_defaults: bool = True,
        include_optional: bool = False,
        fuzzy_matching: bool = True,
        severity_scoring: bool = True,
        min_severity: str = "LOW",
        check_code_fences: bool = True,
        require_allcaps_confidence: bool = False,
    ):
        """Initialize enhanced classified material middleware.

        Args:
            classification_markings: Custom classification markings to detect
            on_violation: Action on detection - 'abort', 'mask', or 'log'
            mask: Replacement text when masking
            channel: Logging channel name
            case_sensitive: Whether matching should be case-sensitive
            include_defaults: Whether to include default high-signal markings
            include_optional: Whether to include optional low-signal markings (OFFICIAL)
            fuzzy_matching: Enable fuzzy regex matching for spacing variants
            severity_scoring: Enable severity scoring (HIGH/MEDIUM/LOW)
            min_severity: Minimum severity to trigger violation (HIGH/MEDIUM/LOW)
            check_code_fences: Apply false-positive dampers for code fences
            require_allcaps_confidence: Require ALL-CAPS or proximity to trigger on single words
        """
        mode = (on_violation or "abort").lower()
        if mode not in {"abort", "mask", "log"}:
            mode = "abort"
        self.mode = mode
        self.mask = mask
        self.channel = channel or "elspeth.classified_material"
        self.case_sensitive = case_sensitive
        self.fuzzy_matching = fuzzy_matching
        self.severity_scoring = severity_scoring
        self.min_severity = min_severity.upper() if min_severity else "LOW"
        self.check_code_fences = check_code_fences
        self.require_allcaps_confidence = require_allcaps_confidence

        # Build marking list
        markings = []
        if include_defaults:
            markings.extend(self.DEFAULT_MARKINGS)
        if include_optional:
            markings.extend(self.OPTIONAL_LOW_SIGNAL)
        if classification_markings:
            markings.extend(classification_markings)

        # Normalize for matching
        if not case_sensitive:
            self.markings = [m.upper() for m in markings]
        else:
            self.markings = list(markings)

        # Compile regex patterns if fuzzy matching enabled
        self.regex_compiled: Dict[str, re.Pattern[str]] = {}
        if self.fuzzy_matching:
            for name, pattern in self.REGEX_PATTERNS.items():
                try:
                    self.regex_compiled[name] = re.compile(pattern, re.IGNORECASE)
                except re.error as exc:
                    logger.warning("[%s] Invalid regex pattern '%s': %s", self.channel, name, exc)

    def _normalize_text(self, text: str) -> tuple[str, str]:
        """Normalize text with unicode NFKC and create punctuation-stripped shadow.

        Returns:
            Tuple of (normalized_text, punctuation_stripped_shadow)
        """
        # NFKC unicode normalization
        normalized = unicodedata.normalize("NFKC", text)

        # Apply homoglyph map
        chars = []
        for char in normalized:
            chars.append(self.HOMOGLYPHS.get(char, char))
        normalized = "".join(chars)

        # Create punctuation-stripped shadow (collapse whitespace, remove punctuation)
        shadow = re.sub(r"[^\w\s]", "", normalized)
        shadow = re.sub(r"\s+", " ", shadow)

        return normalized, shadow

    def _calculate_severity(self, matches: list[tuple[str, str]]) -> str:
        """Calculate severity score for detected markings.

        Returns:
            "HIGH", "MEDIUM", or "LOW"
        """
        if not self.severity_scoring:
            return "HIGH"  # Default to HIGH if scoring disabled

        # HIGH if any of these detected
        high_signals = {
            "TOP SECRET",
            "SECRET",
            "PROTECTED",
            "AUSTEO",
            "AGAO",
            "CABINET",
            "NATIONAL CABINET",
            "NOFORN",
            "ORCON",
            "SCI",
            "SI",
            "HCS",
            "TK",
            "COSMIC TOP SECRET",
            "NATO SECRET",
            "TS//SCI",
            "TS/SCI",
        }

        # Check for banner structure, eyes only, REL TO
        high_patterns = {"banner_segments", "eyes_only", "rel_to_line", "austeo", "agao", "cabinet", "national_cabinet"}

        for _, detected in matches:
            detected_upper = detected.upper()
            # Check literals
            if any(sig in detected_upper for sig in high_signals):
                return "HIGH"
            # Check patterns
            if detected in high_patterns:
                return "HIGH"

        # MEDIUM for US/UK legacy low-tiers without other signal
        medium_signals = {"CONFIDENTIAL", "RESTRICTED", "CUI", "FOUO"}
        for _, detected in matches:
            if detected.upper() in medium_signals:
                return "MEDIUM"

        # Everything else is LOW
        return "LOW"

    def _check_false_positives(self, text: str, match_start: int, match_end: int) -> bool:
        """Apply false-positive dampers.

        Returns:
            True if match should be suppressed (false positive), False otherwise
        """
        if not self.check_code_fences:
            return False

        # Check if inside markdown code fence
        before_text = text[:match_start]
        fence_count = before_text.count("```")
        if fence_count % 2 == 1:  # Inside code fence
            return True

        # Check if inside inline code
        if "`" in before_text:
            last_backtick = before_text.rfind("`")
            if last_backtick > before_text.rfind(" "):  # Inside inline code
                after_text = text[match_end:]
                if "`" in after_text:
                    return True

        return False

    def _check_allcaps_confidence(self, text: str, match: str, match_start: int) -> bool:
        """Check if single-word matches have sufficient confidence (ALL-CAPS or proximity).

        Returns:
            True if match has sufficient confidence, False otherwise
        """
        if not self.require_allcaps_confidence:
            return True  # Always confident if check disabled

        # If match is ALL-CAPS, confidence is high
        if match.isupper():
            return True

        # Check proximity to other strong tokens (within 60 chars)
        strong_tokens = ["//", "AUSTEO", "REL TO", "CABINET", "EYES ONLY"]
        context_start = max(0, match_start - 60)
        context_end = min(len(text), match_start + len(match) + 60)
        context = text[context_start:context_end].upper()

        for token in strong_tokens:
            if token in context:
                return True

        return False

    def before_request(self, request: LLMRequest) -> LLMRequest:
        """Scan prompt for classification markings with advanced detection."""
        text = request.user_prompt

        # Normalize text
        normalized, shadow = self._normalize_text(text)
        check_text = normalized if self.case_sensitive else normalized.upper()
        check_shadow = shadow if self.case_sensitive else shadow.upper()

        detected: list[tuple[str, str]] = []  # (type, marking)

        # 1. Literal marking matches
        for marking in self.markings:
            if marking in check_text:
                # Find position for false-positive checking
                match_start = check_text.find(marking)
                match_end = match_start + len(marking)

                if self._check_false_positives(check_text, match_start, match_end):
                    continue

                if self._check_allcaps_confidence(check_text, marking, match_start):
                    detected.append(("literal", marking))

        # 2. Fuzzy regex matches (if enabled)
        if self.fuzzy_matching:
            for pattern_name, pattern in self.regex_compiled.items():
                for match in pattern.finditer(check_shadow):
                    match_text = match.group(0)
                    if self._check_false_positives(check_shadow, match.start(), match.end()):
                        continue
                    detected.append(("regex", pattern_name))

        # 3. Calculate severity and check threshold
        if detected:
            severity = self._calculate_severity(detected)

            # Check if severity meets minimum threshold
            severity_levels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            if severity_levels[severity] < severity_levels[self.min_severity]:
                # Below threshold, don't trigger violation
                logger.debug(
                    "[%s] Detected classification markings below threshold: %s (severity=%s, min=%s)",
                    self.channel,
                    ", ".join(f"{t}:{m}" for t, m in detected),
                    severity,
                    self.min_severity,
                )
                return request

            # Log with severity
            marking_list = ", ".join(f"{t}:{m}" for t, m in detected)
            logger.warning(
                "[%s] Detected classification markings in prompt: %s (severity=%s)",
                self.channel,
                marking_list,
                severity,
            )

            if self.mode == "abort":
                raise ValueError(f"Prompt contains classification markings (severity={severity}): {marking_list}")

            if self.mode == "mask":
                masked_text = text
                for match_type, marking in detected:
                    if match_type == "literal":
                        # Use case-insensitive replacement if needed
                        if self.case_sensitive:
                            masked_text = masked_text.replace(marking, self.mask)
                        else:
                            # Case-insensitive replacement
                            pattern = re.compile(re.escape(marking), re.IGNORECASE)
                            masked_text = pattern.sub(self.mask, masked_text)
                return request.clone(user_prompt=masked_text)

        return request


register_middleware(
    "audit_logger",
    lambda options, context: AuditMiddleware(
        include_prompts=bool(options.get("include_prompts", False)),
        channel=options.get("channel"),
    ),
    schema=_AUDIT_SCHEMA,
)

register_middleware(
    "prompt_shield",
    lambda options, context: PromptShieldMiddleware(
        denied_terms=options.get("denied_terms", []),
        mask=options.get("mask", "[REDACTED]"),
        on_violation=options.get("on_violation", "abort"),
        channel=options.get("channel"),
    ),
    schema=_PROMPT_SHIELD_SCHEMA,
)

register_middleware(
    "health_monitor",
    lambda options, context: HealthMonitorMiddleware(
        heartbeat_interval=float(options.get("heartbeat_interval", 60.0)),
        stats_window=int(options.get("stats_window", 50)),
        channel=options.get("channel"),
        include_latency=bool(options.get("include_latency", True)),
    ),
    schema=_HEALTH_SCHEMA,
)

register_middleware(
    "azure_content_safety",
    lambda options, context: AzureContentSafetyMiddleware(
        endpoint=options.get("endpoint"),
        key=options.get("key"),
        key_env=options.get("key_env"),
        api_version=options.get("api_version"),
        categories=options.get("categories"),
        severity_threshold=int(options.get("severity_threshold", 4)),
        on_violation=options.get("on_violation", "abort"),
        mask=options.get("mask", "[CONTENT BLOCKED]"),
        channel=options.get("channel"),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_CONTENT_SAFETY_SCHEMA,
)

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

register_middleware(
    "classified_material",
    lambda options, context: ClassifiedMaterialMiddleware(
        classification_markings=options.get("classification_markings"),
        on_violation=options.get("on_violation", "abort"),
        mask=options.get("mask", "[CLASSIFIED]"),
        channel=options.get("channel"),
        case_sensitive=options.get("case_sensitive", False),
        include_defaults=options.get("include_defaults", True),
        include_optional=options.get("include_optional", False),
        fuzzy_matching=options.get("fuzzy_matching", True),
        severity_scoring=options.get("severity_scoring", True),
        min_severity=options.get("min_severity", "LOW"),
        check_code_fences=options.get("check_code_fences", True),
        require_allcaps_confidence=options.get("require_allcaps_confidence", False),
    ),
    schema=_CLASSIFIED_MATERIAL_SCHEMA,
)


__all__ = [
    "AuditMiddleware",
    "PromptShieldMiddleware",
    "HealthMonitorMiddleware",
    "AzureContentSafetyMiddleware",
    "PIIShieldMiddleware",
    "ClassifiedMaterialMiddleware",
]
