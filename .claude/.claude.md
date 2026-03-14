# CLAUDE.md — Noon Conversational AI Agent
## Boilerplate Build Instructions for Claude Code

---

## Project Overview

Build a **production-ready conversational AI agent** for e-commerce customer support.
Modeled after the Noon architecture. Runs fully locally with Docker Compose.
Deployable to AWS with minimal changes.

Stack: Python · LangGraph · FastAPI · Langfuse · Redis · Postgres · Qdrant · Grafana

---

## Project Structure to Generate

```
noon-agent/
├── CLAUDE.md                        ← this file
├── docker-compose.yml               ← full local infrastructure
├── docker-compose.aws.yml           ← AWS overrides
├── .env.example                     ← all required env vars
├── Makefile                         ← dev commands
│
├── src/
│   ├── main.py                      ← FastAPI app entrypoint
│   ├── config.py                    ← settings via pydantic-settings
│   │
│   ├── guard/
│   │   ├── __init__.py
│   │   ├── toxicity.py              ← Llama Guard or HF toxicity model
│   │   ├── pii.py                   ← presidio PII detection + masking
│   │   ├── language.py              ← language detection (Arabic/English)
│   │   └── entity_extractor.py     ← NER: order IDs, product names
│   │
│   ├── intent/
│   │   ├── __init__.py
│   │   ├── registry.py              ← INTENT_REGISTRY dict with tool manifest
│   │   ├── vector_index.py          ← Redis Vector KNN search (1500 intents max)
│   │   ├── classifier.py            ← SetFit + zero-shot BART fallback
│   │   ├── multi_intent.py          ← sentence chunking + multi-intent DAG
│   │   └── supported_check.py      ← supported vs unsupported routing
│   │
│   ├── params/
│   │   ├── __init__.py
│   │   ├── extractor.py             ← LLM param extraction from conversation
│   │   ├── validator.py             ← Pydantic schema validation per tool
│   │   └── swap_detector.py        ← orderId ↔ userId swap detection
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py                 ← LangGraph StateGraph definition
│   │   ├── state.py                 ← ConversationState TypedDict
│   │   ├── nodes.py                 ← all LangGraph node functions
│   │   └── edges.py                 ← conditional edge routing logic
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── manifest.py              ← TOOL_MANIFEST: intent → tool mapping
│   │   ├── order_tool.py            ← order API integration (mock + real)
│   │   ├── refund_tool.py           ← refund API with idempotency keys
│   │   ├── delivery_tool.py         ← delivery tracking tool
│   │   ├── warranty_tool.py         ← warranty claim tool
│   │   ├── escalation_tool.py      ← human handoff with full context
│   │   └── base.py                  ← BaseTool with retry + circuit breaker
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── working.py               ← LangGraph checkpointer (Postgres)
│   │   ├── episodic.py              ← episode store: write + retrieve
│   │   └── summarizer.py           ← conversation summarization for storage
│   │
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── pipeline.py              ← RAG retrieval pipeline
│   │   ├── embedder.py              ← multilingual sentence-transformers
│   │   └── retriever.py             ← Qdrant semantic search
│   │
│   ├── prompts/
│   │   ├── hub.py                   ← PromptHubClient (Langfuse + cache)
│   │   ├── agents/
│   │   │   ├── customer_support_agent.txt
│   │   │   ├── refund_agent.txt
│   │   │   └── warranty_agent.txt
│   │   ├── classifiers/
│   │   │   └── intent_classifier.txt
│   │   └── guards/
│   │       └── output_safety.txt
│   │
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── pipeline.py              ← eval runner: golden set → metrics
│   │   ├── judges.py                ← LLM-as-judge evaluators
│   │   ├── metrics.py               ← all metric calculations
│   │   └── golden_sets/
│   │       ├── refund.json          ← golden test cases
│   │       ├── order_status.json
│   │       ├── delivery.json
│   │       └── adversarial.json     ← param swap + edge cases
│   │
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── tracer.py                ← Langfuse trace wrapper
│   │   ├── metrics_exporter.py     ← Prometheus metrics
│   │   └── cost_tracker.py         ← cost per token → cost per ticket
│   │
│   └── api/
│       ├── __init__.py
│       ├── chat.py                  ← POST /chat endpoint
│       ├── eval.py                  ← POST /eval/run endpoint
│       ├── metrics.py               ← GET /metrics (Prometheus)
│       └── health.py                ← GET /health
│
├── tests/
│   ├── unit/
│   │   ├── test_intent_classifier.py
│   │   ├── test_param_validator.py
│   │   ├── test_swap_detector.py
│   │   └── test_tool_manifest.py
│   ├── integration/
│   │   ├── test_full_conversation.py
│   │   └── test_tool_execution.py
│   └── eval/
│       └── test_golden_sets.py      ← CI gate: runs eval, fails if below threshold
│
├── infra/
│   ├── grafana/
│   │   ├── dashboards/
│   │   │   └── noon_agent.json      ← pre-built Grafana dashboard
│   │   └── datasources/
│   │       └── prometheus.yml
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── langfuse/
│       └── init.sql                 ← Langfuse DB init
│
└── scripts/
    ├── seed_intent_index.py         ← loads intents into Redis Vector
    ├── seed_golden_set.py           ← creates initial golden dataset
    ├── run_eval.py                  ← standalone eval runner
    └── deploy_aws.sh                ← AWS deployment script
```

