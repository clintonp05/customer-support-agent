"""LangGraph node functions for the conversation agent"""
import uuid
import time
from typing import Dict, Any, Optional

from src.agent.state import ConversationState
from src.intent.registry import INTENT_REGISTRY, SUPPORT_STATUS
from src.intent.classifier import IntentClassifier
from src.intent.supported_check import check_intent_support
from src.params.extractor import extract_params
from src.params.validator import validate_params, TOOL_PARAM_SCHEMAS
from src.tools.manifest import get_tool, get_tool_chain
from src.tools.base import CircuitOpenError
from src.guard.toxicity import check_toxicity
from src.guard.pii import mask_pii
from src.guard.language import detect_language
from src.rag.pipeline import retrieve_knowledge
from src.constants import PARAM_REQUEST_TEMPLATE, TOXICITY_RESPONSE, PARAM_SWAP_RESPONSE, ESCALATION_GENERIC_RESPONSE, PARAM_STATUS_COMPLETE, PARAM_STATUS_INCOMPLETE, PARAM_STATUS_SWAP
from src.prompts.hub import PromptHubClient
from src.observability.tracer import trace_node
from src.observability.logger import get_logger


# Initialize components
classifier = IntentClassifier()
prompt_hub = PromptHubClient()
logger = get_logger()

@trace_node("guard_input")
async def guard_input_node(state: ConversationState) -> Dict[str, Any]:
    """Input guard: toxicity, PII detection, language detection"""
    raw_query = state["raw_query"]
    logger.info("guard_input.start", raw_query=raw_query)

    # Check toxicity
    is_toxic, toxicity_score = check_toxicity(raw_query)
    if is_toxic:
        return {
            "next_node": "escalate",
            "final_response": TOXICITY_RESPONSE,
            "escalation_required": True,
            "escalation_reason": "toxic_content_detected"
        }

    # Detect language
    language = detect_language(raw_query)

    # Mask PII
    safe_query = mask_pii(raw_query)

    logger.info("guard_input.complete", language=language)
    return {
        "next_node": "classify_intent",
        "extracted_params": {
            **state.get("extracted_params", {}),
            "language": language,
            "original_query": raw_query
        }
    }


@trace_node("classify_intent")
async def classify_intent_node(state: ConversationState) -> Dict[str, Any]:
    """Intent classification"""
    raw_query = state["raw_query"]

    # Classify intent
    intent, confidence = await classifier.classify(raw_query)

    logger.info("classify_intent.complete", intent=intent, confidence=confidence)

    # Check if intent is supported
    support_status, reason = check_intent_support(intent, state)

    return {
        "detected_intents": [intent] if intent else [],
        "primary_intent": intent or "",
        "intent_confidence": confidence,
        "intent_support_status": support_status,
        "escalation_reason": reason if support_status != SUPPORT_STATUS["SUPPORTED"] else None,
        "next_node": "extract_params" if support_status == SUPPORT_STATUS["SUPPORTED"] else "handle_unsupported"
    }


@trace_node("extract_params")
async def extract_params_node(state: ConversationState) -> Dict[str, Any]:
    """Extract parameters from conversation"""
    intent = state["primary_intent"]
    messages = state["messages"]

    # Get required params for this intent
    intent_config = INTENT_REGISTRY.get(intent, {})
    required_params = intent_config.get("required_params", [])

    # Extract params from message text and conversation, with existing payload
    extracted_from_message = await extract_params(intent, messages, required_params)
    cleaned = {k: v for k, v in extracted_from_message.items() if v is not None}
    extracted = {
        **state.get("extracted_params", {}),
        **cleaned,
    }

    return {
        "extracted_params": extracted,
        "next_node": "validate_params"
    }


