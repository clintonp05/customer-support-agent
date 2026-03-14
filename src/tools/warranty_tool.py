from src.tools.base import BaseTool
from src.db.queries import get_warranty_by_order, get_order_by_id
from typing import Dict, Any


class WarrantyTool(BaseTool):
    """Warranty claim tool"""

    def __init__(self):
        super().__init__(name="warranty_tool")

    async def _call(self, params: dict, state: dict) -> dict:
        order_id = params.get("order_id")
        user_id = params.get("user_id")
        product_id = params.get("product_id")
        issue_description = params.get("issue_description")

        if not order_id or not user_id or not product_id:
            return {
                "success": False,
                "error": "MISSING_PARAMS",
                "message": "order_id, user_id, and product_id are required"
            }

        order = get_order_by_id(order_id=order_id, user_id=user_id)
        if not order:
            return {"success": False, "error": "ORDER_NOT_FOUND", "message": "Order not found"}

        warranty = get_warranty_by_order(order_id=order_id, user_id=user_id, product_id=product_id)
        if not warranty:
            return {"success": False, "error": "WARRANTY_NOT_FOUND", "message": "No warranty record found for this product and order"}

        from datetime import datetime
        end_date = warranty.get("end_date")
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date)

        is_valid = end_date and end_date > datetime.now()

        return {
            "success": True,
            "product_id": product_id,
            "warranty": warranty,
            "is_valid": bool(is_valid),
            "issue_description": issue_description,
        }


class InitiateClaimTool(BaseTool):
    """Initiate warranty claim"""

    def __init__(self):
        super().__init__(name="initiate_claim")

    async def _call(self, params: dict, state: dict) -> dict:
        order_id = params.get("order_id")
        user_id = params.get("user_id")
        product_id = params.get("product_id")
        issue_description = params.get("issue_description")

        warranty_result = state.get("tool_results", {}).get("check_warranty", {})
        if not warranty_result.get("is_valid"):
            return {
                "success": False,
                "error": "WARRANTY_EXPIRED",
                "message": "Cannot initiate claim - warranty has expired"
            }

        import uuid
        return {
            "success": True,
            "claim_id": f"CLM-{uuid.uuid4().hex[:12].upper()}",
            "order_id": order_id,
            "product_id": product_id,
            "status": "claim_initiated",
            "next_steps": [
                "Customer service will review your claim within 48 hours",
                "You will receive a replacement or repair authorization",
                "Return shipping label will be sent to your email"
            ]
        }