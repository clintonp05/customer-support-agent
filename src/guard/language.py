"""Language detection guard (Arabic/English)"""
from typing import Tuple


# Arabic character range
ARABIC_RANGE = range(0x0600, 0x06FF)


def detect_language(text: str) -> str:
    """Detect if text is Arabic or English

    Returns:
        Language code: 'ar', 'en', or 'mixed'
    """
    arabic_chars = sum(1 for c in text if ord(c) in ARABIC_RANGE)
    english_chars = sum(1 for c in text if c.isalpha() and ord(c) < 128)

    total = arabic_chars + english_chars

    if total == 0:
        return "en"  # Default to English for numbers/symbols

    arabic_ratio = arabic_chars / total
    english_ratio = english_chars / total

    if arabic_ratio > 0.5:
        return "ar"
    elif english_ratio > 0.5:
        return "en"
    else:
        return "mixed"


def is_rtl(text: str) -> bool:
    """Check if text direction is RTL (Arabic)"""
    return detect_language(text) == "ar"