@trace_node("validate_params")
async def validate_params_node(state: ConversationState) -> Dict[str, Any]:
    """Validate extracted parameters"""
    intent = state["primary_intent"]
    extracted_params = state["extracted_params"]

    logger

    # Get required params for this intent
    intent_config = INTENT_REGISTRY.get(intent, {})
    required_params = intent_config.get("required_params", [])

    # Check for missing params
    missing = [p for p in required_params if p not in extracted_params or not extracted_params[p]]

    if missing:
        return {
            "param_validation_status": PARAM_STATUS_INCOMPLETE,
            "missing_params": missing,
            "next_node": "request_params"
        }

    # Validate param formats
    tool_chain = get_tool_chain(intent)
    for tool_name in tool_chain[:1]:  # Validate against first tool in chain
        is_valid, missing_params, swap_error = validate_params(tool_name, extracted_params)
        if not is_valid:
            if swap_error:
                return {
                    "param_validation_status": PARAM_STATUS_SWAP,
                    "missing_params": [],
                    "next_node": "handle_param_error"
                }
            if missing_params:
                return {
                    "param_validation_status": "INCOMPLETE",
                    "missing_params": missing_params,
                    "next_node": "request_params"
                }

    return {
        "param_validation_status": PARAM_STATUS_COMPLETE,
        "missing_params": [],
        "next_node": "execute_tools"
    }


@trace_node("request_params")
async def request_params_node(state: ConversationState) -> Dict[str, Any]:
    """Request missing parameters from user"""
    missing = state["missing_params"]

    prompt = prompt_hub.get(
        "param_request",
        missing_params=", ".join(missing),
        intent=state["primary_intent"]
    )

    # For now, generate simple prompt
    response = PARAM_REQUEST_TEMPLATE.format(intent=state["primary_intent"], missing_params=", ".join(missing))

    return {
        "next_node": "end",
        "final_response": response
    }


@trace_node("handle_param_error")
async def handle_param_error_node(state: ConversationState) -> Dict[str, Any]:
    """Handle parameter errors (swap detection)"""
    return {
        "next_node": "escalate",
        "final_response": PARAM_SWAP_RESPONSE,
        "escalation_required": True,
        "escalation_reason": "param_swap_detected"
    }


@trace_node("execute_tools")
async def execute_tools_node(state: ConversationState) -> Dict[str, Any]:
    """Execute tool chain"""
    intent = state["primary_intent"]
    params = state["extracted_params"]
    tool_chain = get_tool_chain(intent)

    results = {}
    tools_executed = []
    budget_start = time.time()

    for tool_name in tool_chain:
        # Check budget
        elapsed = (time.time() - budget_start) * 1000
        if elapsed > state["execution_budget_ms"]:
            break

        tool = get_tool(tool_name)
        if not tool:
            continue

        try:
            result = await tool.execute(params, state)
            results[tool_name] = result
            tools_executed.append(tool_name)
        except CircuitOpenError:
            # Circuit breaker open - escalate
            return {
                "next_node": "escalate",
                "final_response": "I'm experiencing technical difficulties with this service. Connecting you with an agent.",
                "escalation_required": True,
                "escalation_reason": "circuit_breaker_open",
                "tool_results": results,
                "tools_executed": tools_executed
            }
        except Exception as e:
            results[tool_name] = {"success": False, "error": str(e)}
            tools_executed.append(tool_name)

    return {
        "tool_results": results,
        "tools_executed": tools_executed,
        "budget_spent_ms": int((time.time() - budget_start) * 1000),
        "next_node": "generate_response"
    }


@trace_node("generate_response")
async def generate_response_node(state: ConversationState) -> Dict[str, Any]:
    """Generate final response based on tool results"""
    intent = state["primary_intent"]
    tool_results = state["tool_results"]
    extracted_params = state["extracted_params"]

    # Retrieve relevant knowledge from RAG
    query = state["raw_query"]
    knowledge = await retrieve_knowledge(query)
    context = knowledge.get("content", "") if knowledge else ""

    # Generate response using prompt hub
    response = await generate_response(intent, tool_results, extracted_params, context)

    return {
        "final_response": response,
        "next_node": "end"
    }


