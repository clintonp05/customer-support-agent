"""LangGraph node functions for the conversation agent"""
import asyncio
import uuid
import time
import re
import json
import hashlib
from typing import Dict, Any, Optional, List, Tuple

from src.agent.state import ConversationState
from src.intent.registry import INTENT_REGISTRY, SUPPORT_STATUS
from src.intent.classifier import IntentClassifier
from src.intent.supported_check import check_intent_support
from src.intent.multi_intent import split_into_intents
from src.params.extractor import extract_params
from src.params.validator import validate_params, TOOL_PARAM_SCHEMAS
from src.tools.manifest import get_tool, get_tool_chain
from src.tools.base import CircuitOpenError
from src.guard.toxicity import check_toxicity
from src.guard.pii import mask_pii
from src.guard.language import detect_language
from src.guard.emotion import detect_emotion, is_high_value_order
from src.rag.pipeline import retrieve_knowledge
from src.eval.ragas_eval import schedule_faithfulness_eval
from src.config import settings
from src.llm.connector import llm_generate_response, LLMConnectorClient, llm_stream_generate_response
from src.constants import PARAM_REQUEST_TEMPLATE, TOXICITY_RESPONSE, PARAM_SWAP_RESPONSE, ESCALATION_GENERIC_RESPONSE, PARAM_STATUS_COMPLETE, PARAM_STATUS_INCOMPLETE, PARAM_STATUS_SWAP
from src.prompts.hub import PromptHubClient
from src.observability.tracer import trace_node
from src.observability.logger import get_logger
from src.observability.metrics_exporter import (
    record_tool_call, record_conversation_resolution, record_escalation_reason,
    record_conversation_outcome, record_response_latency, record_rag_latency,
    record_multi_intent, record_cost_per_conversation,
    record_intent_classification, record_circuit_breaker_state,
)
from src.cache.redis_client import get_redis_client
from src.db.conversation_store import write_conversation_turn


# Initialize components
classifier = IntentClassifier()
prompt_hub = PromptHubClient()
logger = get_logger()

# Per-conversation token queues for streaming: conversation_id → asyncio.Queue
# The route registers a queue before starting the graph; generate_response_node pushes
# text chunks into it; None sentinel signals end-of-stream.
_token_queues: Dict[str, asyncio.Queue] = {}


def register_token_queue(conversation_id: str, queue: "asyncio.Queue[Optional[str]]") -> None:
    _token_queues[conversation_id] = queue


def deregister_token_queue(conversation_id: str) -> None:
    _token_queues.pop(conversation_id, None)


async def _flush_queue_with_response(conversation_id: str, response: str) -> None:
    """Push a pre-built response to the SSE queue then signal end-of-stream.

    Called by nodes that bypass generate_response_node (cache hit, param request,
    unsupported intent) so the SSE client is never left waiting for a sentinel.
    """
    queue = _token_queues.get(conversation_id)
    if queue is None:
        return
    if response:
        await queue.put(response)
    await queue.put(None)  # EOF sentinel


STOP_CHAR_PATTERN = re.compile(r"[.!?;:]+")
REACT_PROMPT_TEMPLATE = (
    "You are an orchestrator. Analyze the user's complex query, identify distinct intents, "
    "and propose refined sub-queries for each intent. "
    "Return a short plan with bullet points (no tools)."
)

@trace_node("guard_input")
async def guard_input_node(state: ConversationState) -> Dict[str, Any]:
    """Input guard: toxicity, PII detection, language detection"""
    start = time.perf_counter()
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

    # Emotion / signal detection — runs on original (pre-PII-mask) query for accuracy
    emotion = detect_emotion(raw_query)
    logger.info("guard_input.emotion", **emotion)

    logger.info("guard_input.complete", language=language, is_toxic=is_toxic, pii_count=len(pii_types) if pii_types else 0)
    # Skip cache for churn-risk / delivery-dispute queries — always serve fresh
    skip_cache = emotion.get("churn_signal") or emotion.get("delivery_dispute")

    cache_key = None
    cache_hit = False
    cache_payload = None
    redis_client = get_redis_client()
    if redis_client is not None:
        # Scope cache key to conversation context so different users/sessions
        # never share cached responses for the same query text.
        # Also include session-provided order_id / product_id so that queries
        # like "check my order" with different order IDs in the payload don't
        # collide on the same cache bucket.
        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        conversation_id = state.get("conversation_id", "")
        session_params = state.get("extracted_params", {})
        session_order_id = session_params.get("order_id", "")
        session_product_id = session_params.get("product_id", "")
        cache_input = f"{user_id}:{session_id}:{conversation_id}:{session_order_id}:{session_product_id}:{raw_query.strip().lower()}"
        key = hashlib.sha256(cache_input.encode("utf-8")).hexdigest()
        cache_key = f"query_hash:{key}"
        try:
            cached = redis_client.get(cache_key)
            cache_hit = cached is not None and not skip_cache
            logger.info("cache.lookup", key=cache_key, hit=cache_hit, skipped=skip_cache)
            if cache_hit:
                cache_payload = json.loads(cached)
        except Exception as exc:
            logger.warning("cache.lookup_failed", error=str(exc))
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "next_node": "serve_cache" if cache_hit else "query_analyser",
        "emotion": emotion,
        "extracted_params": {
            **state.get("extracted_params", {}),
            "language": language,
            "original_query": raw_query
        },
        "query_analysis": {
            **state.get("query_analysis", {}),
            "cache_key": cache_key,
            "cache_hit": cache_hit,
        }
        ,
        "cache_payload": cache_payload,
        "timings_ms": {
            **state.get("timings_ms", {}),
            "guard_input": elapsed_ms
        }
    }


@trace_node("query_analyser")
async def query_analyser_node(state: ConversationState) -> Dict[str, Any]:
    """Fan-out node for query analysis sub-agents."""
    return {"next_node": "query_analyse_join"}


