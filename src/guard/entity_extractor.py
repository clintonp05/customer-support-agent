"""Entity extraction for order IDs, product names, etc."""
import re
from typing import Dict, List, Optional


# ID patterns
ORDER_ID_PATTERN = r'N-\d{8}-[A-Z0-9]{5}'
USER_ID_PATTERN = r'USR-[A-Z0-9]{4,12}'
PRODUCT_ID_PATTERN = r'PROD-\d{3,}'


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract entities from text

    Returns:
        Dict mapping entity type to list of extracted values
    """
    entities = {
        "order_ids": extract_order_ids(text),
        "user_ids": extract_user_ids(text),
        "product_ids": extract_product_ids(text),
    }

    return entities


def extract_order_ids(text: str) -> List[str]:
    """Extract order IDs from text"""
    return re.findall(ORDER_ID_PATTERN, text, re.IGNORECASE)


def extract_user_ids(text: str) -> List[str]:
    """Extract user IDs from text"""
    return re.findall(USER_ID_PATTERN, text, re.IGNORECASE)


def extract_product_ids(text: str) -> List[str]:
    """Extract product IDs from text"""
    return re.findall(PRODUCT_ID_PATTERN, text, re.IGNORECASE)


def extract_first_order_id(text: str) -> Optional[str]:
    """Extract the first order ID from text"""
    ids = extract_order_ids(text)
    return ids[0] if ids else None


def extract_first_user_id(text: str) -> Optional[str]:
    """Extract the first user ID from text"""
    ids = extract_user_ids(text)
    return ids[0] if ids else None