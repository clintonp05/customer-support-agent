"""PII detection and masking guard using Presidio"""
import re
from typing import Tuple


# PII patterns
PII_PATTERNS = {
    "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "PHONE": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    "CREDIT_CARD": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
    "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
    # ID patterns that we want to preserve for the agent
    # "ORDER_ID": r'N-\d{8}-[A-Z0-9]{5}',
    # "USER_ID": r'USR-[A-Z0-9]{8}',
}


def detect_pii(text: str) -> list:
    """Detect PII in text

    Returns:
        List of detected PII types
    """
    detected = []

    for pii_type, pattern in PII_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            detected.append(pii_type)

    return detected


def mask_pii(text: str) -> str:
    """Mask PII in text

    Returns:
        Text with PII masked
    """
    masked = text

    # Mask email
    masked = re.sub(PII_PATTERNS["EMAIL"], "[EMAIL]", masked)

    # Mask phone
    masked = re.sub(PII_PATTERNS["PHONE"], "[PHONE]", masked)

    # Mask credit card
    masked = re.sub(PII_PATTERNS["CREDIT_CARD"], "[CREDIT_CARD]", masked)

    # Mask SSN
    masked = re.sub(PII_PATTERNS["SSN"], "[SSN]", masked)

    return masked


def get_pii_entities(text: str) -> dict:
    """Get PII entities with their positions"""
    entities = {}

    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        entities[pii_type] = [
            {"value": m.group(), "start": m.start(), "end": m.end()}
            for m in matches
        ]

    return entities