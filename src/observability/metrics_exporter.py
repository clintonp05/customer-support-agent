"""Prometheus metrics exporter"""
from prometheus_client import Counter, Histogram, Gauge

# Intent metrics
intent_classifications_total = Counter(
    "intent_classifications_total",
    "Total intent classifications",
    ["intent", "status"]
)

# Tool metrics
tool_calls_total = Counter(
    "tool_calls_total",
    "Total tool calls",
    ["tool_name", "status"]
)
tool_latency_ms = Histogram(
    "tool_latency_ms",
    "Tool call latency",
    ["tool_name"],
    buckets=[50, 100, 250, 500, 1000, 2000, 5000]
)
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open)",
    ["tool_name"]
)

# Conversation metrics
conversation_resolution_total = Counter(
    "conversation_resolution_total",
    "Conversation resolutions",
    ["resolution_type"]  # resolved / escalated / abandoned
)
escalation_reason_total = Counter(
    "escalation_reason_total",
    "Escalation reasons",
    ["reason"]  # api_failure / policy / complexity / fraud_flag
)

# Cost metrics
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens",
    ["model", "type"]  # input / output
)
cost_per_conversation = Histogram(
    "cost_per_conversation_usd",
    "Cost per conversation in USD",
    buckets=[0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.00]
)

# Eval metrics
eval_accuracy = Gauge(
    "eval_accuracy",
    "Latest eval accuracy",
    ["metric_name"]  # tool_selection / param / goal_success / hallucination
)


def record_intent_classification(intent: str, status: str):
    """Record an intent classification"""
    intent_classifications_total.labels(intent=intent, status=status).inc()


def record_tool_call(tool_name: str, status: str, latency_ms: float):
    """Record a tool call"""
    tool_calls_total.labels(tool_name=tool_name, status=status).inc()
    tool_latency_ms.labels(tool_name=tool_name).observe(latency_ms)


def record_circuit_breaker_state(tool_name: str, is_open: bool):
    """Record circuit breaker state"""
    circuit_breaker_state.labels(tool_name=tool_name).set(1 if is_open else 0)


def record_conversation_resolution(resolution_type: str):
    """Record conversation resolution"""
    conversation_resolution_total.labels(resolution_type=resolution_type).inc()


def record_escalation_reason(reason: str):
    """Record escalation reason"""
    escalation_reason_total.labels(reason=reason).inc()


def record_llm_tokens(model: str, token_type: str, count: int):
    """Record LLM token usage"""
    llm_tokens_total.labels(model=model, type=token_type).inc(count)


def record_cost_per_conversation(cost_usd: float):
    """Record cost per conversation"""
    cost_per_conversation.observe(cost_usd)


def update_eval_accuracy(metric_name: str, value: float):
    """Update eval accuracy gauge"""
    eval_accuracy.labels(metric_name=metric_name).set(value)