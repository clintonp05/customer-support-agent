"""Order ID ↔ User ID swap detection"""
import re
from typing import Tuple, Optional


ORDER_ID_PATTERN = r"^N-\d{8}-[A-Z0-9]{5}$"
USER_ID_PATTERN = r"^USR-[A-Z0-9]{8}$"


def detect_swap(order_id_candidate: str, user_id_candidate: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if order_id and user_id were swapped

    Returns:
        Tuple of (swap_detected, error_message)
    """
    if not order_id_candidate or not user_id_candidate:
        return False, None

    order_matches_pattern = bool(re.match(ORDER_ID_PATTERN, order_id_candidate, re.IGNORECASE))
    user_matches_pattern = bool(re.match(USER_ID_PATTERN, user_id_candidate, re.IGNORECASE))

    order_looks_like_user = bool(re.match(USER_ID_PATTERN, order_id_candidate, re.IGNORECASE))
    user_looks_like_order = bool(re.match(ORDER_ID_PATTERN, user_id_candidate, re.IGNORECASE))

    if order_looks_like_user and user_looks_like_order:
        return True, f"PARAM_SWAP: order_id '{order_id_candidate}' looks like user_id pattern"

    if order_looks_like_user:
        return True, f"PARAM_SWAP: order_id '{order_id_candidate}' looks like user_id"

    if user_looks_like_order:
        return True, f"PARAM_SWAP: user_id '{user_id_candidate}' looks like order_id"

    return False, None


def validate_id_pair(order_id: Optional[str], user_id: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate that an order_id and user_id are correctly formatted and not swapped

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not order_id and not user_id:
        return True, None  # Nothing to validate

    if order_id and not validate_order_id_format(order_id):
        return False, f"Invalid order_id format: {order_id}"

    if user_id and not validate_user_id_format(user_id):
        return False, f"Invalid user_id format: {user_id}"

    return detect_swap(order_id or "", user_id or "")


def validate_order_id_format(order_id: str) -> bool:
    """Check if order_id has valid format"""
    return bool(re.match(ORDER_ID_PATTERN, order_id, re.IGNORECASE))


def validate_user_id_format(user_id: str) -> bool:
    """Check if user_id has valid format"""
    return bool(re.match(USER_ID_PATTERN, user_id, re.IGNORECASE))