@trace_node("intent_analyser")
async def intent_analyser_node(state: ConversationState) -> Dict[str, Any]:
    """Intent classification sub-agent."""
    start = time.perf_counter()
    raw_query = state["raw_query"]
    intent, confidence = await classifier.classify(raw_query, messages=state.get("messages"))
    logger.info("intent_analyser.complete", intent=intent, confidence=confidence)
    record_intent_classification(intent or "unknown", "classified" if confidence >= 0.5 else "fallback")

    support_status, reason = check_intent_support(intent, state)

    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "detected_intents": [intent] if intent else [],
        "primary_intent": intent or "",
        "intent_confidence": confidence,
        "intent_support_status": support_status,
        "escalation_reason": reason if support_status != SUPPORT_STATUS["SUPPORTED"] else None,
        "timings_ms": {
            **state.get("timings_ms", {}),
            "intent_classification": elapsed_ms
        }
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
    start = time.perf_counter()
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

    elapsed_ms = (time.perf_counter() - start) * 1000
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
        ,
        "timings_ms": {
            **state.get("timings_ms", {}),
            "complexity_analysis": elapsed_ms
        }
    }


@trace_node("query_analyse_join")
async def query_analyse_join_node(state: ConversationState) -> Dict[str, Any]:
    """Join intent + complexity analysis and route."""
    support_status = state.get("intent_support_status", SUPPORT_STATUS["SUPPORTED"])
    if support_status != SUPPORT_STATUS["SUPPORTED"]:
        return {"next_node": "handle_unsupported"}
    return {"next_node": "complex_query_orchestrator"}


@trace_node("complex_query_orchestrator")
async def complex_query_orchestrator_node(state: ConversationState) -> Dict[str, Any]:
    """Orchestrator for complex query analysis.

    is_complex is now driven purely by whether split_into_intents() returns
    multiple meaningful segments — the old char_count > 100 gate was blocking
    short but genuinely multi-intent queries like
    "what is the refund policy and warranty for electronics?" (50 chars).
    """
    raw_query = state["raw_query"]
    char_count = len(raw_query)
    intent_segments = split_into_intents(raw_query)
    is_complex = len(intent_segments) > 1  # char_count gate removed

    react_plan = None
    if is_complex:
        logger.info("complex_query.multi_intent_detected",
                    segment_count=len(intent_segments),
                    segments=intent_segments,
                    char_count=char_count)
        try:
            client = LLMConnectorClient("BALANCED")
            react_prompt = f"{REACT_PROMPT_TEMPLATE}\n\nUser Query: {raw_query}\n"
            react_result = client.generate(react_prompt, max_tokens=256)
            if react_result.get("success"):
                react_plan = react_result.get("response", "").strip()
        except Exception as exc:
            logger.warning("complex_query.react_failed", error=str(exc))

    return {
        "query_analysis": {
            **state.get("query_analysis", {}),
            "multi_intents": intent_segments,
            "intent_count": len(intent_segments),
            "is_complex": is_complex,
            "char_count": char_count,
            "complexity_reason": "multi_intent" if is_complex else "single_intent",
            "react_plan": react_plan,
        }
    }


@trace_node("complex_intent_agent")
async def complex_intent_agent_node(state: ConversationState) -> Dict[str, Any]:
    """Sub-agent: classify each intent chunk in a complex query."""
    analysis = state.get("query_analysis", {})
    if not analysis.get("is_complex"):
        return {}

    intent_segments = analysis.get("multi_intents", [])
    labels = []
    confidences = []
    messages = state.get("messages")
    for segment in intent_segments:
        intent, confidence = await classifier.classify(segment, messages=messages)
        labels.append(intent)
        confidences.append(confidence)

    primary_intent = ""
    if labels and confidences:
        best_idx = max(range(len(confidences)), key=lambda i: confidences[i])
        primary_intent = labels[best_idx] or ""

    return {
        "detected_intents": [label for label in labels if label],
        "primary_intent": primary_intent or state.get("primary_intent", ""),
        "query_analysis": {
            **analysis,
            "multi_intent_labels": labels,
            "multi_intent_confidences": confidences,
        },
    }


@trace_node("complex_refine_agent")
async def complex_refine_agent_node(state: ConversationState) -> Dict[str, Any]:
    """Sub-agent: refine intent chunks for downstream analysis."""
    analysis = state.get("query_analysis", {})
    if not analysis.get("is_complex"):
        return {}

    intent_segments = analysis.get("multi_intents", [])
    refined = [segment.strip() for segment in intent_segments if segment.strip()]
    return {
        "query_analysis": {
            **analysis,
            "refined_queries": refined,
        }
    }


@trace_node("complex_query_join")
async def complex_query_join_node(state: ConversationState) -> Dict[str, Any]:
    """Join complex sub-agents and continue."""
    return {"next_node": "extract_params"}


@trace_node("classify_intent")
async def classify_intent_node(state: ConversationState) -> Dict[str, Any]:
    """Intent classification"""
    raw_query = state["raw_query"]

    # Classify intent using current message + conversation history for context
    intent, confidence = await classifier.classify(raw_query, messages=state.get("messages"))

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
    start = time.perf_counter()
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

    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "extracted_params": extracted,
        "next_node": "validate_params",
        "timings_ms": {
            **state.get("timings_ms", {}),
            "param_extraction": elapsed_ms
        }
    }


