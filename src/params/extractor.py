"""LLM param extraction from conversation"""
from typing import Dict, Any, List, Optional
import re

from src.guard.entity_extractor import extract_order_ids, extract_user_ids, extract_product_ids
from src.intent.registry import INTENT_REGISTRY


async def extract_params(intent: str, messages: List[Dict[str, str]], required_params: List[str]) -> Dict[str, Any]:
    """
    Extract parameters for an intent from conversation messages.

    Strategy: always prefer the CURRENT (latest) user message.  Only fall back
    to the most-recent occurrence in conversation history when the current message
    contains no match.  This prevents old order IDs / user IDs in prior turns
    from overriding what the user explicitly said in their latest message.
    """
    # Current message = last user turn in the list
    current_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            current_text = msg.get("content", "")
            break

    # History text (all user turns) — used as fallback only
    history_text = " ".join(
        msg.get("content", "")
        for msg in messages
        if msg.get("role") == "user"
    )

    def _first_from(text: str, extractor) -> Optional[str]:
        found = extractor(text)
        return found[0] if found else None

    def _last_from(text: str, extractor) -> Optional[str]:
        """Return the LAST (most recent) occurrence in the concatenated history."""
        found = extractor(text)
        return found[-1] if found else None

    params: Dict[str, Any] = {}

    # Extract known entity types — current message takes priority
    if "order_id" in required_params:
        value = _first_from(current_text, extract_order_ids) or _last_from(history_text, extract_order_ids)
        if value:
            params["order_id"] = value

    if "user_id" in required_params:
        value = _first_from(current_text, extract_user_ids) or _last_from(history_text, extract_user_ids)
        if value:
            params["user_id"] = value

    if "product_id" in required_params:
        value = _first_from(current_text, extract_product_ids) or _last_from(history_text, extract_product_ids)
        if value:
            params["product_id"] = value

    # For remaining params, try to extract from current message first, then history
    for param in required_params:
        if param not in params:
            params[param] = _extract_generic_param(param, current_text) or _extract_generic_param(param, history_text)

    return params


def _extract_generic_param(param: str, text: str) -> Any:
    """Extract generic parameters using pattern matching"""
    # Address extraction
    if param == "new_address":
        address_match = re.search(r'(?:address|location|ship to)[:\s]+(.+?)(?:\.|$)', text, re.IGNORECASE)
        if address_match:
            return address_match.group(1).strip()

    # Reason extraction
    if "reason" in param.lower():
        reason_match = re.search(r'(?:because|reason|due to)[:\s]+(.+?)(?:\.|$)', text, re.IGNORECASE)
        if reason_match:
            return reason_match.group(1).strip()

    return None