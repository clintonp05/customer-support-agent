"""LangGraph node functions for the conversation agent"""
import uuid
import time
import re
import json
from typing import Dict, Any, Optional, List

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
from src.config import settings
from src.llm.connector import llm_generate_response, LLMConnectorClient
from src.constants import PARAM_REQUEST_TEMPLATE, TOXICITY_RESPONSE, PARAM_SWAP_RESPONSE, ESCALATION_GENERIC_RESPONSE, PARAM_STATUS_COMPLETE, PARAM_STATUS_INCOMPLETE, PARAM_STATUS_SWAP
from src.prompts.hub import PromptHubClient
from src.observability.tracer import trace_node
from src.observability.logger import get_logger
from src.cache.redis_client import get_redis_client
from src.db.conversation_store import write_conversation_turn


# Initialize components
classifier = IntentClassifier()
prompt_hub = PromptHubClient()
logger = get_logger()

STOP_CHAR_PATTERN = re.compile(r"[.!?;:]+")

@trace_node("guard_input")
async def guard_input_node(state: ConversationState) -> Dict[str, Any]:
    """Input guard: toxicity, PII detection, language detection"""
    raw_query = state["raw_query"]
    logger.info("guard_input.start", raw_query=raw_query[:100])

    # Check toxicity
    is_toxic, toxicity_score = check_toxicity(raw_query)
    if is_toxic:
        logger.warning("guard_input.toxic_detected", toxicity_score=toxicity_score)
        return {
            "next_node": "escalate",
            "final_response": TOXICITY_RESPONSE,
            "escalation_required": True,
            "escalation_reason": "toxic_content_detected"
        }

    # Detect language
    language = detect_language(raw_query)
    logger.info("guard_input.language_detected", language=language)

    # Mask PII
    safe_query, pii_types = mask_pii(raw_query)
    if pii_types:
        logger.info("guard_input.pii_masked", pii_types=pii_types)

    logger.info("guard_input.complete", language=language, is_toxic=is_toxic, pii_count=len(pii_types) if pii_types else 0)
    return {
        "next_node": "query_analyser",
        "extracted_params": {
            **state.get("extracted_params", {}),
            "language": language,
            "original_query": raw_query
        }
    }


@trace_node("query_analyser")
async def query_analyser_node(state: ConversationState) -> Dict[str, Any]:
    """Fan-out node for query analysis sub-agents."""
    return {"next_node": "query_analyse_join"}


@trace_node("intent_analyser")
async def intent_analyser_node(state: ConversationState) -> Dict[str, Any]:
    """Intent classification sub-agent."""
    raw_query = state["raw_query"]
    intent, confidence = await classifier.classify(raw_query)
    logger.info("intent_analyser.complete", intent=intent, confidence=confidence)

    support_status, reason = check_intent_support(intent, state)

    return {
        "detected_intents": [intent] if intent else [],
        "primary_intent": intent or "",
        "intent_confidence": confidence,
        "intent_support_status": support_status,
        "escalation_reason": reason if support_status != SUPPORT_STATUS["SUPPORTED"] else None,
    }


def _split_by_stop_chars(text: str) -> List[str]:
    parts = STOP_CHAR_PATTERN.split(text)
    return [p.strip() for p in parts if p.strip()]


def _heuristic_complexity(word_count: int, sentence_count: int) -> str:
    if word_count <= 8 and sentence_count <= 1:
        return "simple"
    if word_count <= 20 and sentence_count <= 2:
        return "moderate"
    return "complex"


@trace_node("complexity_analyser")
async def complexity_analyser_node(state: ConversationState) -> Dict[str, Any]:
    """Analyze query complexity via LLM + sentence heuristics."""
    raw_query = state["raw_query"]
    segments = _split_by_stop_chars(raw_query)
    sentence_count = len(segments)
    word_count = len(raw_query.split())
    char_count = len(raw_query)
    avg_sentence_len = (word_count / sentence_count) if sentence_count > 0 else word_count

    llm_complexity = None
    try:
        client = LLMConnectorClient("SPEED")
        prompt = (
            "Classify the user query complexity as one word: simple, moderate, or complex.\n"
            f"Query: {raw_query}\n"
            "Answer with a single word."
        )
        result = client.generate(prompt, max_tokens=8)
        if result.get("success"):
            llm_text = result.get("response", "").lower()
            if "complex" in llm_text:
                llm_complexity = "complex"
            elif "moderate" in llm_text or "medium" in llm_text:
                llm_complexity = "moderate"
            elif "simple" in llm_text:
                llm_complexity = "simple"
    except Exception as exc:
        logger.warning("complexity_analyser.llm_failed", error=str(exc))

    heuristic = _heuristic_complexity(word_count, sentence_count)
    final_complexity = llm_complexity or heuristic

    return {
        "query_analysis": {
            **state.get("query_analysis", {}),
            "complexity": final_complexity,
            "llm_complexity": llm_complexity,
            "heuristic_complexity": heuristic,
            "sentence_count": sentence_count,
            "word_count": word_count,
            "char_count": char_count,
            "avg_sentence_length": avg_sentence_len,
            "stop_char_splits": sentence_count,
            "segments": segments,
        }
    }


