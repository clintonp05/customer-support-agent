"""Prometheus metrics exporter.

Dashboard-ready metric set covering:
  - Intent classification quality
  - Tool execution (latency, success rate, circuit breaker)
  - Conversation outcomes (resolution, escalation, FCR, turns to resolve)
  - Latency SLAs (end-to-end response, RAG retrieval)
  - Cost per conversation (USD + token counts)
  - Multi-intent detection rate
  - Evaluation accuracy (faithfulness, goal success, hallucination)
"""
from prometheus_client import Counter, Histogram, Gauge

# ---------------------------------------------------------------------------
# Intent metrics
# ---------------------------------------------------------------------------
intent_classifications_total = Counter(
    "intent_classifications_total",
    "Total intent classifications",
    ["intent", "status"],         # status: classified / fallback
)

multi_intent_detection_total = Counter(
    "multi_intent_detection_total",
    "Queries where multiple intents were detected",
    ["intent_count"],             # "2", "3", "4+"
)

# ---------------------------------------------------------------------------
# Tool metrics
# ---------------------------------------------------------------------------
tool_calls_total = Counter(
    "tool_calls_total",
    "Total tool calls",
    ["tool_name", "status"],      # status: success / failure / circuit_open / error
)
tool_latency_ms = Histogram(
    "tool_latency_ms",
    "Tool call latency in milliseconds",
    ["tool_name"],
    buckets=[50, 100, 250, 500, 1000, 2000, 5000],
)
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open)",
    ["tool_name"],
)

# ---------------------------------------------------------------------------
# Conversation outcome metrics
# ---------------------------------------------------------------------------
conversation_resolution_total = Counter(
    "conversation_resolution_total",
    "Conversation resolutions by type",
    ["resolution_type"],          # resolved / escalated / abandoned
)
escalation_reason_total = Counter(
    "escalation_reason_total",
    "Escalation reason breakdown",
    ["reason"],                   # api_failure / policy / complexity / fraud_flag / refund_ineligible / circuit_breaker_open
)

# First Contact Resolution — did the conversation resolve in a single turn?
first_contact_resolution_total = Counter(
    "first_contact_resolution_total",
    "Conversations resolved on the first customer turn",
    ["resolved"],                 # "true" / "false"
)

# Turns needed to reach resolution — powers 'average turns to resolve' dashboard panel
turns_to_resolve_histogram = Histogram(
    "turns_to_resolve",
    "Number of conversation turns at resolution time",
    buckets=[1, 2, 3, 4, 5, 6, 8, 10, 15],
)

# Per-intent resolution outcomes — enables intent-level success rate
intent_resolution_total = Counter(
    "intent_resolution_total",
    "Resolution outcome broken down by intent",
    ["intent", "resolution_type"],  # intent × resolved|escalated|abandoned
)

# ---------------------------------------------------------------------------
# Latency SLA metrics
# ---------------------------------------------------------------------------
response_latency_ms = Histogram(
    "response_latency_ms",
    "End-to-end response latency per conversation turn (wall clock)",
    buckets=[200, 500, 1000, 2000, 3000, 5000, 8000, 15000],
)

rag_retrieval_latency_ms = Histogram(
    "rag_retrieval_latency_ms",
    "RAG knowledge retrieval latency in milliseconds",
    ["intent"],
    buckets=[50, 100, 200, 500, 1000, 2000],
)

# ---------------------------------------------------------------------------
# Cost metrics
# ---------------------------------------------------------------------------
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "type"],            # type: input / output
)
cost_per_conversation = Histogram(
    "cost_per_conversation_usd",
    "Cost per conversation in USD",
    buckets=[0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.00],
)

# ---------------------------------------------------------------------------
# Evaluation / quality metrics
# ---------------------------------------------------------------------------
eval_accuracy = Gauge(
    "eval_accuracy",
    "Latest offline evaluation accuracy",
    ["metric_name"],              # tool_selection / param / goal_success / hallucination / faithfulness
)

faithfulness_score = Histogram(
    "rag_faithfulness_score",
    "RAG faithfulness score (0-1) from LLM judge: is the answer grounded in context?",
    ["intent"],
    buckets=[0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 1.0],
)


# ---------------------------------------------------------------------------
# Recording helpers
# ---------------------------------------------------------------------------

def record_intent_classification(intent: str, status: str) -> None:
    intent_classifications_total.labels(intent=intent, status=status).inc()


def record_multi_intent(detected_count: int) -> None:
    bucket = str(detected_count) if detected_count <= 3 else "4+"
    multi_intent_detection_total.labels(intent_count=bucket).inc()


def record_tool_call(tool_name: str, status: str, latency_ms: float) -> None:
    tool_calls_total.labels(tool_name=tool_name, status=status).inc()
    tool_latency_ms.labels(tool_name=tool_name).observe(latency_ms)


def record_circuit_breaker_state(tool_name: str, is_open: bool) -> None:
    circuit_breaker_state.labels(tool_name=tool_name).set(1 if is_open else 0)


def record_conversation_resolution(resolution_type: str) -> None:
    conversation_resolution_total.labels(resolution_type=resolution_type).inc()


def record_escalation_reason(reason: str) -> None:
    escalation_reason_total.labels(reason=reason).inc()


def record_conversation_outcome(
    intent: str,
    resolution_type: str,
    turn_index: int,
    is_first_contact: bool,
) -> None:
    """Single call to record all outcome metrics at conversation resolution time.

    Args:
        intent:           The primary intent that was resolved.
        resolution_type:  "resolved" | "escalated" | "abandoned"
        turn_index:       1-based turn number when resolution occurred.
        is_first_contact: True if turn_index == 1 (single-turn resolution).
    """
    record_conversation_resolution(resolution_type)
    intent_resolution_total.labels(intent=intent, resolution_type=resolution_type).inc()
    turns_to_resolve_histogram.observe(turn_index)
    first_contact_resolution_total.labels(resolved=str(is_first_contact).lower()).inc()


def record_response_latency(latency_ms: float) -> None:
    response_latency_ms.observe(latency_ms)


def record_rag_latency(intent: str, latency_ms: float) -> None:
    rag_retrieval_latency_ms.labels(intent=intent).observe(latency_ms)


def record_llm_tokens(model: str, token_type: str, count: int) -> None:
    llm_tokens_total.labels(model=model, type=token_type).inc(count)


def record_cost_per_conversation(cost_usd: float) -> None:
    cost_per_conversation.observe(cost_usd)


def record_faithfulness(intent: str, score: float) -> None:
    """Record a faithfulness score (0–1) from the async LLM judge."""
    faithfulness_score.labels(intent=intent).observe(score)


def update_eval_accuracy(metric_name: str, value: float) -> None:
    eval_accuracy.labels(metric_name=metric_name).set(value)