@trace_node("validate_params")
async def validate_params_node(state: ConversationState) -> Dict[str, Any]:
    """Validate extracted parameters"""
    start = time.perf_counter()
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
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "param_validation_status": PARAM_STATUS_INCOMPLETE,
            "missing_params": missing,
            "next_node": "request_params",
            "timings_ms": {
                **state.get("timings_ms", {}),
                "param_validation": elapsed_ms
            }
        }

    # Validate param formats
    tool_chain = get_tool_chain(intent)
    for tool_name in tool_chain[:1]:  # Validate against first tool in chain
        is_valid, missing_params, swap_error = validate_params(tool_name, extracted_params)
        if not is_valid:
            if swap_error:
                logger.warning("validate_params.swap_detected", intent=intent, tool_name=tool_name)
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {
                    "param_validation_status": PARAM_STATUS_SWAP,
                    "missing_params": [],
                    "next_node": "handle_param_error",
                    "timings_ms": {
                        **state.get("timings_ms", {}),
                        "param_validation": elapsed_ms
                    }
                }
            if missing_params:
                logger.info("validate_params.incomplete_after_validation", intent=intent, missing_params=missing_params)
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {
                    "param_validation_status": "INCOMPLETE",
                    "missing_params": missing_params,
                    "next_node": "request_params",
                    "timings_ms": {
                        **state.get("timings_ms", {}),
                        "param_validation": elapsed_ms
                    }
                }

    logger.info("validate_params.complete", intent=intent, status="COMPLETE")
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "param_validation_status": PARAM_STATUS_COMPLETE,
        "missing_params": [],
        "next_node": "execute_tools",
        "timings_ms": {
            **state.get("timings_ms", {}),
            "param_validation": elapsed_ms
        }
    }