@trace_node("query_analyse_join")
async def query_analyse_join_node(state: ConversationState) -> Dict[str, Any]:
    """Join intent + complexity analysis and route."""
    support_status = state.get("intent_support_status", SUPPORT_STATUS["SUPPORTED"])
    if support_status != SUPPORT_STATUS["SUPPORTED"]:
        return {"next_node": "handle_unsupported"}
    return {"next_node": "extract_params"}


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

    logger.info("extract_params.start", intent=intent, message_count=len(messages))

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

    logger.info("extract_params.complete", intent=intent, extracted_params=list(extracted.keys()), required_params=required_params)

    return {
        "extracted_params": extracted,
        "next_node": "validate_params"
    }


@trace_node("validate_params")
async def validate_params_node(state: ConversationState) -> Dict[str, Any]:
    """Validate extracted parameters"""
    intent = state["primary_intent"]
    extracted_params = state["extracted_params"]

    logger.info("validate_params.start", intent=intent, extracted_keys=list(extracted_params.keys()))

    # Get required params for this intent
    intent_config = INTENT_REGISTRY.get(intent, {})
    required_params = intent_config.get("required_params", [])

    # Check for missing params
    missing = [p for p in required_params if p not in extracted_params or not extracted_params[p]]

    if missing:
        logger.info("validate_params.incomplete", intent=intent, missing_params=missing)
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
                logger.warning("validate_params.swap_detected", intent=intent, tool_name=tool_name)
                return {
                    "param_validation_status": PARAM_STATUS_SWAP,
                    "missing_params": [],
                    "next_node": "handle_param_error"
                }
            if missing_params:
                logger.info("validate_params.incomplete_after_validation", intent=intent, missing_params=missing_params)
                return {
                    "param_validation_status": "INCOMPLETE",
                    "missing_params": missing_params,
                    "next_node": "request_params"
                }

    logger.info("validate_params.complete", intent=intent, status="COMPLETE")
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

    logger.info("execute_tools.start", intent=intent, tool_chain=tool_chain, params=list(params.keys()))

    results = {}
    tools_executed = []
    budget_start = time.time()

    for tool_name in tool_chain:
        # Check budget
        elapsed = (time.time() - budget_start) * 1000
        if elapsed > state["execution_budget_ms"]:
            logger.warning("execute_tools.budget_exceeded", elapsed_ms=int(elapsed), budget_ms=state["execution_budget_ms"])
            break

        tool = get_tool(tool_name)
        if not tool:
            logger.warning("execute_tools.tool_not_found", tool_name=tool_name)
            continue

        try:
            logger.info("execute_tools.executing", tool_name=tool_name)
            result = await tool.execute(params, state)
            results[tool_name] = result
            tools_executed.append(tool_name)
            logger.info("execute_tools.tool_result", tool_name=tool_name, success=result.get("success", True))
        except CircuitOpenError:
            # Circuit breaker open - escalate
            logger.error("execute_tools.circuit_open", tool_name=tool_name)
            return {
                "next_node": "escalate",
                "final_response": "I'm experiencing technical difficulties with this service. Connecting you with an agent.",
                "escalation_required": True,
                "escalation_reason": "circuit_breaker_open",
                "tool_results": results,
                "tools_executed": tools_executed
            }
        except Exception as e:
            logger.error("execute_tools.tool_error", tool_name=tool_name, error=str(e))
            results[tool_name] = {"success": False, "error": str(e)}
            tools_executed.append(tool_name)

    budget_spent = int((time.time() - budget_start) * 1000)
    logger.info("execute_tools.complete", tools_executed=tools_executed, budget_spent_ms=budget_spent)

    return {
        "tool_results": results,
        "tools_executed": tools_executed,
        "budget_spent_ms": budget_spent,
        "next_node": "generate_response"
    }


@trace_node("generate_response")
async def generate_response_node(state: ConversationState) -> Dict[str, Any]:
    """Generate final response based on tool results"""
    intent = state["primary_intent"]
    tool_results = state["tool_results"]
    extracted_params = state["extracted_params"]

    logger.info("generate_response.start", intent=intent, tool_results=list(tool_results.keys()))

    query = state["raw_query"]
    context = ""
    if intent in {"refund_request", "warranty_claim"}:
        logger.info("generate_response.retrieving_knowledge", intent=intent)
        knowledge = await retrieve_knowledge(query)
        context = knowledge.get("content", "") if knowledge else ""
        logger.info("generate_response.knowledge_retrieved", context_length=len(context))

    # Build simple conversation string
    conversation_text = "\n".join(
        [f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in state.get("messages", [])]
    )

    response = await generate_response(intent, tool_results, extracted_params, conversation_text, context)
    logger.info("generate_response.complete", intent=intent, response_length=len(response), response_snippet=response[:80])

    return {
        "final_response": response,
        "next_node": "persist_response"
    }


