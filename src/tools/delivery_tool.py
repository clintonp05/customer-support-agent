from src.tools.base import BaseTool
from src.db.queries import get_delivery_by_order
from typing import Dict, Any


class DeliveryTool(BaseTool):
    """Delivery tracking tool"""

    def __init__(self):
        super().__init__(name="delivery_tool")

    async def _call(self, params: dict, state: dict) -> dict:
        order_id = params.get("order_id")
        user_id = params.get("user_id")

        if not order_id:
            return {"success": False, "error": "MISSING_ORDER_ID", "message": "Missing order_id"}

        delivery = get_delivery_by_order(order_id=order_id, user_id=user_id)
        if not delivery:
            return {"success": False, "error": "TRACKING_NOT_FOUND", "message": f"No delivery record for order {order_id}"}

        return {"success": True, "tracking": delivery}
