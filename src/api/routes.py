from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time
import functools

from src.constants import X_REQUEST_ID_HEADER, X_CHANNEL_ID_HEADER, MISSING_HEADERS_ERROR, DEFAULT_EXECUTION_BUDGET_MS
from src.services.conversation_service import conversation_service
from src.observability.logger import get_logger
from src.observability.tracer import get_tracer

router = APIRouter()


def profile_api(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        logger = get_logger()
        start = time.time()
        result = await fn(*args, **kwargs)
        elapsed_ms = (time.time() - start) * 1000
        logger.info("api.profile", fn=fn.__name__, elapsed_ms=elapsed_ms)
        return result
    return wrapper



class ConversationTurn(BaseModel):
    conversation_id: str = Field(default="")
    user_id: str = Field(default="user-1")
    session_id: str = Field(default="session-1")
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    message: str
    messages: List[Dict[str, str]] = Field(default_factory=list)
    execution_budget_ms: int = DEFAULT_EXECUTION_BUDGET_MS


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: str
    session_id: str
    final_response: str
    next_node: str
    escalation_required: bool = False
    tool_results: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str


@router.get("/health")
@profile_api
async def health_check(request: Request):
    logger = getattr(request.state, "logger", get_logger())
    logger.info("health_check", status="ok")
    return {"status": "ok"}


@router.post("/support", response_model=ConversationResponse)
@profile_api
async def support_query(turn: ConversationTurn, request: Request):
    logger = getattr(request.state, "logger", get_logger())
    logger.info("support_query.received", conversation_id=turn.conversation_id, user_id=turn.user_id, session_id=turn.session_id)

    tracer = get_tracer()
    async with tracer.trace("support_query"):
        try:
            result = await conversation_service.process_conversation(
                conversation_id=turn.conversation_id,
                user_id=turn.user_id,
                session_id=turn.session_id,
                message=turn.message,
                messages=turn.messages,
                order_id=turn.order_id,
                product_id=turn.product_id,
                payload=turn.payload,
                execution_budget_ms=turn.execution_budget_ms,
            )
        except Exception as exc:
            logger.error("support_query.failed", error=str(exc))
            raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    logger.info("support_query.completed", next_node=result.get("next_node", ""), escalation_required=result.get("escalation_required", False))
    return ConversationResponse(
        conversation_id=result.get("conversation_id", turn.conversation_id),
        user_id=result.get("user_id", turn.user_id),
        session_id=result.get("session_id", turn.session_id),
        final_response=result.get("final_response", ""),
        next_node=result.get("next_node", ""),
        escalation_required=result.get("escalation_required", False),
        tool_results=result.get("tool_results", {}),
        trace_id=result.get("trace_id", ""),
    )
