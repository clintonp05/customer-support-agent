"""LangGraph StateGraph definition"""
from langgraph.graph import StateGraph, END
from typing import Dict, Any, Optional

from src.agent.state import ConversationState
from src.agent.nodes import guard_input_node, serve_cache_node, query_analyser_node, intent_analyser_node, complexity_analyser_node, query_analyse_join_node, complex_query_orchestrator_node, complex_intent_agent_node, complex_refine_agent_node, complex_query_join_node, classify_intent_node, extract_params_node, validate_params_node, request_params_node, handle_param_error_node, execute_tools_node, generate_response_node, handle_unsupported_node, escalate_node, persist_response_node
from src.agent.edges import route_after_guard, route_after_query_analyse, route_after_classify, route_after_extract_params, route_after_validate, route_after_execute, route_to_node
from src.observability.logger import get_logger


def create_agent_graph() -> StateGraph:
    """Create the main agent conversation graph"""

    workflow = StateGraph(ConversationState)

    workflow.add_node("guard_input", guard_input_node)
    workflow.add_node("serve_cache", serve_cache_node)
    workflow.add_node("query_analyser", query_analyser_node)
    workflow.add_node("intent_analyser", intent_analyser_node)
    workflow.add_node("complexity_analyser", complexity_analyser_node)
    workflow.add_node("query_analyse_join", query_analyse_join_node)
    workflow.add_node("complex_query_orchestrator", complex_query_orchestrator_node)
    workflow.add_node("complex_intent_agent", complex_intent_agent_node)
    workflow.add_node("complex_refine_agent", complex_refine_agent_node)
    workflow.add_node("complex_query_join", complex_query_join_node)
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("extract_params", extract_params_node)
    workflow.add_node("validate_params", validate_params_node)
    workflow.add_node("request_params", request_params_node)
    workflow.add_node("handle_param_error", handle_param_error_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("generate_response", generate_response_node)
    workflow.add_node("persist_response", persist_response_node)
    workflow.add_node("handle_unsupported", handle_unsupported_node)
    workflow.add_node("escalate", escalate_node)

    workflow.set_entry_point("guard_input")

    workflow.add_conditional_edges(
        "guard_input",
        route_after_guard,
        ["escalate", "query_analyser", "serve_cache", "classify_intent"]
    )
    workflow.add_edge("serve_cache", "persist_response")
    workflow.add_edge("query_analyser", "intent_analyser")
    workflow.add_edge("query_analyser", "complexity_analyser")
    workflow.add_edge("intent_analyser", "query_analyse_join")
    workflow.add_edge("complexity_analyser", "query_analyse_join")
    workflow.add_conditional_edges(
        "query_analyse_join",
        route_after_query_analyse,
        ["complex_query_orchestrator", "handle_unsupported", "escalate"]
    )
    workflow.add_edge("complex_query_orchestrator", "complex_intent_agent")
    workflow.add_edge("complex_query_orchestrator", "complex_refine_agent")
    workflow.add_edge("complex_intent_agent", "complex_query_join")
    workflow.add_edge("complex_refine_agent", "complex_query_join")
    workflow.add_edge("complex_query_join", "extract_params")
    workflow.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        ["extract_params", "handle_unsupported", "escalate"]
    )
    workflow.add_conditional_edges(
        "extract_params",
        route_after_extract_params,
        ["validate_params"]
    )
    workflow.add_conditional_edges(
        "validate_params",
        route_after_validate,
        ["request_params", "handle_param_error", "execute_tools"]
    )

    workflow.add_edge("request_params", "persist_response")
    workflow.add_edge("handle_param_error", "escalate")
    workflow.add_edge("execute_tools", "generate_response")
    workflow.add_conditional_edges(
        "handle_unsupported",
        route_to_node,
        ["escalate", "persist_response"]
    )
    workflow.add_edge("generate_response", "persist_response")
    workflow.add_edge("escalate", "generate_response")
    workflow.add_edge("persist_response", END)

    return workflow.compile()


_agent_graph: Optional[StateGraph] = None


def get_agent_graph() -> StateGraph:
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = create_agent_graph()
    return _agent_graph


async def process_conversation(
    conversation_id: str,
    user_id: str,
    session_id: str,
    message: str,
    messages: list,
    order_id: Optional[str] = None,
    product_id: Optional[str] = None,
    execution_budget_ms: int = 8000
) -> Dict[str, Any]:
    """Process a conversation turn through the agent graph"""
    import uuid
    logger = get_logger()
    logger.info("process_conversation.start", conversation_id=conversation_id, user_id=user_id, session_id=session_id)

    graph = get_agent_graph()

    # Build initial state
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
        "extracted_params": {
            "user_id": user_id,
            **({"order_id": order_id} if order_id else {}),
            **({"product_id": product_id} if product_id else {})
        },
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
        "prompt_versions": {}
    }

    # Run the graph
    result = await graph.ainvoke(initial_state)
    logger.info("process_conversation.end", next_node=result.get("next_node", ""), escalation_required=result.get("escalation_required", False))
    return result