async def generate_response(intent: str, tool_results: Dict, params: Dict, context: str) -> str:
    """Generate response based on intent and tool results"""

    # Check for escalation needed
    for tool_name, result in tool_results.items():
        if not result.get("success", True) and "escalate" in str(result.get("error", "")).lower():
            return "I'm having trouble processing your request. Let me connect you with a human agent."

    if intent == "refund_request":
        refund_result = tool_results.get("initiate_refund", {})
        if refund_result.get("success"):
            return f"Your refund has been processed! Refund ID: {refund_result.get('refund_id')}. The amount will be credited to your account within 5-7 business days."

    elif intent == "order_status":
        order_result = tool_results.get("check_order", {})
        if order_result.get("success"):
            order = order_result.get("order", {})
            return f"Your order {order.get('order_id')} is currently: {order.get('status', 'Unknown')}. Total: ${order.get('total_amount', 0):.2f}"

    elif intent == "delivery_tracking":
        tracking_result = tool_results.get("track_delivery", {})
        if tracking_result.get("success"):
            tracking = tracking_result.get("tracking", {})
            return f"Current status: {tracking.get('status', 'Unknown')}. Location: {tracking.get('current_location', 'N/A')}. Carrier: {tracking.get('carrier', 'N/A')}"

    elif intent == "warranty_claim":
        claim_result = tool_results.get("initiate_claim", {})
        if claim_result.get("success"):
            return f"Your warranty claim has been initiated! Claim ID: {claim_result.get('claim_id')}. " + " ".join(claim_result.get("next_steps", []))

    elif intent == "speak_to_human":
        return "I'll connect you with a customer support agent. Please hold on for a moment."

    # Generic response
    return "I've processed your request. Is there anything else I can help you with?"


@trace_node("handle_unsupported")
async def handle_unsupported_node(state: ConversationState) -> Dict[str, Any]:
    """Handle unsupported intents"""
    support_status = state["intent_support_status"]

    if support_status == SUPPORT_STATUS["IN_DOMAIN_OUT_OF_SCOPE"]:
        return {
            "final_response": "I understand your request, but this is outside my current capabilities. Let me connect you with a human agent who can help.",
            "next_node": "escalate",
            "escalation_required": True,
            "escalation_reason": "in_domain_out_of_scope"
        }
    else:
        return {
            "final_response": "I'm not able to help with that particular request. Could you try a different question?",
            "next_node": "end"
        }


@trace_node("escalate")
async def escalate_node(state: ConversationState) -> Dict[str, Any]:
    """Escalate to human agent"""
    tool = get_tool("escalate_to_human")
    if not tool:
        return {
            "final_response": ESCALATION_GENERIC_RESPONSE,
            "next_node": "end"
        }

    params = {
        "user_id": state.get("user_id", ""),
        "reason": state.get("escalation_reason", "general_inquiry"),
        "conversation_summary": str(state.get("messages", []))
    }

    try:
        result = await tool.execute(params, state)
        return {
            "final_response": result.get("message", "A customer support agent will contact you shortly."),
            "tool_results": {"escalate_to_human": result},
            "tools_executed": ["escalate_to_human"],
            "next_node": "end"
        }
    except Exception:
        return {
            "final_response": "A customer support agent will contact you shortly.",
            "next_node": "end"
        }


# Node mapping
NODES = {
    "guard_input": guard_input_node,
    "classify_intent": classify_intent_node,
    "extract_params": extract_params_node,
    "validate_params": validate_params_node,
    "request_params": request_params_node,
    "handle_param_error": handle_param_error_node,
    "execute_tools": execute_tools_node,
    "generate_response": generate_response_node,
    "handle_unsupported": handle_unsupported_node,
    "escalate": escalate_node,
}