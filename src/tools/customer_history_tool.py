"""Customer history tool — fetches past orders and support interactions.

Used to detect repeat issues, compute churn risk, and populate the
escalation packet sent to human agents.
"""
from typing import Any, Dict

from src.tools.base import BaseTool
from src.db.queries import get_customer_order_history, get_customer_past_issues
from src.observability.logger import get_logger

logger = get_logger()

_CHURN_RISK_HIGH_THRESHOLD = 3   # ≥ 3 past issues → high risk
_DELIVERY_REPEAT_THRESHOLD = 1   # ≥ 1 prior delivery issue → repeat


class CustomerHistoryTool(BaseTool):
    """Fetch customer order history and past support interactions."""

    def __init__(self):
        super().__init__(name="get_customer_history", circuit_threshold=5, circuit_recovery_s=30)

    async def _call(self, params: Dict[str, Any], state: Any) -> Dict[str, Any]:
        user_id = params.get("user_id") or (state.get("user_id") if state else None)
        if not user_id:
            logger.warning("customer_history.missing_user_id")
            return {"success": False, "error": "MISSING_USER_ID", "history": {}}

        logger.info("customer_history.start", user_id=user_id)

        recent_orders = get_customer_order_history(user_id, limit=5)
        past_issues = get_customer_past_issues(user_id, days_back=90)

        delivery_issues = past_issues.get("delivery_issues", 0)
        refund_requests = past_issues.get("refund_requests", 0)
        total = past_issues.get("total_interactions", 0)

        is_repeat_delivery = delivery_issues >= _DELIVERY_REPEAT_THRESHOLD
        churn_risk = (
            "high" if total >= _CHURN_RISK_HIGH_THRESHOLD or delivery_issues >= 2
            else "medium" if is_repeat_delivery
            else "low"
        )

        history = {
            "recent_orders": recent_orders,
            "past_interactions": past_issues,
            "is_repeat_delivery_issue": is_repeat_delivery,
            "churn_risk": churn_risk,
            "recommended_action": _recommend_action(delivery_issues, refund_requests, churn_risk),
        }

        logger.info(
            "customer_history.complete",
            user_id=user_id,
            churn_risk=churn_risk,
            delivery_issues=delivery_issues,
            is_repeat=is_repeat_delivery,
        )
        return {"success": True, "history": history}


def _recommend_action(delivery_issues: int, refund_requests: int, churn_risk: str) -> str:
    if churn_risk == "high":
        return "full_refund + goodwill_credit"
    if delivery_issues >= 1:
        return "full_refund + priority_investigation"
    if refund_requests >= 2:
        return "full_refund + account_review"
    return "standard_refund"