@trace_node("persist_response")
async def persist_response_node(state: ConversationState) -> Dict[str, Any]:
    """Persist final response to DB and cache query/response in Redis."""
    conversation_id = state.get("conversation_id", "")
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    raw_query = state.get("raw_query", "")
    final_response = state.get("final_response", "") or ""
    messages = state.get("messages", [])
    query_analysis = state.get("query_analysis", {})
    tool_results = state.get("tool_results", {})
    turn_index = state.get("current_turn", 0)

    stored_db = write_conversation_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        session_id=session_id,
        turn_index=turn_index,
        raw_query=raw_query,
        final_response=final_response,
        messages=messages,
        query_analysis=query_analysis,
        tool_results=tool_results,
    )
    if stored_db:
        logger.info("persist_response.db_complete", conversation_id=conversation_id, turn_index=turn_index)

    redis_client = get_redis_client()
    if redis_client is not None:
        key = f"query:{conversation_id}:{turn_index}"
        payload = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "session_id": session_id,
            "turn_index": turn_index,
            "raw_query": raw_query,
            "final_response": final_response,
            "query_analysis": query_analysis,
        }
        try:
            ttl_s = max(0, int(getattr(settings, "redis_query_ttl_s", 0)))
            if ttl_s > 0:
                redis_client.setex(key, ttl_s, json.dumps(payload, ensure_ascii=False))
            else:
                redis_client.set(key, json.dumps(payload, ensure_ascii=False))
            logger.info("persist_response.redis_complete", key=key)
        except Exception as exc:
            logger.warning("persist_response.redis_failed", error=str(exc))

    return {"next_node": "end"}


async def generate_response(intent: str, tool_results: Dict, params: Dict, conversation: str, context: str) -> str:
    """Generate response based on intent and tool results"""

    # Check for escalation needed
    for tool_name, result in tool_results.items():
        if not result.get("success", True) and "escalate" in str(result.get("error", "")).lower():
            return "I'm having trouble processing your request. Let me connect you with a human agent."

    llm_intents = {"refund_request", "warranty_claim", "order_status", "delivery_tracking"}
    if intent in llm_intents:
        # choose tier by intent
        if intent in {"order_status", "delivery_tracking"}:
            tier = "SPEED"
        elif intent in {"refund_request", "warranty_claim"}:
            tier = "BALANCED"
        else:
            tier = "BALANCED"

        # Use tool results to construct final answer
        llm_response = llm_generate_response(intent, conversation, tool_results, params, context=context, speed_tier=tier)
        if llm_response:
            return llm_response

    if intent == "refund_request":
        refund_result = tool_results.get("initiate_refund", {})
        if refund_result.get("success"):
            return f"Your refund has been processed! Refund ID: {refund_result.get('refund_id')}. The amount will be credited to your account within 5-7 business days."

    elif intent == "order_status":
        order_result = tool_results.get("check_order", {})
        if order_result.get("success"):
            order = order_result.get("order", {})
            logger.info("generate_response.order_status", order_id=order.get("order_id"), status=order.get("status"))
            return f"Your order {order.get('order_id')} is currently: {order.get('status', 'Unknown')}. Total: ${order.get('total_amount', 0):.2f}"
        if order_result.get("error") == "ORDER_NOT_FOUND" or "not found" in str(order_result.get("message", "")).lower():
            return "Order not found. Please verify the order ID and try again."

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
            "next_node": "persist_response"
        }


@trace_node("escalate")
async def escalate_node(state: ConversationState) -> Dict[str, Any]:
    """Escalate to human agent"""
    logger.info("escalate.start", reason=state.get("escalation_reason"))

    tool = get_tool("escalate_to_human")
    if not tool:
        logger.warning("escalate.tool_not_found")
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
        logger.info("escalate.complete", success=result.get("success", True))
        return {
            "final_response": result.get("message", "A customer support agent will contact you shortly."),
            "tool_results": {"escalate_to_human": result},
            "tools_executed": ["escalate_to_human"],
            "next_node": "end"
        }
    except Exception as e:
        logger.error("escalate.error", error=str(e))
        return {
            "final_response": "A customer support agent will contact you shortly.",
            "next_node": "end"
        }


# Node mapping
NODES = {
    "guard_input": guard_input_node,
    "query_analyser": query_analyser_node,
    "intent_analyser": intent_analyser_node,
    "complexity_analyser": complexity_analyser_node,
    "query_analyse_join": query_analyse_join_node,
    "classify_intent": classify_intent_node,
    "extract_params": extract_params_node,
    "validate_params": validate_params_node,
    "request_params": request_params_node,
    "handle_param_error": handle_param_error_node,
    "execute_tools": execute_tools_node,
    "generate_response": generate_response_node,
    "persist_response": persist_response_node,
    "handle_unsupported": handle_unsupported_node,
    "escalate": escalate_node,
}
