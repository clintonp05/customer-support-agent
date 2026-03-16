from typing import TypedDict, List, Optional, Dict, Any, Annotated
from datetime import datetime


def merge_dicts(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if left:
        merged.update(left)
    if right:
        merged.update(right)
    return merged


def union_list(left: Optional[List[str]], right: Optional[List[str]]) -> List[str]:
    """Merge two intent lists, deduplicating while preserving order."""
    seen: set = set()
    result: List[str] = []
    for item in (left or []) + (right or []):
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def last_non_empty(left: str, right: str) -> str:
    """Keep the most recently written non-empty value."""
    return right if right else left


class ConversationState(TypedDict):
    # Identity
    conversation_id: str
    user_id: str
    session_id: str

    # Conversation
    messages: List[Dict[str, str]]
    current_turn: int

    # Intent layer
    raw_query: str
    detected_intents: Annotated[List[str], union_list]  # parallel-safe union
    primary_intent: Annotated[str, last_non_empty]  # parallel-safe last-write
    intent_confidence: float
    intent_support_status: str  # SUPPORTED / IN_DOMAIN_OUT_OF_SCOPE / UNSUPPORTED
    query_analysis: Annotated[Dict[str, Any], merge_dicts]
    timings_ms: Annotated[Dict[str, float], merge_dicts]
    response_source: str
    cache_payload: Optional[Dict[str, Any]]

    # Params
    extracted_params: Dict[str, Any]
    param_validation_status: str  # COMPLETE / INCOMPLETE / SWAP_DETECTED
    missing_params: List[str]

    # Execution
    tools_executed: List[str]
    tool_results: Dict[str, Any]
    execution_budget_ms: int
    budget_spent_ms: int

    # Memory
    episodic_context: Optional[Dict]  # injected at session start

    # Control flow
    next_node: str  # LangGraph routing
    escalation_required: bool
    escalation_reason: Optional[str]

    # Response
    final_response: Optional[str]

    # Emotion & signal detection (populated by guard_input_node)
    emotion: Optional[Dict[str, Any]]  # tone, churn_signal, repeat_complaint, delivery_dispute, escalation_weight

    # Customer history (populated by execute_tools_node in parallel)
    customer_history: Optional[Dict[str, Any]]  # past_issues, churn_risk, recommended_action

    # Escalation packet (populated by escalate_node for human agents)
    escalation_packet: Optional[Dict[str, Any]]  # full context: order, delivery, history, assessment

    # UI progress messages pushed to token_queue before LLM call
    progress_messages: Optional[list]  # e.g. ["Checking order details...", "Verifying delivery status..."]

    # Observability
    trace_id: str
    prompt_versions: Dict[str, str]  # prompt_name → version hash
