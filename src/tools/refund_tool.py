import json
import uuid
import hashlib
from src.tools.base import BaseTool
from src.db.queries import get_order_by_id, get_refunds_by_order
from src.cache.redis_client import get_redis_client
from src.observability.logger import get_logger
from typing import Dict, Any, Optional

logger = get_logger()

_IDEM_TTL_S = 86400 * 7  # 7 days


class RefundTool(BaseTool):
    """Refund API tool with Redis-backed idempotency keys (falls back to in-memory)."""

    def __init__(self):
        super().__init__(name="refund_tool")
        self._processed_refunds: Dict[str, dict] = {}  # in-memory fallback only

    def _idem_redis_key(self, idem_key: str) -> str:
        return f"refund_idem:{idem_key}"

    def _idem_get(self, idem_key: str) -> Optional[dict]:
        redis = get_redis_client()
        if redis is not None:
            try:
                raw = redis.get(self._idem_redis_key(idem_key))
                if raw:
                    return json.loads(raw)
            except Exception as exc:
                logger.warning("refund_tool.idem_redis_read_failed", error=str(exc))
        return self._processed_refunds.get(idem_key)

    def _idem_set(self, idem_key: str, result: dict) -> None:
        redis = get_redis_client()
        if redis is not None:
            try:
                redis.setex(self._idem_redis_key(idem_key), _IDEM_TTL_S, json.dumps(result, ensure_ascii=False))
                return
            except Exception as exc:
                logger.warning("refund_tool.idem_redis_write_failed", error=str(exc))
        self._processed_refunds[idem_key] = result  # fallback

    async def _call(self, params: dict, state: dict) -> dict:
        order_id = params.get("order_id")
        user_id = params.get("user_id")
        reason = params.get("reason", "Customer requested refund")

        if not order_id or not user_id:
            return {"success": False, "error": "MISSING_PARAMS", "message": "order_id and user_id are required"}

        order = get_order_by_id(order_id=order_id, user_id=user_id)
        if not order:
            return {"success": False, "error": "ORDER_NOT_FOUND", "message": f"Order {order_id} not found"}

        # Prevent double refunds for the same order (DB-level check)
        existing_refunds = get_refunds_by_order(order_id=order_id, user_id=user_id)
        if existing_refunds:
            return {
                "success": False,
                "error": "REFUND_ALREADY_EXISTS",
                "message": "A refund has already been processed for this order"
            }

        # Idempotency check — Redis first, in-memory fallback
        idem_key = self._generate_idempotency_key(order_id, user_id)
        cached = self._idem_get(idem_key)
        if cached:
            logger.info("refund_tool.idem_hit", idem_key=idem_key)
            return cached

        refund_id = f"REF-{uuid.uuid4().hex[:12].upper()}"
        result = {
            "success": True,
            "refund_id": refund_id,
            "order_id": order_id,
            "user_id": user_id,
            "amount": order.get("total_aed", 0),
            "status": "processed",
            "reason": reason,
            "idempotency_key": idem_key,
        }

        self._idem_set(idem_key, result)
        return result

    def _generate_idempotency_key(self, order_id: str, user_id: str) -> str:
        data = f"{order_id}:{user_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:16].upper()

    def _validate_result(self, result: dict) -> dict:
        if not result.get("refund_id"):
            return {"success": False, "error": "REFUND_FAILED"}
        return result


class CheckRefundEligibilityTool(BaseTool):
    """Check if order is eligible for refund"""

    def __init__(self):
        super().__init__(name="check_refund_eligibility")

    async def _call(self, params: dict, state: dict) -> dict:
        order_id = params.get("order_id")
        user_id = params.get("user_id")

        if not order_id or not user_id:
            return {"success": False, "error": "MISSING_PARAMS", "eligible": False}

        order = get_order_by_id(order_id=order_id, user_id=user_id)
        if not order:
            return {"success": False, "error": "ORDER_NOT_FOUND", "eligible": False}

        placed_at = order.get("placed_at")
        from datetime import datetime
        if isinstance(placed_at, str):
            try:
                placed_at = datetime.fromisoformat(placed_at)
            except Exception:
                placed_at = None

        age_days = 999
        if placed_at:
            age_days = (datetime.now() - placed_at).days

        status = order.get("status", "")
        eligible = age_days <= 30 and status not in ["refunded", "cancelled"]

        return {
            "success": True,
            "eligible": eligible,
            "reason": None if eligible else f"Order is {age_days} days old, status: {status}"
        }