"""Conditional edge routing logic for LangGraph"""
from typing import Literal
from src.agent.state import ConversationState
from src.params.validator import TOOL_PARAM_SCHEMAS


def route_after_guard(state: ConversationState) -> str:
    """Route after input guard"""
    if state.get("escalation_required"):
        return "escalate"
    return state.get("next_node", "query_analyser")


def route_after_query_analyse(state: ConversationState) -> str:
    """Route after query analysis"""
    return state.get("next_node", "extract_params")


def route_after_classify(state: ConversationState) -> str:
    """Route after intent classification"""
    return state.get("next_node", "extract_params")


def route_after_extract_params(state: ConversationState) -> str:
    """Route after parameter extraction"""
    return state.get("next_node", "validate_params")


def route_after_validate(state: ConversationState) -> str:
    """Route after param validation"""
    validation_status = state.get("param_validation_status", "COMPLETE")

    if validation_status == "INCOMPLETE":
        return "request_params"
    elif validation_status == "SWAP_DETECTED":
        return "handle_param_error"
    else:
        return "execute_tools"


def route_after_execute(state: ConversationState) -> str:
    """Route after tool execution"""
    return state.get("next_node", "generate_response")


def route_to_node(state: ConversationState) -> str:
    """Generic routing based on next_node"""
    return state.get("next_node", "end")


# Edge mapping
EDGES = {
    "guard_input": route_after_guard,
    "query_analyse_join": route_after_query_analyse,
    "classify_intent": route_after_classify,
    "extract_params": route_after_extract_params,
    "validate_params": route_after_validate,
    "execute_tools": route_after_execute,
    "handle_unsupported": route_to_node,
}
