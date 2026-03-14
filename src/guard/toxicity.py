"""Toxicity detection guard"""
from typing import Tuple


# Mock toxicity detection - in production, use Llama Guard or HF toxicity model
TOXIC_KEYWORDS = [
    "hate", "kill", "attack", "threat", "violence",
    "abuse", "harass", "spam", "scam"
]


def check_toxicity(text: str) -> Tuple[bool, float]:
    """Check if text contains toxic content

    Returns:
        Tuple of (is_toxic, confidence_score)
    """
    text_lower = text.lower()

    for keyword in TOXIC_KEYWORDS:
        if keyword in text_lower:
            return True, 0.95

    return False, 0.0