---

## docker-compose.yml — Generate This Exactly

Services to include:

```yaml
services:

  # The agent API
  agent:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis, qdrant, langfuse]

  # Postgres — LangGraph checkpointer + episode store + Langfuse
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: noon_agent
      POSTGRES_USER: noon
      POSTGRES_PASSWORD: noon_local
    ports: ["5432:5432"]
    volumes: ["postgres_data:/var/lib/postgresql/data"]

  # Redis — intent vector index + session cache + prompt cache
  redis:
    image: redis/redis-stack:latest   # includes RedisSearch for vectors
    ports: ["6379:6379", "8001:8001"] # 8001 = RedisInsight UI
    volumes: ["redis_data:/data"]

  # Qdrant — RAG knowledge base (FAQ, policies, support history)
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes: ["qdrant_data:/qdrant/storage"]

  # Langfuse — observability + prompt hub (self-hosted)
  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3000:3000"]
    environment:
      DATABASE_URL: postgresql://noon:noon_local@postgres:5432/langfuse
      NEXTAUTH_SECRET: local_secret_change_in_prod
      NEXTAUTH_URL: http://localhost:3000
      SALT: local_salt
    depends_on: [postgres]

  # Prometheus — metrics collection
  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes:
      - ./infra/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml

  # Grafana — metrics dashboard
  grafana:
    image: grafana/grafana:latest
    ports: ["3001:3000"]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - ./infra/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./infra/grafana/datasources:/etc/grafana/provisioning/datasources
      - grafana_data:/var/lib/grafana
    depends_on: [prometheus]

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  grafana_data:
```

---

## Key Implementation Requirements

### 1. LangGraph State — src/agent/state.py

```python
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
    detected_intents: List[str]          # multi-intent list
    primary_intent: str
    intent_confidence: float
    intent_support_status: str           # SUPPORTED / IN_DOMAIN_OUT_OF_SCOPE / UNSUPPORTED
    
    # Params
    extracted_params: Dict[str, Any]
    param_validation_status: str         # COMPLETE / INCOMPLETE / SWAP_DETECTED
    missing_params: List[str]
    
    # Execution
    tools_executed: List[str]
    tool_results: Dict[str, Any]
    execution_budget_ms: int
    budget_spent_ms: int
    
    # Memory
    episodic_context: Optional[Dict]     # injected at session start
    
    # Control flow
    next_node: str                        # LangGraph routing
    escalation_required: bool
    escalation_reason: Optional[str]
    
    # Response
    final_response: Optional[str]
    
    # Observability
    trace_id: str
    prompt_versions: Dict[str, str]      # prompt_name → version hash
```

### 2. Intent Registry — src/intent/registry.py

```python
INTENT_REGISTRY = {
    "refund_request": {
        "supported": True,
        "utterances": [
            "I want my money back",
            "please refund me",
            "charge is wrong",
            "I was overcharged",
            "أريد استرداد أموالي",
        ],
        "conditions": [
            "order_exists",
            "order_belongs_to_user",
            "order_age_days <= 30",
            "refund_not_already_processed"
        ],
        "required_params": ["order_id", "user_id"],
        "tool_chain": {
            "sequential": ["check_order", "check_refund_eligibility"],
            "conditional": {
                "eligible": "initiate_refund",
                "ineligible": "escalate_to_human"
            }
        },
        "fallback": "escalate_to_human"
    },
    "order_status": {
        "supported": True,
        "utterances": [
            "where is my order",
            "track my order",
            "order status",
            "أين طلبي",
        ],
        "conditions": ["order_exists", "order_belongs_to_user"],
        "required_params": ["order_id", "user_id"],
        "tool_chain": {
            "sequential": ["check_order"]
        },
        "fallback": "escalate_to_human"
    },
    # ... add all intents following same pattern
}
```

