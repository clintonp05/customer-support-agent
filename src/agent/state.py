from typing import TypedDict, List, Optional, Dict, Any
from datetime import datetime


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
    detected_intents: List[str]  # multi-intent list
    primary_intent: str
    intent_confidence: float
    intent_support_status: str  # SUPPORTED / IN_DOMAIN_OUT_OF_SCOPE / UNSUPPORTED

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

    # Observability
    trace_id: str
    prompt_versions: Dict[str, str]  # prompt_name → version hash