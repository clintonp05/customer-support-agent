from src.tools.base import BaseTool
from src.db.queries import get_order_by_id
from typing import Dict, Any


class OrderTool(BaseTool):
    """Order API integration tool"""

    def __init__(self):
        super().__init__(name="order_tool")

    async def _call(self, params: dict, state: dict) -> dict:
        order_id = params.get("order_id")
        user_id = params.get("user_id")

        if not order_id:
            return {
                "success": False,
                "error": "MISSING_ORDER_ID",
                "message": "Missing required parameter order_id"
            }

        order = get_order_by_id(order_id=order_id, user_id=user_id)
        if not order:
            return {
                "success": False,
                "error": "ORDER_NOT_FOUND",
                "message": f"Order {order_id} not found"
            }

        return {"success": True, "order": order}

    def _validate_result(self, result: dict) -> dict:
        if not result.get("success"):
            return result

        order = result.get("order", {})
        # Calculate order age if placed_at exists
        from datetime import datetime
        placed_at = order.get("placed_at")
        if placed_at:
            if isinstance(placed_at, str):
                try:
                    placed_at = datetime.fromisoformat(placed_at)
                except Exception:
                    placed_at = None
            if placed_at:
                age_days = (datetime.now() - placed_at).days
                order["age_days"] = age_days

        result["order"] = order
        return result