### 3. Tool Base — src/tools/base.py

```python
import time
import asyncio
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.observability.tracer import trace_tool_call

class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, recovery_s: int = 30):
        self.name = name
        self.failures = 0
        self.threshold = threshold
        self.recovery_s = recovery_s
        self.state = "CLOSED"
        self.last_failure = None

    def can_execute(self) -> bool:
        if self.state == "OPEN":
            if time.time() - self.last_failure > self.recovery_s:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.threshold:
            self.state = "OPEN"


class BaseTool(ABC):
    name: str
    circuit_breaker: CircuitBreaker

    @retry(
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2)
    )
    async def execute(self, params: dict, state: dict) -> dict:
        if not self.circuit_breaker.can_execute():
            raise CircuitOpenError(f"{self.name} circuit is OPEN")
        
        try:
            start = time.time()
            result = await self._call(params, state)
            elapsed = (time.time() - start) * 1000
            
            self.circuit_breaker.record_success()
            await trace_tool_call(self.name, params, result, elapsed)
            
            return self._validate_result(result)
        
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise

    @abstractmethod
    async def _call(self, params: dict, state: dict) -> dict:
        pass

    def _validate_result(self, result: dict) -> dict:
        """Override to add result-specific validation"""
        return result
```

### 4. Param Validator — src/params/validator.py

```python
import re
from pydantic import BaseModel, validator
from typing import Optional

# ID format signatures — MUST be distinct
ORDER_ID_PATTERN = r"^N-\d{8}-[A-Z0-9]{5}$"
USER_ID_PATTERN  = r"^USR-[A-Z0-9]{8}$"

class RefundToolParams(BaseModel):
    order_id: str
    user_id: str
    reason: Optional[str] = None

    @validator("order_id")
    def validate_order_id(cls, v):
        if not re.match(ORDER_ID_PATTERN, v):
            if re.match(USER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: order_id looks like user_id: {v}")
            raise ValueError(f"Invalid order_id format: {v}")
        return v

    @validator("user_id")
    def validate_user_id(cls, v):
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v

TOOL_PARAM_SCHEMAS = {
    "check_order":             RefundToolParams,
    "check_refund_eligibility": RefundToolParams,
    "initiate_refund":         RefundToolParams,
    # ... add all tools
}
```

### 5. Eval Pipeline — src/eval/pipeline.py

```python
import json
from pathlib import Path
from src.eval.judges import LLMJudge
from src.eval.metrics import EvalMetrics

GOLDEN_SET_DIR = Path("src/eval/golden_sets")

class EvalPipeline:
    def __init__(self, agent, judge: LLMJudge):
        self.agent = agent
        self.judge = judge

    async def run(self, golden_set_name: str) -> EvalMetrics:
        cases = json.loads((GOLDEN_SET_DIR / f"{golden_set_name}.json").read_text())
        results = []

        for case in cases:
            response = await self.agent.process(
                user_id=case["user_id"],
                message=case["input"]
            )
            scores = await self.judge.evaluate(
                input=case["input"],
                expected=case["expected_output"],
                actual=response.text,
                expected_tool=case.get("expected_tool"),
                actual_tool=response.tool_called,
                expected_params=case.get("expected_params"),
                actual_params=response.params_used
            )
            results.append(scores)

        return EvalMetrics.aggregate(results)


class EvalMetrics:
    def __init__(self, results):
        self.tool_selection_accuracy = sum(r.tool_correct for r in results) / len(results)
        self.param_accuracy = sum(r.params_correct for r in results) / len(results)
        self.goal_success_rate = sum(r.goal_achieved for r in results) / len(results)
        self.hallucination_rate = sum(r.hallucinated for r in results) / len(results)

    def passes_gates(self) -> bool:
        return (
            self.tool_selection_accuracy >= 0.90 and
            self.param_accuracy >= 0.95 and
            self.goal_success_rate >= 0.85 and
            self.hallucination_rate <= 0.02
        )

    @classmethod
    def aggregate(cls, results) -> "EvalMetrics":
        return cls(results)
```

### 6. Golden Set Format — src/eval/golden_sets/refund.json

