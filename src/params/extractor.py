"""LLM param extraction from conversation"""
from typing import Dict, Any, List
import re

from src.guard.entity_extractor import extract_order_ids, extract_user_ids, extract_product_ids
from src.intent.registry import INTENT_REGISTRY


async def extract_params(intent: str, messages: List[Dict[str, str]], required_params: List[str]) -> Dict[str, Any]:
    """
    Extract parameters for an intent from conversation messages

    Returns:
        Dict of extracted parameters
    """
    # Combine all user messages
    all_text = " ".join([
        msg.get("content", "")
        for msg in messages
        if msg.get("role") == "user"
    ])

    params = {}

    # Extract known entity types
    if "order_id" in required_params:
        order_ids = extract_order_ids(all_text)
        if order_ids:
            params["order_id"] = order_ids[0]

    if "user_id" in required_params:
        user_ids = extract_user_ids(all_text)
        if user_ids:
            params["user_id"] = user_ids[0]

    if "product_id" in required_params:
        product_ids = extract_product_ids(all_text)
        if product_ids:
            params["product_id"] = product_ids[0]

    # For remaining params, try to extract from context
    for param in required_params:
        if param not in params:
            params[param] = _extract_generic_param(param, all_text)

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