"""PII detection and redaction.

Combines:
  - Presidio (English + some international PII)
  - Custom Vietnamese regex (CCCD, CMND, số điện thoại VN, biển số xe)

Returns redacted text + list of detected entities for logging/audit.
"""
import re
from dataclasses import dataclass
from typing import Pattern

from presidio_analyzer import AnalyzerEngine, Pattern as PresidioPattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PIIDetection:
    entity_type: str
    start: int
    end: int
    score: float


# --- Vietnamese-specific patterns ---

VN_PATTERNS: dict[str, Pattern] = {
    # CCCD: 12 digits (new ID)
    "VN_CCCD": re.compile(r"\b\d{12}\b"),
    # CMND: 9 digits (old ID)
    "VN_CMND": re.compile(r"\b\d{9}\b"),
    # Vietnam phone: +84... or 0... with 9-10 digits
    "VN_PHONE": re.compile(r"(?:\+84|0)(?:3|5|7|8|9)\d{8}\b"),
    # License plate: 30A-12345, 51F-678.90
    "VN_LICENSE_PLATE": re.compile(r"\b\d{2}[A-Z]-?\d{3}\.?\d{2}\b"),
    # Bank account: 10-16 digits (heuristic — only block if near banking words)
    # We skip this in MVP since false-positive rate is high
}


# --- Presidio recognizers for VN ---

def _build_vn_recognizers() -> list[PatternRecognizer]:
    recognizers = []
    for entity_type, pattern in VN_PATTERNS.items():
        recognizers.append(
            PatternRecognizer(
                supported_entity=entity_type,
                patterns=[
                    PresidioPattern(
                        name=f"{entity_type}_pattern",
                        regex=pattern.pattern,
                        score=0.85,
                    )
                ],
                supported_language="en",  # Presidio doesn't have 'vi'; engine still scans
            )
        )
    return recognizers


class PIIService:
    """Singleton-style service. Heavy engines instantiated once."""

    def __init__(self):
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()
        for rec in _build_vn_recognizers():
            self._analyzer.registry.add_recognizer(rec)

    def detect(self, text: str, language: str = "en") -> list[PIIDetection]:
        """Return all PII entities found."""
        if not text.strip():
            return []
        try:
            results = self._analyzer.analyze(text=text, language=language)
            return [
                PIIDetection(
                    entity_type=r.entity_type,
                    start=r.start,
                    end=r.end,
                    score=r.score,
                )
                for r in results
            ]
        except Exception as e:
            logger.warning("pii_detect_failed", error=str(e))
            return []

    def redact(self, text: str, language: str = "en") -> tuple[str, list[PIIDetection]]:
        """Return (redacted_text, detections). Replaces with [TYPE]."""
        detections = self.detect(text, language=language)
        if not detections:
            return text, []

        try:
            # Build analyzer results for anonymizer
            from presidio_analyzer import RecognizerResult

            analyzer_results = [
                RecognizerResult(
                    entity_type=d.entity_type,
                    start=d.start,
                    end=d.end,
                    score=d.score,
                )
                for d in detections
            ]

            operators = {
                "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
                "VN_PHONE": OperatorConfig("replace", {"new_value": "[PHONE]"}),
                "VN_CCCD": OperatorConfig("replace", {"new_value": "[ID]"}),
                "VN_CMND": OperatorConfig("replace", {"new_value": "[ID]"}),
                "VN_LICENSE_PLATE": OperatorConfig("replace", {"new_value": "[PLATE]"}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CARD]"}),
                "PERSON": OperatorConfig("replace", {"new_value": "[NAME]"}),
                "LOCATION": OperatorConfig("replace", {"new_value": "[LOCATION]"}),
            }

            result = self._anonymizer.anonymize(
                text=text,
                analyzer_results=analyzer_results,
                operators=operators,
            )
            return result.text, detections
        except Exception as e:
            logger.warning("pii_redact_failed", error=str(e))
            return text, detections

    def has_pii(self, text: str, min_score: float = 0.7) -> bool:
        """Quick check — true if any high-confidence PII detected."""
        return any(d.score >= min_score for d in self.detect(text))


pii_service = PIIService()
