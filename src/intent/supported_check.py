"""Check if intent is supported or out of scope"""
from typing import Tuple
from src.intent.registry import INTENT_REGISTRY, SUPPORT_STATUS


def check_intent_support(intent: str, state: dict) -> Tuple[str, str]:
    """
    Check if an intent is supported

    Returns:
        Tuple of (support_status, reason)
    """
    if not intent:
        return SUPPORT_STATUS["UNSUPPORTED"], "empty_intent"

    # Check if intent exists in registry
    if intent not in INTENT_REGISTRY:
        return SUPPORT_STATUS["UNSUPPORTED"], "unknown_intent"

    intent_config = INTENT_REGISTRY[intent]

    # Check if marked as supported
    if not intent_config.get("supported", False):
        return SUPPORT_STATUS["UNSUPPORTED"], "intent_not_supported"

    # For now, all registered intents are in-scope
    # In production, this would check additional conditions
    return SUPPORT_STATUS["SUPPORTED"], ""


def is_intent_supported(intent: str) -> bool:
    """Quick check if intent is supported"""
    status, _ = check_intent_support(intent, {})
    return status == SUPPORT_STATUS["SUPPORTED"]