```json
[
  {
    "id": "refund_001",
    "description": "Standard refund within 30 days",
    "user_id": "USR-TEST0001",
    "conversation": [
      {"role": "user", "content": "I want to return order N-20240312-AB123"}
    ],
    "expected_intent": "refund_request",
    "expected_tool": "check_order",
    "expected_params": {
      "order_id": "N-20240312-AB123",
      "user_id": "USR-TEST0001"
    },
    "expected_output_contains": ["refund", "processed"],
    "swap_test": false
  },
  {
    "id": "refund_002_adversarial",
    "description": "Param swap adversarial — user mentions both IDs",
    "user_id": "USR-TEST0001",
    "conversation": [
      {"role": "user", "content": "Refund order N-20240312-AB123 for user USR-TEST0001"}
    ],
    "expected_intent": "refund_request",
    "expected_params": {
      "order_id": "N-20240312-AB123",
      "user_id": "USR-TEST0001"
    },
    "swap_test": true,
    "should_not_swap": true
  },
  {
    "id": "refund_003_out_of_scope",
    "description": "Refund for order older than 30 days — unsupported case",
    "user_id": "USR-TEST0001",
    "conversation": [
      {"role": "user", "content": "I want a refund on an order from 18 months ago"}
    ],
    "expected_support_status": "IN_DOMAIN_OUT_OF_SCOPE",
    "expected_behavior": "explain_policy_offer_alternatives",
    "swap_test": false
  }
]
```

### 7. Prometheus Metrics — src/observability/metrics_exporter.py

```python
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
    ["resolution_type"]   # resolved / escalated / abandoned
)
escalation_reason_total = Counter(
    "escalation_reason_total",
    "Escalation reasons",
    ["reason"]            # api_failure / policy / complexity / fraud_flag
)

# Cost metrics
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens",
    ["model", "type"]     # input / output
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
    ["metric_name"]       # tool_selection / param / goal_success / hallucination
)
```

### 8. Prompt Hub Client — src/prompts/hub.py

```python
import time
import hashlib
from pathlib import Path
from langfuse import Langfuse
from src.config import settings

class CachedPrompt:
    def __init__(self, template: str, ttl: int):
        self.template = template
        self.expires_at = time.time() + ttl
        self.version = hashlib.md5(template.encode()).hexdigest()[:8]

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def compile(self, **variables) -> str:
        return self.template.format(**variables)


class PromptHubClient:
    """
    Fetches prompts from Langfuse (self-hosted).
    Falls back to local .txt files if hub unavailable.
    Cache TTL: 300 seconds (5 minutes).
    Warmed on startup for all critical prompts.
    """
    CRITICAL_PROMPTS = [
        "customer-support-agent",
        "refund-agent",
        "intent-classifier",
        "output-safety-guard"
    ]

    def __init__(self):
        self.langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST
        )
        self._cache: dict[str, CachedPrompt] = {}
        self._local_dir = Path("src/prompts")

    def warm_cache(self):
        """Call at application startup"""
        for name in self.CRITICAL_PROMPTS:
            try:
                self._fetch_and_cache(name)
            except Exception as e:
                print(f"[PromptHub] WARNING: Could not warm {name}: {e}")

    def get(self, prompt_name: str, label: str = "production", **variables) -> str:
        cached = self._cache.get(prompt_name)
        
        if cached and not cached.is_expired():
            return cached.compile(**variables)
        
        try:
            prompt = self._fetch_and_cache(prompt_name, label)
        except Exception:
            # Fallback to local file
            prompt = self._load_local(prompt_name)
            self._cache[prompt_name] = CachedPrompt(prompt, ttl=60)

        return self._cache[prompt_name].compile(**variables)

    def _fetch_and_cache(self, name: str, label: str = "production") -> str:
        prompt = self.langfuse.get_prompt(name, label=label)
        template = prompt.prompt
        self._cache[name] = CachedPrompt(template, ttl=300)
        return template

    def _load_local(self, name: str) -> str:
        """Local fallback — reads from prompts/ directory"""
        path = self._local_dir / f"{name.replace('-', '_')}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"No local prompt found for: {name}")
```

---

## .env.example — Generate This File

