"""Conversation service for processing support requests."""
import uuid
from typing import Dict, Any, List, Optional

from src.agent.graph import get_agent_graph
from src.agent.state import ConversationState
from src.observability.logger import get_logger


class ConversationService:
    """Encapsulates conversation processing logic."""

    def __init__(self):
        self.logger = get_logger()
        self.graph = get_agent_graph()

    async def process_conversation(
        self,
        conversation_id: str,
        user_id: str,
        session_id: str,
        message: str,
        messages: List[Dict[str, str]],
        order_id: Optional[str] = None,
        product_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        execution_budget_ms: int = 8000,
    ) -> Dict[str, Any]:
        self.logger.info(
            "conversation_service.start",
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=session_id,
            order_id=order_id,
            product_id=product_id,
        )

        initial_extracted = {
            "user_id": user_id,
            **({"order_id": order_id} if order_id else {}),
            **({"product_id": product_id} if product_id else {}),
        }

        if payload:
            for k, v in payload.items():
                if v is not None:
                    initial_extracted[k] = v

        initial_state: ConversationState = {
            "conversation_id": conversation_id or str(uuid.uuid4()),
            "user_id": user_id,
            "session_id": session_id,
            "messages": messages + [{"role": "user", "content": message}],
            "current_turn": len(messages) + 1,
            "raw_query": message,
            "detected_intents": [],
            "primary_intent": "",
            "intent_confidence": 0.0,
            "intent_support_status": "SUPPORTED",
            "query_analysis": {},
            "timings_ms": {},
            "response_source": "",
            "cache_payload": None,
            "extracted_params": initial_extracted,
            "param_validation_status": "COMPLETE",
            "missing_params": [],
            "tools_executed": [],
            "tool_results": {},
            "execution_budget_ms": execution_budget_ms,
            "budget_spent_ms": 0,
            "episodic_context": None,
            "next_node": "",
            "escalation_required": False,
            "escalation_reason": None,
            "final_response": None,
            "trace_id": str(uuid.uuid4()),
            "prompt_versions": {},
        }

        result = await self.graph.ainvoke(initial_state)
        self.logger.info(
            "conversation_service.complete",
            conversation_id=conversation_id,
            next_node=result.get("next_node", ""),
            escalation_required=result.get("escalation_required", False),
        )
        return result


conversation_service = ConversationService()