@trace_node("request_params")
async def request_params_node(state: ConversationState) -> Dict[str, Any]:
    """Request missing parameters from user.

    Routes to persist_response (not "end") so the turn is recorded in DB and
    metrics are emitted.  Signals the SSE queue so the client receives the
    prompt immediately.
    """
    missing = state.get("missing_params", [])
    intent = state.get("primary_intent", "")

    prompt_hub.get(
        "param_request",
        missing_params=", ".join(missing),
        intent=intent,
    )
    response = PARAM_REQUEST_TEMPLATE.format(intent=intent, missing_params=", ".join(missing))

    conversation_id = state.get("conversation_id", "")
    await _flush_queue_with_response(conversation_id, response)
    logger.info("request_params.queue_flushed", conversation_id=conversation_id,
                missing=missing, intent=intent)

    return {
        "next_node": "persist_response",
        "final_response": response,
        # Signal that this turn is not a resolution — persist_response uses this
        # to record "waiting_for_params" instead of "resolved"
        "param_validation_status": "INCOMPLETE",
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


_INTENT_PROGRESS_MESSAGES: Dict[str, str] = {
    "order_status": "Checking order details...",
    "delivery_tracking": "Verifying delivery status...",
    "refund_request": "Checking refund eligibility...",
    "warranty_claim": "Looking up warranty information...",
    "cancel_order": "Checking order status for cancellation...",
    "product_inquiry": "Fetching product information...",
    "general_inquiry": "Searching knowledge base...",
    "speak_to_human": "Connecting to support team...",
}


def _build_progress_messages(detected_intents: List[str]) -> List[str]:
    """Return UI progress messages for the detected intents."""
    seen: set = set()
    msgs = []
    for intent in detected_intents:
        msg = _INTENT_PROGRESS_MESSAGES.get(intent)
        if msg and msg not in seen:
            seen.add(msg)
            msgs.append(msg)
    return msgs


async def _run_single_intent_chain(
    intent: str,
    params: Dict[str, Any],
    state: ConversationState,
    budget_remaining_ms: float,
) -> Tuple[Dict[str, Any], List[str], Optional[str], Optional[str]]:
    """Run all tools in a single intent's chain.

    Returns (results_dict, tools_executed, escalate_reason_or_None, escalation_message_or_None).
    Fully traced: each tool is logged with intent scope for dashboard correlation.
    """
    tool_chain = get_tool_chain(intent)
    results: Dict[str, Any] = {}
    tools_executed: List[str] = []
    budget_start = time.time()
    escalate_reason: Optional[str] = None
    escalation_msg: Optional[str] = None

    logger.info("execute_tools.intent_chain.start", intent=intent, tool_chain=tool_chain)

    for tool_name in tool_chain:
        elapsed = (time.time() - budget_start) * 1000
        if elapsed > budget_remaining_ms:
            logger.warning("execute_tools.intent_chain.budget_exceeded",
                           intent=intent, elapsed_ms=int(elapsed))
            break

        tool = get_tool(tool_name)
        if not tool:
            logger.warning("execute_tools.tool_not_found", tool_name=tool_name, intent=intent)
            continue

        try:
            tool_start = time.perf_counter()
            logger.info("execute_tools.executing", tool_name=tool_name, intent=intent)
            result = await tool.execute(params, state)
            tool_elapsed = (time.perf_counter() - tool_start) * 1000

            # Namespace key by intent when running multiple chains so results don't collide
            results[tool_name] = result
            tools_executed.append(tool_name)
            success = result.get("success", True)
            logger.info("execute_tools.tool_result", tool_name=tool_name,
                        intent=intent, success=success, elapsed_ms=round(tool_elapsed, 1))
            # Distinguish business-logic "not found" from infra failures so the
            # Error Rate panel only counts real errors, not missing-order queries.
            if success:
                tool_status = "success"
            elif result.get("error") in {
                "ORDER_NOT_FOUND", "MISSING_ORDER_ID", "PRODUCT_NOT_FOUND",
                "WARRANTY_NOT_FOUND", "WARRANTY_EXPIRED", "REFUND_NOT_ELIGIBLE",
                "DELIVERY_NOT_FOUND",
            }:
                tool_status = "not_found"
            else:
                tool_status = "failure"
            record_tool_call(tool_name, tool_status, tool_elapsed)

            if tool_name == "check_refund_eligibility" and not result.get("eligible", True):
                logger.info("execute_tools.refund_ineligible",
                            intent=intent, reason=result.get("reason"))
                escalate_reason = "refund_ineligible"
                escalation_msg = (
                    f"Your refund request cannot be processed: "
                    f"{result.get('reason', 'ineligible')}. "
                    "Let me connect you with a support agent."
                )
                break

        except CircuitOpenError:
            logger.error("execute_tools.circuit_open", tool_name=tool_name, intent=intent)
            record_tool_call(tool_name, "circuit_open", 0)
            record_circuit_breaker_state(tool_name, True)
            escalate_reason = "circuit_breaker_open"
            escalation_msg = (
                "I'm experiencing technical difficulties with this service. "
                "Connecting you with an agent."
            )
            break

        except Exception as exc:
            logger.error("execute_tools.tool_error",
                         tool_name=tool_name, intent=intent, error=str(exc))
            record_tool_call(tool_name, "error", 0)
            results[tool_name] = {"success": False, "error": str(exc)}
            tools_executed.append(tool_name)

    chain_ms = (time.time() - budget_start) * 1000
    logger.info("execute_tools.intent_chain.complete",
                intent=intent, tools_executed=tools_executed,
                escalated=escalate_reason is not None, elapsed_ms=round(chain_ms, 1))
    return results, tools_executed, escalate_reason, escalation_msg


@trace_node("execute_tools")
async def execute_tools_node(state: ConversationState) -> Dict[str, Any]:
    """Execute tool chains for ALL detected intents in parallel.

    For multi-intent queries (e.g. "refund policy AND warranty") each intent
    gets its own independent tool chain run concurrently via asyncio.gather.
    Results are merged into tool_results keyed by tool name. Each chain is
    fully logged with intent scope for per-intent traceability on dashboards.
    """
    start = time.perf_counter()
    primary_intent = state["primary_intent"]
    detected_intents: List[str] = state.get("detected_intents") or [primary_intent]
    params = state["extracted_params"]
    budget_ms = float(state.get("execution_budget_ms", 8000))

    emotion: Dict[str, Any] = state.get("emotion") or {}
    user_id = params.get("user_id", state.get("user_id", ""))

    logger.info("execute_tools.start",
                primary_intent=primary_intent,
                detected_intents=detected_intents,
                params=list(params.keys()),
                emotion_weight=emotion.get("escalation_weight", 0))

    # Push progress messages to UI token_queue before tool execution
    conversation_id = state.get("conversation_id", "")
    token_queue = _token_queues.get(conversation_id)
    progress_msgs = _build_progress_messages(detected_intents)
    if token_queue is not None:
        for msg in progress_msgs:
            await token_queue.put(f"__progress__:{msg}")

    # Always fetch customer history in parallel when emotion signals are elevated
    # (churn signal, repeat complaint, delivery dispute, escalation_weight >= 2)
    needs_history = (
        emotion.get("churn_signal")
        or emotion.get("repeat_complaint")
        or emotion.get("delivery_dispute")
        or emotion.get("escalation_weight", 0) >= 2
    )

    # Run each intent's tool chain concurrently; optionally add history fetch
    chain_coros = [
        _run_single_intent_chain(intent, params, state, budget_ms)
        for intent in detected_intents
    ]
    history_coro = None
    if needs_history and user_id:
        history_tool = get_tool("get_customer_history")
        if history_tool:
            history_coro = history_tool.execute({"user_id": user_id}, state)

    if history_coro:
        all_coros = chain_coros + [history_coro]
        all_outputs = await asyncio.gather(*all_coros, return_exceptions=True)
        chain_outputs = all_outputs[:-1]
        history_result = all_outputs[-1] if not isinstance(all_outputs[-1], Exception) else {}
    else:
        chain_outputs = await asyncio.gather(*chain_coros, return_exceptions=False)
        history_result = {}

    # Merge results from all chains
    merged_results: Dict[str, Any] = {}
    all_tools_executed: List[str] = []
    timings: Dict[str, float] = dict(state.get("timings_ms", {}))
    first_escalation_reason: Optional[str] = None
    first_escalation_msg: Optional[str] = None

    for intent, chain_output in zip(detected_intents, chain_outputs):
        if isinstance(chain_output, Exception):
            logger.error("execute_tools.chain_error", intent=intent, error=str(chain_output))
            continue
        results, tools_executed, esc_reason, esc_msg = chain_output
        merged_results.update(results)
        all_tools_executed.extend(tools_executed)
        if esc_reason and first_escalation_reason is None:
            first_escalation_reason = esc_reason
            first_escalation_msg = esc_msg

    # Customer history result
    customer_history = history_result.get("history") if history_result.get("success") else {}

    budget_spent = int((time.perf_counter() - start) * 1000)
    elapsed_ms = (time.perf_counter() - start) * 1000
    timings["execute_tools_total"] = elapsed_ms

    # --- Delivery dispute decision logic ---
    # "Marked delivered but not received" + (high-value OR repeat issue OR churn signal)
    # → above bot's auto-resolution authority → escalate with rich packet
    if not first_escalation_reason:
        delivery_result = merged_results.get("track_delivery", {})
        order_result = merged_results.get("check_order", {})
        order_data = order_result.get("order", {}) or {}
        delivery_data = delivery_result.get("tracking", {}) or {}

        is_marked_delivered = (
            delivery_data.get("status", "").lower() in ("delivered", "تم التسليم")
            or order_data.get("status", "").lower() == "delivered"
        )
        is_delivery_dispute = emotion.get("delivery_dispute") and is_marked_delivered
        is_high_value = is_high_value_order(order_data)
        is_repeat = (
            emotion.get("repeat_complaint")
            or (customer_history or {}).get("is_repeat_delivery_issue")
        )
        is_churn = emotion.get("churn_signal")

        if is_delivery_dispute and (is_high_value or is_repeat or is_churn):
            churn_risk = (customer_history or {}).get("churn_risk", "medium")
            recommended = (customer_history or {}).get("recommended_action", "full_refund")
            first_escalation_reason = "delivery_dispute_high_authority"
            first_escalation_msg = f"delivery_dispute|churn_risk:{churn_risk}|recommended:{recommended}"
            logger.info(
                "execute_tools.delivery_dispute_escalate",
                is_high_value=is_high_value, is_repeat=is_repeat,
                is_churn=is_churn, churn_risk=churn_risk,
            )

    logger.info("execute_tools.complete",
                tools_executed=all_tools_executed,
                intents_executed=detected_intents,
                budget_spent_ms=budget_spent,
                escalated=first_escalation_reason is not None)

    base_return = {
        "tool_results": merged_results,
        "tools_executed": all_tools_executed,
        "budget_spent_ms": budget_spent,
        "customer_history": customer_history or {},
        "timings_ms": timings,
    }

    if first_escalation_reason:
        return {
            **base_return,
            "next_node": "escalate",
            "escalation_required": True,
            "escalation_reason": first_escalation_reason,
            "final_response": first_escalation_msg or "",
        }

    return {
        **base_return,
        "next_node": "generate_response",
    }


_RAG_INTENTS = {"refund_request", "warranty_claim", "product_inquiry", "general_inquiry"}
_LLM_INTENTS = {"refund_request", "warranty_claim", "order_status", "delivery_tracking",
                "product_inquiry", "general_inquiry"}


async def _retrieve_context_for_intents(
    query: str,
    detected_intents: List[str],
    timings: Dict[str, float],
) -> str:
    """Run RAG in parallel for every detected intent that requires knowledge context.

    Deduplicates by content to avoid repeating the same policy text when two
    intents resolve to overlapping Qdrant results (e.g. refund + warranty both
    hit the same policy section).  Each retrieval is logged individually.
    """
    rag_intents = [i for i in detected_intents if i in _RAG_INTENTS]
    if not rag_intents:
        return ""

    async def _fetch(intent: str) -> Tuple[str, Optional[Dict]]:
        rag_start = time.perf_counter()
        result = await retrieve_knowledge(query, intent=intent)
        rag_ms = (time.perf_counter() - rag_start) * 1000
        timings[f"rag:{intent}"] = round(rag_ms, 1)
        logger.info("generate_response.rag_retrieved",
                    intent=intent, context_length=len(result.get("content", "")) if result else 0,
                    scores=result.get("scores", []) if result else [], elapsed_ms=round(rag_ms, 1))
        return intent, result

    fetch_results = await asyncio.gather(*[_fetch(i) for i in rag_intents])

    # Merge and deduplicate by content fingerprint
    seen: set = set()
    parts: List[str] = []
    for intent, knowledge in fetch_results:
        if not knowledge:
            continue
        content = knowledge.get("content", "")
        fp = hash(content[:200])
        if fp not in seen:
            seen.add(fp)
            parts.append(content)

    return "\n\n---\n\n".join(parts)


def _apply_grounding_check(response: str, tool_results: Dict[str, Any], intent: str) -> str:
    """Lightweight grounding check: ensure the response doesn't contain hallucinated
    order IDs, amounts, or statuses that contradict the tool results.

    Strategy: if the response contains a dollar sign or an unsupported currency,
    strip it. If the response mentions an order status that doesn't match the tool
    result, append a clarifying correction.

    Returns the (potentially corrected) response string.
    """
    if not response:
        return response

    # 1. Currency guard — remove any $ signs that slipped through
    if "$" in response:
        response = response.replace("$", "AED ")
        logger.warning("grounding_check.currency_hallucination_corrected")

    # 2. For order_status: verify status mentioned in response matches DB result
    if intent == "order_status":
        order = (tool_results.get("check_order") or {}).get("order") or {}
        actual_status = order.get("status", "").lower()
        if actual_status and actual_status not in response.lower():
            # Don't alter — LLM may have rephrased the status; only log mismatch
            logger.info("grounding_check.status_mismatch",
                        actual=actual_status, response_snippet=response[:100])

    return response


@trace_node("generate_response")
async def generate_response_node(state: ConversationState) -> Dict[str, Any]:
    """Generate final response for single or multi-intent queries.

    Multi-intent path:
      - RAG retrieval runs in parallel for every RAG-eligible detected intent.
      - Merged context (deduplicated) and all tool results are passed to the LLM.
      - The LLM system prompt includes guidance for EACH detected intent so the
        response addresses every question the customer asked.

    Streaming:
      - If a token_queue is registered for this conversation, tokens are pushed
        as they arrive.  A None sentinel signals end-of-stream.
    """
    start = time.perf_counter()
    primary_intent = state["primary_intent"]
    detected_intents: List[str] = state.get("detected_intents") or [primary_intent]
    tool_results = state["tool_results"]
    extracted_params = state["extracted_params"]
    conversation_id = state.get("conversation_id", "")
    timings: Dict[str, float] = dict(state.get("timings_ms", {}))
    is_multi_intent = len(detected_intents) > 1

    logger.info("generate_response.start",
                primary_intent=primary_intent,
                detected_intents=detected_intents,
                is_multi_intent=is_multi_intent,
                tool_results=list(tool_results.keys()))

    query = state["raw_query"]

    # system_prompt_override may arrive via payload → extracted_params
    system_prompt_override: Optional[str] = state.get("extracted_params", {}).get("system_prompt_override")

    # --- RAG: parallel retrieval for all intents that need knowledge context ---
    context = await _retrieve_context_for_intents(query, detected_intents, timings)
    if context:
        logger.info("generate_response.context_merged", context_length=len(context),
                    rag_intents=[i for i in detected_intents if i in _RAG_INTENTS])

    conversation_text = "\n".join(
        [f"{msg.get('role', 'user')}: {msg.get('content', '')}"
         for msg in state.get("messages", [])]
    )

    token_queue = _token_queues.get(conversation_id)

    # For multi-intent, use primary but pass all detected intents into the LLM.
    effective_intent = primary_intent

    response = ""
    response_source = "fallback"
    llm_ms: Optional[float] = None

    # --- Always use non-streaming LLM path ---
    # Progress messages were already sent during tool execution.
    # After the LLM call we do a lightweight grounding check, then push
    # the verified response to the token_queue in one shot.
    result = await generate_response(
        effective_intent, tool_results, extracted_params,
        conversation_text, context, detected_intents=detected_intents,
        system_override=system_prompt_override,
    )
    if isinstance(result, dict):
        response = result.get("text", "")
        response_source = result.get("source", "fallback")
        llm_ms = result.get("llm_ms")
    else:
        response = str(result)

    # --- Grounding check ---
    # Verify the response doesn't hallucinate key facts from tool results.
    response = _apply_grounding_check(response, tool_results, primary_intent)

    # Push verified response to queue (single push, not streamed per-token)
    if token_queue is not None:
        if response:
            await token_queue.put(response)
        await token_queue.put(None)

    if llm_ms is not None:
        timings["llm_generation"] = llm_ms

    logger.info("generate_response.complete",
                primary_intent=primary_intent,
                detected_intents=detected_intents,
                response_length=len(response),
                response_snippet=response[:80])

    # Async faithfulness evaluation — fires in background, zero latency impact
    if context and response:
        schedule_faithfulness_eval(
            question=query,
            context=context,
            answer=response,
            intent=primary_intent,
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    timings["generate_response_total"] = elapsed_ms

    return {
        "final_response": response,
        "next_node": "persist_response",
        "response_source": response_source,
        "timings_ms": timings,
    }


@trace_node("persist_response")
async def persist_response_node(state: ConversationState) -> Dict[str, Any]:
    """Persist final response to DB and cache query/response in Redis."""
    start = time.perf_counter()
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
        primary_intent=state.get("primary_intent") or None,
        intent_confidence=state.get("intent_confidence") or None,
        messages=messages,
        query_analysis=query_analysis,
        tool_results=tool_results,
    )
    if stored_db:
        logger.info("persist_response.db_complete", conversation_id=conversation_id, turn_index=turn_index)

    primary_intent = state.get("primary_intent") or "unknown"
    param_status = state.get("param_validation_status", "")
    is_waiting_for_params = (param_status == "INCOMPLETE")

    if is_waiting_for_params:
        # Not a resolution yet — don't record FCR or turns-to-resolve
        resolution_type = "waiting_for_params"
        record_conversation_resolution(resolution_type)
    else:
        resolution_type = "escalated" if state.get("escalation_required") else "resolved"
        is_fcr = (turn_index == 1)
        # Single call records: resolution_total, intent_resolution_total, turns_to_resolve, FCR
        record_conversation_outcome(
            intent=primary_intent,
            resolution_type=resolution_type,
            turn_index=max(turn_index, 1),
            is_first_contact=is_fcr,
        )

    # End-to-end response latency — use generate_response_total when available (LLM path),
    # fall back to summing all timing buckets (cache / param-request paths).
    timings = state.get("timings_ms", {})
    e2e_ms = timings.get("generate_response_total") or timings.get("execute_tools_total")
    if not e2e_ms:
        e2e_ms = sum(v for v in timings.values() if isinstance(v, (int, float)) and v > 0) or None
    if e2e_ms:
        record_response_latency(e2e_ms)

    # Cost per conversation — proxy: LLM latency scaled to USD; minimum $0.001 for non-LLM paths
    llm_ms = timings.get("llm_generation") or timings.get("generate_response_total") or 0.0
    cost_usd = max(0.001, llm_ms * 0.000005)
    record_cost_per_conversation(cost_usd)

    # Per-intent RAG latency recorded from individual rag:<intent> keys in timings
    # Use only real intents (not "unknown" fallback) for metric labels
    detected_intents: List[str] = [
        i for i in (state.get("detected_intents") or [])
        if i and i != "unknown"
    ]
    for intent in detected_intents:
        rag_key = f"rag:{intent}"
        if rag_key in timings:
            record_rag_latency(intent, timings[rag_key])

    # Multi-intent detection rate
    if len(detected_intents) > 1:
        record_multi_intent(len(detected_intents))

    logger.info("persist_response.metrics_recorded",
                resolution_type=resolution_type,
                turn_index=turn_index,
                detected_intents=detected_intents if detected_intents else ["(none)"])

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
            # Only cache successful tool lookups.  If every tool call failed
            # (e.g. order-not-found), skip writing to the query-hash bucket so
            # a corrected retry doesn't get the wrong cached response.
            cache_key = query_analysis.get("cache_key")
            tool_results = state.get("tool_results", {})
            any_tool_success = any(
                v.get("success", True) is not False
                for v in tool_results.values()
                if isinstance(v, dict)
            )
            should_cache = cache_key and (not tool_results or any_tool_success)
            if should_cache:
                if ttl_s > 0:
                    redis_client.setex(cache_key, ttl_s, json.dumps(payload, ensure_ascii=False))
                else:
                    redis_client.set(cache_key, json.dumps(payload, ensure_ascii=False))
                logger.info("persist_response.redis_cache_complete", key=cache_key)
            elif cache_key:
                logger.info("persist_response.redis_cache_skipped", key=cache_key, reason="all_tools_failed")
        except Exception as exc:
            logger.warning("persist_response.redis_failed", error=str(exc))

    elapsed_ms = (time.perf_counter() - start) * 1000
    return {"next_node": "end", "timings_ms": {**state.get("timings_ms", {}), "persist_response": elapsed_ms}}


@trace_node("serve_cache")
async def serve_cache_node(state: ConversationState) -> Dict[str, Any]:
    """Serve response from Redis cache if available.

    Must signal the SSE token queue so the streaming client receives the
    cached answer immediately instead of waiting 30 s for a timeout.
    """
    cached = state.get("cache_payload") or {}
    response = cached.get("final_response", "") or "Cached response not available."
    conversation_id = state.get("conversation_id", "")
    await _flush_queue_with_response(conversation_id, response)
    logger.info("serve_cache.queue_flushed", conversation_id=conversation_id,
                response_length=len(response))
    return {
        "final_response": response,
        "response_source": "redis",
        "next_node": "persist_response",
    }


async def generate_response(
    intent: str,
    tool_results: Dict,
    params: Dict,
    conversation: str,
    context: str,
    detected_intents: Optional[List[str]] = None,
    system_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate response based on intent and tool results.

    detected_intents: when set (multi-intent queries), the LLM is asked to
    address every intent in a single cohesive response.
    system_override: when set, replaces the default system prompt for A/B prompt testing.
    """
    llm_ms = None
    source = "fallback"

    # Check for escalation needed
    for _tn, result in tool_results.items():
        if not result.get("success", True) and "escalate" in str(result.get("error", "")).lower():
            return {"text": "I'm having trouble processing your request. Let me connect you with a human agent.", "source": "escalation_trigger"}

    llm_intents = {"refund_request", "warranty_claim", "order_status", "delivery_tracking",
                   "product_inquiry", "general_inquiry"}
    if intent in llm_intents:
        tier = "SPEED" if intent in {"order_status", "delivery_tracking"} else "BALANCED"

        # Use tool results to construct final answer
        llm_payload = llm_generate_response(
            intent, conversation, tool_results, params,
            context=context, speed_tier=tier, return_meta=True,
            detected_intents=detected_intents,
            system_override=system_override,
        )
        llm_response = llm_payload.get("response")
        llm_ms = llm_payload.get("elapsed_ms")
        if llm_response:
            return {"text": llm_response, "source": "llm", "llm_ms": llm_ms}

    if intent == "refund_request":
        refund_result = tool_results.get("initiate_refund", {})
        if refund_result.get("success"):
            return {"text": f"Your refund has been processed! Refund ID: {refund_result.get('refund_id')}. The amount will be credited to your account within 5-7 business days.", "source": source}

    elif intent == "order_status":
        order_result = tool_results.get("check_order", {})
        if order_result.get("success"):
            order = order_result.get("order", {})
            logger.info("generate_response.order_status", order_id=order.get("order_id"), status=order.get("status"))
            return {"text": f"Your order {order.get('order_id')} is currently: {order.get('status', 'Unknown')}. Total: {order.get('total_aed', 'N/A')} AED", "source": source}
        if order_result.get("error") == "ORDER_NOT_FOUND" or "not found" in str(order_result.get("message", "")).lower():
            return {"text": "Order not found. Please verify the order ID and try again.", "source": source}

    elif intent == "delivery_tracking":
        tracking_result = tool_results.get("track_delivery", {})
        if tracking_result.get("success"):
            tracking = tracking_result.get("tracking", {})
            return {"text": f"Current status: {tracking.get('status', 'Unknown')}. Location: {tracking.get('current_location', 'N/A')}. Carrier: {tracking.get('carrier', 'N/A')}", "source": source}

    elif intent == "warranty_claim":
        claim_result = tool_results.get("initiate_claim", {})
        if claim_result.get("success"):
            return {"text": f"Your warranty claim has been initiated! Claim ID: {claim_result.get('claim_id')}. " + " ".join(claim_result.get("next_steps", [])), "source": source}

    elif intent == "speak_to_human":
        return {"text": "I'll connect you with a customer support agent. Please hold on for a moment.", "source": source}
    elif intent == "end_conversation":
        return {"text": "Thanks for contacting us. If you need anything else, just let me know!", "source": "rule"}

    # Generic response
    return {"text": "I've processed your request. Is there anything else I can help you with?", "source": source}


@trace_node("handle_unsupported")
async def handle_unsupported_node(state: ConversationState) -> Dict[str, Any]:
    """Handle unsupported intents.

    In-domain-but-out-of-scope intents escalate to a human agent (generate_response_node
    will handle queue signaling on the escalate path).  Truly unsupported intents
    return a polite decline and flush the queue directly.
    """
    support_status = state.get("intent_support_status", "")
    conversation_id = state.get("conversation_id", "")

    if support_status == SUPPORT_STATUS["IN_DOMAIN_OUT_OF_SCOPE"]:
        # Escalate path goes through generate_response_node — queue handled there
        return {
            "final_response": "I understand your request, but this is outside my current capabilities. Let me connect you with a human agent who can help.",
            "next_node": "escalate",
            "escalation_required": True,
            "escalation_reason": "in_domain_out_of_scope",
        }
    else:
        response = "I'm not able to help with that particular request. Could you try a different question?"
        await _flush_queue_with_response(conversation_id, response)
        return {
            "final_response": response,
            "next_node": "persist_response",
        }


def _build_escalation_packet(state: ConversationState) -> Dict[str, Any]:
    """Assemble the full context packet for the human agent."""
    tool_results = state.get("tool_results") or {}
    emotion = state.get("emotion") or {}
    customer_history = state.get("customer_history") or {}
    reason = state.get("escalation_reason") or "unknown"

    order_data = (tool_results.get("check_order") or {}).get("order") or {}
    delivery_data = (tool_results.get("track_delivery") or {}).get("tracking") or {}

    # Bot assessment
    signals = []
    if emotion.get("delivery_dispute"):
        signals.append("delivery marked delivered — customer denies receipt")
    if emotion.get("repeat_complaint") or customer_history.get("is_repeat_delivery_issue"):
        signals.append("repeat delivery failure")
    if emotion.get("churn_signal"):
        signals.append("high churn risk — customer threatening to leave")
    if emotion.get("high_value_item_mentioned"):
        signals.append(f"high-value item: {emotion['high_value_item_mentioned']}")

    assessment = "; ".join(signals) if signals else reason
    recommended_action = customer_history.get("recommended_action") or "standard_refund"

    return {
        "escalation_reason": reason,
        "order": order_data,
        "delivery": delivery_data,
        "customer_history": customer_history,
        "emotion": emotion,
        "bot_assessment": assessment,
        "recommended_action": recommended_action,
        "raw_query": state.get("raw_query", ""),
        "conversation_summary": [
            {"role": m.get("role"), "content": m.get("content", "")[:200]}
            for m in (state.get("messages") or [])[-6:]
        ],
    }


async def _generate_escalation_response(state: ConversationState, packet: Dict[str, Any]) -> str:
    """Generate a personalized, empathetic escalation message using LLM.

    Falls back to a template string if LLM is unavailable.
    """
    order = packet.get("order") or {}
    delivery = packet.get("delivery") or {}
    emotion = packet.get("emotion") or {}
    history = packet.get("customer_history") or {}

    order_id = order.get("order_id") or state.get("extracted_params", {}).get("order_id") or "your order"
    delivered_at = delivery.get("delivered_at") or ""
    item_name = emotion.get("high_value_item_mentioned") or ""
    is_repeat = history.get("is_repeat_delivery_issue") or emotion.get("repeat_complaint")
    recommended = packet.get("recommended_action", "")

    # Build LLM prompt for personalized escalation message
    context_lines = [f"Order ID: {order_id}" if order_id != "your order" else ""]
    if delivered_at:
        context_lines.append(f"Delivery timestamp: {delivered_at}")
    if item_name:
        context_lines.append(f"Item: {item_name}")
    if is_repeat:
        context_lines.append("This customer had a prior delivery issue.")
    if "goodwill" in recommended:
        context_lines.append("Recommended action: full refund + goodwill credit")
    elif "refund" in recommended:
        context_lines.append("Recommended action: full refund + priority investigation")

    context = "\n".join(l for l in context_lines if l)

    prompt = (
        "You are a customer support assistant for Noon e-commerce. "
        "Write a short, empathetic escalation message to the customer. "
        "Acknowledge their issue specifically, show what you found, "
        "tell them a specialist will contact them within 15 minutes, "
        "and assure them they won't need to repeat anything. "
        "Keep it under 4 sentences. Use AED not $. "
        f"Context:\n{context}\nCustomer message: {state.get('raw_query', '')}"
    )

    try:
        client = LLMConnectorClient("SPEED")
        result = client.generate(prompt, max_tokens=200)
        if result.get("success"):
            return result.get("response", "").strip()
    except Exception as exc:
        logger.warning("escalate.llm_failed", error=str(exc))

    # Template fallback
    lines = ["I'm sorry about this — "]
    if order_id != "your order":
        lines.append(f"I can see {item_name + ' (' if item_name else ''}Order #{order_id}{')' if item_name else ''}")
        if delivered_at:
            lines.append(f" was marked as delivered on {delivered_at}")
        lines.append(". ")
    if is_repeat:
        lines.append("I also see this isn't the first time you've had a delivery issue with us, and I completely understand your frustration. ")
    lines.append(
        "I've flagged this as urgent with our support team — a specialist will reach out within 15 minutes "
        "with the full context. You won't need to repeat anything."
    )
    return "".join(lines)


@trace_node("escalate")
async def escalate_node(state: ConversationState) -> Dict[str, Any]:
    """Escalate to human agent with rich context packet and personalized response."""
    reason = state.get("escalation_reason") or "unknown"
    logger.info("escalate.start", reason=reason)
    record_escalation_reason(reason)

    # Build the escalation packet
    packet = _build_escalation_packet(state)

    # Generate personalized response for the customer
    response = await _generate_escalation_response(state, packet)

    # Push response to streaming queue if registered
    conversation_id = state.get("conversation_id", "")
    token_queue = _token_queues.get(conversation_id)
    if token_queue is not None:
        await token_queue.put(response)
        await token_queue.put(None)

    # Call escalate_to_human tool to create the ticket
    tool = get_tool("escalate_to_human")
    ticket_result: Dict[str, Any] = {}
    if tool:
        try:
            ticket_result = await tool.execute({
                "user_id": state.get("user_id", ""),
                "reason": reason,
                "conversation_summary": str(packet.get("conversation_summary", [])),
            }, state)
        except Exception as exc:
            logger.error("escalate.ticket_error", error=str(exc))

    ticket_id = ticket_result.get("ticket_id") or ticket_result.get("escalation_id", "")
    logger.info("escalate.complete", reason=reason, ticket_id=ticket_id,
                churn_risk=(packet.get("customer_history") or {}).get("churn_risk", "unknown"))

    return {
        "final_response": response,
        "escalation_packet": packet,
        "tool_results": {**state.get("tool_results", {}), "escalate_to_human": ticket_result},
        "tools_executed": (state.get("tools_executed") or []) + ["escalate_to_human"],
        "next_node": "end",
    }


# Node mapping
NODES = {
    "guard_input": guard_input_node,
    "serve_cache": serve_cache_node,
    "query_analyser": query_analyser_node,
    "intent_analyser": intent_analyser_node,
    "complexity_analyser": complexity_analyser_node,
    "query_analyse_join": query_analyse_join_node,
    "complex_query_orchestrator": complex_query_orchestrator_node,
    "complex_intent_agent": complex_intent_agent_node,
    "complex_refine_agent": complex_refine_agent_node,
    "complex_query_join": complex_query_join_node,
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