```env
# LLM
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEFAULT_MODEL=claude-sonnet-4-20250514
FAST_MODEL=claude-haiku-4-5-20251001

# Postgres
DATABASE_URL=postgresql://noon:noon_local@localhost:5432/noon_agent

# Redis
REDIS_URL=redis://localhost:6379

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_FAQ=noon_faq
QDRANT_COLLECTION_POLICIES=noon_policies

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000

# Agent config
INTENT_CONFIDENCE_THRESHOLD=0.80
MAX_CONVERSATION_TURN_MS=8000
TOOL_RETRY_MAX_ATTEMPTS=2
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_S=30
PROMPT_CACHE_TTL_S=300

# Eval
EVAL_TOOL_ACCURACY_MIN=0.90
EVAL_PARAM_ACCURACY_MIN=0.95
EVAL_GOAL_SUCCESS_MIN=0.85
EVAL_HALLUCINATION_MAX=0.02

# Cost targets
TARGET_COST_PER_TICKET_USD=0.05
```

---

## Makefile — Generate These Commands

```makefile
.PHONY: up down build seed eval test

up:
	docker-compose up -d
	@echo "Services starting..."
	@echo "Agent:      http://localhost:8000"
	@echo "Langfuse:   http://localhost:3000"
	@echo "RedisInsight: http://localhost:8001"
	@echo "Grafana:    http://localhost:3001"
	@echo "Prometheus: http://localhost:9090"

down:
	docker-compose down

build:
	docker-compose build agent

seed:
	python scripts/seed_intent_index.py
	python scripts/seed_golden_set.py

eval:
	python scripts/run_eval.py --all

test:
	pytest tests/unit/ -v
	pytest tests/integration/ -v

eval-ci:
	pytest tests/eval/test_golden_sets.py -v --tb=short
	@echo "Eval gates: tool>=0.90, param>=0.95, goal>=0.85, hallucination<=0.02"

logs:
	docker-compose logs -f agent

shell:
	docker-compose exec agent bash
```

---

## Grafana Dashboard Panels to Generate

Pre-build a dashboard JSON at infra/grafana/dashboards/noon_agent.json with these panels:

1. **Resolution Rate** — gauge: AI resolved / total conversations (target: >78%)
2. **Cost per Ticket** — stat: rolling 1h average (target: <$0.05)
3. **Intent Classification Accuracy** — time series from eval runs
4. **Tool Error Rate by API** — bar chart: order_api, refund_api, delivery_api
5. **Latency p95 by Layer** — time series: guard, intent, tool, response
6. **Circuit Breaker Status** — table: per tool, current state
7. **Escalation Reasons** — pie chart: api_failure, policy, complexity, fraud
8. **LLM Token Usage** — stacked: input vs output tokens over time
9. **Param Accuracy** — gauge: from latest eval run (target: >95%)
10. **Golden Set Trend** — time series: eval accuracy per commit over 30 days

---

## Build Order for Claude Code

Build in this exact sequence — each step must succeed before the next:

1. `docker-compose.yml` + `.env.example` + `Makefile`
2. `src/config.py` — Pydantic settings
3. `src/agent/state.py` — ConversationState TypedDict
4. `src/intent/registry.py` — full intent registry (10 intents minimum)
5. `src/params/validator.py` — Pydantic schemas for all tool params
6. `src/tools/base.py` — BaseTool with circuit breaker + retry
7. `src/tools/` — all tool implementations (use mock API responses)
8. `src/agent/nodes.py` + `src/agent/edges.py` + `src/agent/graph.py`
9. `src/prompts/hub.py` + all .txt prompt files
10. `src/guard/` — all guard modules
11. `src/intent/` — classifier + vector index + multi-intent
12. `src/memory/` — working + episodic + summarizer
13. `src/rag/` — pipeline + embedder + retriever
14. `src/observability/` — tracer + metrics + cost tracker
15. `src/eval/` — pipeline + judges + metrics + golden sets
16. `src/api/` — FastAPI endpoints
17. `src/main.py` — app entrypoint
18. `tests/` — unit + integration + eval tests
19. `infra/` — Grafana dashboard JSON + Prometheus config
20. `scripts/` — seed + eval scripts

---

## Non-Negotiable Rules

- No prompt content hardcoded in Python files. All prompts in .txt files, fetched via PromptHubClient.
- Every tool must use BaseTool. No direct API calls bypassing retry/circuit breaker.
- Every LangGraph node must emit a Langfuse trace span.
- Pydantic validation on every tool parameter. No raw dict passing to tools.
- ConversationState is the single source of truth. No state outside it.
- All tool calls log: tool_name, params (masked), result_status, latency_ms.
- Golden set must include adversarial cases for every intent (param swap + out-of-scope).
- Eval pipeline must be runnable as a standalone script AND as a pytest test.
- Grafana dashboard must load without manual configuration after `make up`.
- README.md must document every `make` command and every dashboard panel.