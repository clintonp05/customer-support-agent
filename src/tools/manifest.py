from typing import Dict, List, Any, Optional
from src.tools.order_tool import OrderTool
from src.tools.refund_tool import RefundTool, CheckRefundEligibilityTool
from src.tools.delivery_tool import DeliveryTool
from src.tools.warranty_tool import WarrantyTool, InitiateClaimTool
from src.tools.escalation_tool import EscalationTool
from src.tools.base import BaseTool

# Tool manifest: maps tool names to instances
TOOL_REGISTRY: Dict[str, BaseTool] = {
    "check_order": OrderTool(),
    "check_refund_eligibility": CheckRefundEligibilityTool(),
    "initiate_refund": RefundTool(),
    "track_delivery": DeliveryTool(),
    "check_warranty": WarrantyTool(),
    "initiate_claim": InitiateClaimTool(),
    "escalate_to_human": EscalationTool(),
}


# Intent to tool chain mapping
TOOL_CHAINS = {
    "refund_request": ["check_order", "check_refund_eligibility", "initiate_refund"],
    "order_status": ["check_order"],
    "delivery_tracking": ["track_delivery"],
    "warranty_claim": ["check_warranty", "initiate_claim"],
    "cancel_order": ["check_order"],
    "change_delivery_address": ["check_order"],
    "payment_issue": [],
    "product_inquiry": [],
    "account_help": [],
    "general_inquiry": [],
    "speak_to_human": [],
}


# Tool manifest for the agent
TOOL_MANIFEST = """
Available Tools:

1. check_order
   - Description: Retrieves order details by order_id and user_id
   - Parameters: order_id, user_id
   - Returns: order details including status, items, delivery info

2. check_refund_eligibility
   - Description: Checks if an order is eligible for refund
   - Parameters: order_id, user_id
   - Returns: eligibility status and reason

3. initiate_refund
   - Description: Processes a refund for an order
   - Parameters: order_id, user_id, reason (optional)
   - Returns: refund_id, status

4. track_delivery
   - Description: Tracks delivery status of an order
   - Parameters: order_id, user_id
   - Returns: tracking number, carrier, current location, events

5. check_warranty
   - Description: Checks warranty status for a product
   - Parameters: order_id, user_id, product_id
   - Returns: warranty details, validity

6. initiate_claim
   - Description: Initiates a warranty claim
   - Parameters: order_id, user_id, product_id, issue_description
   - Returns: claim_id, next steps

7. escalate_to_human
   - Description: Escalates to human agent
   - Parameters: user_id, reason
   - Returns: ticket_id, priority
"""


def get_tool(tool_name: str) -> Optional[BaseTool]:
    """Get tool instance by name"""
    return TOOL_REGISTRY.get(tool_name)


def get_tool_chain(intent: str) -> List[str]:
    """Get the tool chain for an intent"""
    return TOOL_CHAINS.get(intent, [])