"""ClassifiedMaterialMiddleware - LLM middleware plugin."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Sequence

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMMiddleware, LLMRequest
from elspeth.core.base.types import SecurityLevel
from elspeth.core.registries.middleware import register_middleware

logger = logging.getLogger(__name__)

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


class ClassifiedMaterialMiddleware(BasePlugin, LLMMiddleware):
    """Detect and block classified material markings in prompts with advanced fuzzy matching.

    Features:
    - Unicode normalization (NFKC) and homoglyph detection
    - Fuzzy regex matching for spacing variants (A.U.S.T.E.O)
    - Severity scoring (HIGH/MEDIUM/LOW)
    - False-positive dampers (code fence detection, all-caps requirement)
    - REL TO country-list parsing

    Args:
        security_level: Security clearance for this middleware (MANDATORY per ADR-004).
        allow_downgrade: Whether middleware can operate at lower pipeline levels (MANDATORY per ADR-005).
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
        security_level: SecurityLevel,
        allow_downgrade: bool,
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
            security_level: Security clearance for this middleware (MANDATORY per ADR-004).
            allow_downgrade: Whether middleware can operate at lower pipeline levels (MANDATORY per ADR-005).
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
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
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
        self.regex_compiled: dict[str, re.Pattern[str]] = {}
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


def _create_classified_material_middleware(
    options: dict[str, Any], context: PluginContext
) -> ClassifiedMaterialMiddleware:
    """Factory for classified material middleware with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    allow_downgrade = opts.get("allow_downgrade", True)
    return ClassifiedMaterialMiddleware(
        security_level=opts["security_level"],
        allow_downgrade=allow_downgrade,
        classification_markings=opts.get("classification_markings"),
        on_violation=opts.get("on_violation", "abort"),
        mask=opts.get("mask", "[CLASSIFIED]"),
        channel=opts.get("channel"),
        case_sensitive=opts.get("case_sensitive", False),
        include_defaults=opts.get("include_defaults", True),
        include_optional=opts.get("include_optional", False),
        fuzzy_matching=opts.get("fuzzy_matching", True),
        severity_scoring=opts.get("severity_scoring", True),
        min_severity=opts.get("min_severity", "LOW"),
        check_code_fences=opts.get("check_code_fences", True),
        require_allcaps_confidence=opts.get("require_allcaps_confidence", False),
    )


register_middleware(
    "classified_material",
    _create_classified_material_middleware,
    schema=_CLASSIFIED_MATERIAL_SCHEMA,
)


__all__ = ["ClassifiedMaterialMiddleware"]
