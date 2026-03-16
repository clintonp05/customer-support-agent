# Noon Customer Support Agent — Full System Review & Gap Analysis
**Date:** March 2026 | **Role Target:** AI Engineer (Conversational AI) — SDE-4  
**System:** `ecom-cst-asst-agent` | **Stack:** LangGraph · FastAPI · Qdrant · PostgreSQL · Redis · Langfuse · Prometheus/Grafana

---

## Table of Contents

1. [What Is Actually Built & Working](#1-what-is-actually-built--working)
2. [Where Are the Agents — Honest Assessment](#2-where-are-the-agents--honest-assessment)
3. [Memory Architecture — Short, Long, Semantic, Episodic](#3-memory-architecture--short-long-semantic-episodic)
4. [Critical Bugs Found in Code Review](#4-critical-bugs-found-in-code-review)
5. [RAG Pipeline — What's Missing](#5-rag-pipeline--whats-missing)
6. [Semantic Caching — Not Implemented](#6-semantic-caching--not-implemented)
7. [Intent Classification — Dataset & Evaluation Gaps](#7-intent-classification--dataset--evaluation-gaps)
8. [Evaluation Pipeline — Full Gap Analysis](#8-evaluation-pipeline--full-gap-analysis)
9. [Business Metrics — Conversation Resolution & Economics](#9-business-metrics--conversation-resolution--economics)
10. [Guardrails & Safety — Emotional & Behavioral Signals](#10-guardrails--safety--emotional--behavioral-signals)
11. [Observability — Grafana, Langfuse, Prometheus](#11-observability--grafana-langfuse-prometheus)
12. [Context Management — Session, Topic Deviation](#12-context-management--session-topic-deviation)
13. [Agent Memory Sharing — Multi-Agent Coordination](#13-agent-memory-sharing--multi-agent-coordination)
14. [Parallel vs Sequential Agent Execution](#14-parallel-vs-sequential-agent-execution)
15. [What to Say in the Interview](#15-what-to-say-in-the-interview)
16. [Master Priority List — What to Fix](#16-master-priority-list--what-to-fix)

---

## 1. What Is Actually Built & Working

### Infrastructure ✅
| Component | Status | Details |
|---|---|---|
| PostgreSQL 14 | ✅ Running | Operational DB + conversation turns table |
| Redis | ✅ Running | Query cache + idempotency (in-memory fallback) |
| Qdrant 1.17 | ✅ Running | 3 collections: noon_intents, noon_faq, noon_policies |
| FastAPI | ✅ Running | `/support`, `/health`, `/metrics`, `/ui` |
| Langfuse Cloud | ✅ Connected | Tracing every node via `@trace_node` decorator |
| Prometheus | ✅ Emitting | Counters, histograms, gauges all defined |
| Grafana | ⚠️ Configured | Dashboard needs panels wired to metrics |

### Database Seed ✅
| Table | Count | Notes |
|---|---|---|
| customers | 500 | UAE names, real Sharjah/Dubai/Abu Dhabi addresses |
| products | 500 | Electronics, Mobile, Appliances, Fashion |
| orders | 1,000 | 30% delivered, 20% shipped, 15% confirmed |
| order_items | 3,041 | Multi-item orders |
| payments | 1,000 | COD, credit card, Apple Pay |
| deliveries | 1,000 | 30 deliberately delayed, Fetchr/Aramex/DHL |
| refunds | 200 | Only on orders < 30 days old |
| warranties | 300 | Electronics/Mobile/Laptops/Appliances only |

### Agent Graph ✅
```
guard_input → cache_check → query_analyser
                                ↓
                    intent_analyser + complexity_analyser (parallel fan-out)
                                ↓
                    query_analyse_join → complex_query_orchestrator
                                ↓
                    classify_intent → extract_params → validate_params
                                ↓
                    execute_tools → generate_response → persist_response
```

### Live Demo Results ✅
- Multi-turn conversation working (delivery query → order history pivot)
- Real DB data: Order `N-20260314-ITIKF`, AED 1,579.42, Fetchr `FTR-00000013`
- Response: ~7,300ms (bottleneck: subprocess LLM call — fixable)
- Markdown rendering in chat UI working
- `total_aed` field bug fixed

---

## 2. Where Are the Agents — Honest Assessment

### Current Reality: A Deterministic Pipeline with LLM Nodes

The system as built is **Level 1 — Orchestration**, not true agency:

```
Guard → Classify → Extract → Validate → Execute → Respond
Every step is predetermined.
The LLM fills blanks — it does not decide what to do next.
The manifest decides tool routing, not the LLM.
```

### Where Genuine Agent Behaviour Exists

| Location | Type | Why It Qualifies |
|---|---|---|
| `complexity_analyser_node` | Micro-agent | LLM decides routing label (simple/moderate/complex) |
| `complex_query_orchestrator_node` | ReAct-lite | LLM produces a plan for multi-intent queries |
| `generate_response_node` (escalation) | Weak agent | LLM decides to escalate vs answer |
| LangGraph graph itself | Agent framework | Conditional edges, state-driven routing |

### What Is Missing: True ReAct Agent for Refund/Warranty

A true agent scenario for `refund_request`:

```
Step 1: check_order → finds 3 orders for this user
Step 2: check_refund_eligibility → order is 45 days old, INELIGIBLE
Step 3: [LLM decides to pivot] → check_warranty instead of escalating
Step 4: warranty is active → initiate_claim
```

Your current system **cannot do Step 3**. The manifest chains `check_refund_eligibility → escalate`. The LLM does not reason about alternatives.

### How to Add It (LangGraph `create_react_agent`)

```python
from langgraph.prebuilt import create_react_agent

react_agent = create_react_agent(
    model=claude_haiku,
    tools=[check_order, check_refund_eligibility, initiate_refund,
           check_warranty, escalate_to_human],
    system_prompt=refund_specialist_prompt
)

# Use in execute_tools_node for complex intents only
if intent in {"refund_request", "warranty_claim"}:
    return await react_agent.ainvoke(state)
else:
    return await deterministic_execution(state)  # keep fast path
```

### The 3 Levels of Agency

| Level | Description | What You Have |
|---|---|---|
| Level 1 | Fixed pipeline, LLM fills blanks | order_status, delivery_tracking |
| Level 2 | LLM chooses tools, guardrails enforced | complex_query_orchestrator (partial) |
| Level 3 | LLM fully autonomous, invents paths | NOT built |

**Interview answer:** *"Production-safe hybrid. Deterministic for guard, intent, param layers where predictability matters. Supervised agent loop for tool execution where flexibility is needed. We expand LLM autonomy gradually as eval scores improve."*

---

## 3. Memory Architecture — Short, Long, Semantic, Episodic

### The 4 Memory Types

| Type | Purpose | What You Have | Status |
|---|---|---|---|
| **Working memory** | Current turn context | `ConversationState` TypedDict | ✅ Built |
| **Short-term / Session** | Multi-turn within session | `messages[]` in state + Redis TTL cache | ✅ Built |
| **Episodic** | Past conversations, user history | `EpisodeStore` class | ⚠️ Stub — not wired |
| **Semantic** | World knowledge, policies, FAQs | Qdrant `noon_faq` + `noon_policies` | ⚠️ Not ingested |

### Working Memory (Current Turn)

```python
# ConversationState holds everything for one turn
{
    "conversation_id": "ui-1",
    "messages": [...],          # Full conversation history
    "extracted_params": {...},  # Params accumulated across turns
    "tool_results": {...},      # All tool outputs this turn
    "query_analysis": {...},    # Intent + complexity
    "timings_ms": {...},        # Latency per node
}
```

**What it does well:** State flows through the entire graph. Every node reads and updates the same state object. The `Annotated[Dict, merge_dicts]` reducers handle parallel fan-out safely for `timings_ms` and `query_analysis`.

**What it doesn't do:** It does not survive a server restart. It is not checkpointed between turns correctly (PostgresSaver bug — see Section 4).

### Short-Term Memory (Session Cache)

```python
# persist_response_node writes to Redis
key = f"query:{conversation_id}:{turn_index}"
redis.setex(key, ttl_s, json.dumps(payload))

# guard_input_node checks semantic cache
cache_key = f"query_hash:{sha256(query)}"
cached = redis.get(cache_key)
```

**What it does well:** Identical queries served from cache (< 50ms vs 7000ms).

**What it doesn't do:** This is **hash-based** caching, not semantic caching. "Where is my order" and "track my package" are treated as completely different queries.

### Episodic Memory (Cross-Session History)

```python
# episodic.py — the class exists but is never called
class EpisodeStore:
    async def write_episode(self, conversation_id, user_id, messages, summary): ...
    async def get_context(self, user_id) -> Optional[Dict]: ...
```

**The bug:** `get_context` is never called at session start. `write_episode` is never called at session end. The `episodic_context` field in `ConversationState` is always `None`.

**Why it matters for Noon:** A user who called three times about a delayed order and was already escalated should be recognized. The agent should say "I see you've contacted us twice about this — let me escalate immediately" instead of starting from scratch.

**Fix:**

```python
# In guard_input_node (session start)
episode_store = get_episode_store()
episodic_ctx = await episode_store.get_context(user_id)
state["episodic_context"] = episodic_ctx

# In persist_response_node (session end)
summary = await summarizer.summarize(messages)
await episode_store.write_episode(
    conversation_id=conversation_id,
    user_id=user_id,
    messages=messages,
    summary=summary
)
```

**Production episodic store (what it should be):**

```sql
-- CQRS write side: append-only event log
CREATE TABLE user_support_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    intent TEXT,
    resolution TEXT,   -- resolved / escalated / abandoned
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- CQRS read side: materialized view for fast retrieval
CREATE MATERIALIZED VIEW user_support_summary AS
SELECT user_id,
       COUNT(*) AS total_conversations,
       SUM(CASE WHEN resolution = 'escalated' THEN 1 ELSE 0 END) AS escalations,
       MAX(created_at) AS last_contact,
       array_agg(intent ORDER BY created_at DESC) AS recent_intents
FROM user_support_events
GROUP BY user_id;
```

### Semantic Memory (Knowledge Base)

```python
# Qdrant collections are created and empty
# noon_faq — FAQs, return policies, shipping policies
# noon_policies — refund rules, warranty terms
# noon_intents — utterances for vector-based classification
```

**The gap:** All three collections exist in Qdrant but contain zero documents. RAG calls in `generate_response_node` return empty results. The system falls back to pure LLM generation with no grounding.

---

## 4. Critical Bugs Found in Code Review

### Bug 1 🔴 — Conditional Tool Chains Not Executed

**File:** `src/agent/nodes.py` + `src/tools/manifest.py`

**Problem:** The intent registry defines conditional branching (eligible → initiate_refund, ineligible → escalate_to_human) but `execute_tools_node` reads a flat `TOOL_CHAINS` dict that hardcodes `["check_order", "check_refund_eligibility", "initiate_refund"]` — unconditionally calling `initiate_refund` regardless of eligibility result.

**Impact:** Ineligible refunds get initiated. A user with a 45-day-old order would receive a refund confirmation incorrectly.

**Fix:** After running `check_refund_eligibility`, read `result["eligible"]` and branch to either `initiate_refund` or `escalate_to_human` before continuing the tool chain.

---

### Bug 2 🔴 — Idempotency Keys Are In-Memory

**File:** `src/tools/refund_tool.py`

```python
self._processed_refunds: Dict[str, dict] = {}  # Lost on every restart
```

**Impact:** Double refunds possible on server restart. In production with multiple pods, each pod has its own dict — a user hitting pod-2 after pod-1 processed the refund gets a second refund.

**Fix:** Move idempotency keys to Redis with a 7-day TTL:

```python
redis.setex(f"refund_idem:{idem_key}", 86400 * 7, json.dumps(result))
```

---

### Bug 3 🔴 — LangGraph Parallel Fan-Out Has Race Condition

**File:** `src/agent/graph.py`

```python
workflow.add_edge("query_analyser", "intent_analyser")
workflow.add_edge("query_analyser", "complexity_analyser")
```

Both branches write to `detected_intents` and `primary_intent`. These fields have no merge reducer in `ConversationState`, so whichever branch finishes last silently overwrites the other.

**Fix:** Either make them sequential (`intent_analyser → complexity_analyser → query_analyse_join`) or add proper reducers for `detected_intents` and `primary_intent`.

---

### Bug 4 🟡 — PostgresCheckpointer Uses Raw psycopg2 Connection

**File:** `src/memory/working.py`

```python
conn = psycopg2.connect(self.database_url)  # Single raw connection
self.saver = PostgresSaver(conn)             # LangGraph expects psycopg v3 pool
# Missing: self.saver.setup()               # Never creates checkpoint tables
```

**Fix:**

```python
from psycopg_pool import ConnectionPool
pool = ConnectionPool(conninfo=self.database_url)
pool.wait()
self.saver = PostgresSaver(pool)
self.saver.setup()  # Creates langgraph_checkpoints table
```

---

### Bug 5 🟡 — ProductTool Registered But Not in Manifest

**File:** `src/tools/manifest.py`

`ProductTool` exists in `src/tools/product_tool.py` but is never imported into the manifest. `TOOL_CHAINS["product_inquiry"]` is empty. Product inquiries return no tool results and fall back to generic LLM response.

---

### Bug 6 🟡 — `classify_intent` Node Is Dead Code

**File:** `src/agent/graph.py` + `src/agent/edges.py`

`classify_intent` is listed as a possible destination in `guard_input`'s conditional edges, but `route_after_guard` only ever returns `"escalate"` or `"query_analyser"`. The `classify_intent` path is unreachable.

---

### Bug 7 🟡 — Episodic Memory Never Wired

**File:** `src/memory/episodic.py`

The class is complete but no node calls `write_episode` or `get_context`. Every session starts with `episodic_context: None`.

---

## 5. RAG Pipeline — What's Missing

### Current State

```python
# pipeline.py — retrieval is called correctly
if intent in {"refund_request", "warranty_claim"}:
    knowledge = await retrieve_knowledge(query)

# retriever.py — Qdrant client works, collections exist
results = client.query_points(collection_name=collection, query=query_vector, limit=3)
```

**The pipeline is wired correctly. The problem: zero documents have been ingested.**

### What Needs to Be Ingested

| Collection | Content | Priority |
|---|---|---|
| `noon_faq` | Return policy (30-day window), shipping times, payment methods, COD policy | 🔴 Critical |
| `noon_policies` | Warranty terms by category, refund eligibility rules, escalation policy | 🔴 Critical |
| `noon_intents` | Intent utterances from registry (for vector-based classification) | 🟡 High |

### Ingestion Script Needed

```python
# scripts/ingest_knowledge.py
faq_docs = [
    {"content": "noon's return policy allows returns within 30 days of delivery...", "source": "return_policy"},
    {"content": "Refunds are processed within 5-7 business days...", "source": "refund_policy"},
    {"content": "Cash on delivery (COD) orders must be paid at time of delivery...", "source": "payment_policy"},
    {"content": "Warranty claims are accepted for Electronics, Mobile, Laptops, and Appliances...", "source": "warranty_policy"},
    {"content": "Delivery in UAE typically takes 2-5 business days...", "source": "shipping_policy"},
]
retriever = get_retriever()
await retriever.add_documents("noon_faq", faq_docs)
```

### RAG Evaluation Metrics Missing

| Metric | What It Measures | Target |
|---|---|---|
| **Recall@K** | Are relevant docs in the top-K results? | Recall@3 ≥ 0.85 |
| **Groundedness** | Is the response factually grounded in retrieved docs? | ≥ 0.90 |
| **Relevance score** | Are retrieved docs relevant to the query? | Avg score ≥ 0.65 |
| **Faithfulness** | Does the LLM response contradict the retrieved context? | ≤ 0.05 |

**How to measure Recall@K:**

```python
# Build a golden set of query → expected_doc_source pairs
golden = [
    {"query": "can I return after 30 days", "expected_source": "return_policy"},
    {"query": "how long does refund take", "expected_source": "refund_policy"},
]

# For each golden query
results = await retriever.retrieve(query, "noon_faq", limit=3)
sources = [r["source"] for r in results]
hit = expected_source in sources  # Recall@3 = hit rate across all golden queries
```

**How to measure Groundedness (LLM-as-judge):**

```python
judge_prompt = f"""
Retrieved context: {retrieved_docs}
Agent response: {final_response}

Is the response factually grounded in the retrieved context?
Score from 0.0 to 1.0. Only return a number.
"""
score = float(llm.generate(judge_prompt).strip())
```

---

## 6. Semantic Caching — Not Implemented

### What's Built (Hash Cache Only)

```python
# guard_input_node
key = hashlib.sha256(raw_query.strip().lower().encode()).hexdigest()
cache_key = f"query_hash:{key}"
cached = redis.get(cache_key)
```

This is **exact match only**. "Where is my order" and "track my package" are two different cache keys. Cache hit rate in practice will be < 5%.

### What Semantic Caching Would Look Like

```python
class SemanticCache:
    """Cache based on embedding similarity, not exact hash."""
    
    async def lookup(self, query: str, threshold: float = 0.92) -> Optional[Dict]:
        query_vec = embedder.embed([query])[0]
        
        # Search Qdrant for semantically similar past queries
        results = client.query_points(
            collection_name="semantic_cache",
            query=query_vec,
            limit=1,
            score_threshold=threshold,   # 0.92 = near-identical meaning
            with_payload=True
        )
        
        if results.points:
            cached_response = results.points[0].payload.get("response")
            logger.info("semantic_cache.hit", score=results.points[0].score)
            return cached_response
        return None
    
    async def write(self, query: str, response: str, ttl_s: int = 3600):
        query_vec = embedder.embed([query])[0]
        client.upsert("semantic_cache", points=[
            PointStruct(
                id=uuid.uuid4().int >> 64,
                vector=query_vec,
                payload={"query": query, "response": response, "created_at": time.time()}
            )
        ])
```

### Why It Matters for Noon

Customer support queries are highly repetitive:
- "where is my order" / "track my order" / "order status" → same response shape
- "I want a refund" / "get my money back" / "return this" → same flow

Semantic caching at 0.92 threshold would hit ~30-40% of queries, reducing LLM calls significantly.

**Cost impact:** If 35% of queries hit semantic cache, cost per ticket drops from $0.05 to ~$0.033.

---

## 7. Intent Classification — Dataset & Evaluation Gaps

### Current Classifier: Word Overlap (Not Semantic)

```python
def _calculate_similarity(self, query: str, utterance: str) -> float:
    query_words = set(query.split())
    utterance_words = set(utterance.split())
    intersection = query_words & utterance_words
    return len(intersection) / len(utterance_words)  # Jaccard word overlap
```

**Problems:**
- "أين طلبي" (Arabic for "where is my order") → scores 0.0 against all English utterances
- Semantically similar phrases with no word overlap → always miss
- "My MacBook broke" → zero overlap with "broken product" or "warranty claim"

### What Each Intent Needs in a Production Dataset

| Intent | Utterance Count Needed | Languages | Edge Cases |
|---|---|---|---|
| refund_request | 50+ | en, ar, mixed | "I was overcharged", "double billing", "charged twice" |
| order_status | 50+ | en, ar, mixed | "my package", "N-20260314-ITIKF status", with/without order ID |
| delivery_tracking | 50+ | en, ar, mixed | "when will it arrive", "still not delivered", "3 days late" |
| warranty_claim | 40+ | en, ar, mixed | "broken after 2 months", "dead on arrival", "screen cracked" |
| cancel_order | 30+ | en, ar, mixed | "cancel before delivery", "I changed my mind" |
| speak_to_human | 20+ | en, ar, mixed | "I want to talk to someone", "get me a manager" |
| end_conversation | 20+ | en, ar, mixed | "thanks", "bye", "شكراً", "مع السلامة" |

**Total:** ~400+ labeled utterances minimum for a meaningful fine-tuned classifier.

### What the Classifier Should Be

```
Stage 1: Vector similarity via Qdrant noon_intents
          Embed utterances from registry at startup
          At classification time: embed query → KNN search → top-1 intent + score
          
Stage 2: Confidence threshold gate
          score ≥ 0.80 → use Stage 1 result
          score < 0.80 → fallback to zero-shot BART-large-mnli
          
Stage 3: Zero-shot with action-oriented labels (proven in experiments)
          Labels: "get money back", "track my item", "broken product"
          NOT: "refund_request", "delivery_tracking", "warranty_claim"
```

### Key Finding from Earlier Experiments

Action-oriented labels vs business taxonomy labels:
- `"refund_request"` → BART-large-mnli score: 0.508
- `"get my money back"` → BART-large-mnli score: 0.921

**Always use customer-language labels, not system names, in zero-shot classification.**

---

## 8. Evaluation Pipeline — Full Gap Analysis

### What's Built

```python
# eval/pipeline.py + eval/metrics.py + eval/judges.py
class EvalPipeline:
    async def run(self, golden_set_name: str) -> EvalMetrics: ...

class EvalMetrics:
    tool_selection_accuracy: float  # target ≥ 0.90
    param_accuracy: float           # target ≥ 0.95
    goal_success_rate: float        # target ≥ 0.85
    hallucination_rate: float       # target ≤ 0.02
```

### What's Missing

#### 1. Golden Dataset Files

```
src/eval/golden_sets/  ← DIRECTORY EXISTS BUT IS EMPTY
    order_status.json
    delivery_tracking.json
    refund_eligible.json
    refund_ineligible.json
    warranty_claim.json
    multi_turn.json
    arabic_queries.json
    angry_customer.json
    obscene_customer.json
```

**Each golden case needs:**

```json
{
  "id": "order_status_001",
  "user_id": "USR-00397",
  "conversation": [
    {"role": "user", "content": "where is my order N-20260314-ITIKF"}
  ],
  "expected_intent": "order_status",
  "expected_tool": "check_order",
  "expected_params": {"order_id": "N-20260314-ITIKF", "user_id": "USR-00397"},
  "expected_output_contains": ["Out for Delivery", "Fetchr", "FTR-00000013"]
}
```

#### 2. Tool Selection Accuracy in Agent Flow

The eval pipeline tests the full agent graph, but the `tools_executed` list it compares against doesn't account for conditional branching. For refund flows:
- eligible path: `["check_order", "check_refund_eligibility", "initiate_refund"]`
- ineligible path: `["check_order", "check_refund_eligibility", "escalate_to_human"]`

The judge needs to know which path was expected, not just a single `expected_tool`.

#### 3. Hallucination Detection

```python
# Current judge — always returns False
hallucinated = False  # ← placeholder only
```

**Production hallucination check:**

```python
async def check_hallucination(response: str, tool_results: dict, threshold: float = 0.02) -> bool:
    # Extract all factual claims from response (order IDs, amounts, dates)
    # Verify each claim against tool_results
    # Flag if response contains data not present in tool_results
    
    judge_prompt = f"""
    Tool results (ground truth): {json.dumps(tool_results)}
    Agent response: {response}
    
    Does the response contain any facts NOT present in the tool results?
    Return JSON: {{"hallucinated": true/false, "details": "..."}}
    """
    result = json.loads(llm.generate(judge_prompt))
    return result["hallucinated"]
```

#### 4. Missing Eval Scenarios

| Scenario | Coverage | Priority |
|---|---|---|
| Order not found | ❌ | 🔴 |
| Refund ineligible (> 30 days) | ❌ | 🔴 |
| Warranty expired | ❌ | 🔴 |
| Multi-turn: delivery → refund pivot | ❌ | 🔴 |
| Arabic query | ❌ | 🔴 |
| Mixed Arabic-English | ❌ | 🟡 |
| Parameter swap (orderId as userId) | ❌ | 🟡 |
| Duplicate refund attempt | ❌ | 🟡 |
| Circuit breaker open | ❌ | 🟡 |
| Toxic input → escalation | ❌ | 🟡 |
| Angry/frustrated tone | ❌ | 🟡 |

#### 5. Recall@K and Groundedness Not Wired to Pipeline

```python
class EvalMetrics:
    # Missing fields:
    recall_at_k: float        # RAG retrieval quality
    groundedness: float       # Response grounded in retrieved docs
    rag_relevance: float      # Are retrieved docs relevant?
    faithfulness: float       # Does response contradict context?
    intent_accuracy: float    # Classifier accuracy on golden set
    latency_p50_ms: float     # 50th percentile response time
    latency_p95_ms: float     # 95th percentile response time
    escalation_rate: float    # % of conversations escalated
    resolution_rate: float    # % of conversations resolved by agent
```

---

## 9. Business Metrics — Conversation Resolution & Economics

### What's Built

```python
# metrics_exporter.py — Prometheus counters defined
conversation_resolution_total     # resolved / escalated / abandoned
cost_per_conversation_usd         # histogram
llm_tokens_total                  # by model and type
eval_accuracy                     # gauge by metric name
```

### What's Not Being Recorded

**Resolution status is never set.** The `persist_response_node` writes to DB but never calls `record_conversation_resolution()`. Prometheus gets no data.

**Fix:**

```python
# In persist_response_node
escalation_required = state.get("escalation_required", False)
final_response = state.get("final_response", "")

if escalation_required:
    resolution_type = "escalated"
elif "transfer" in final_response.lower() or "human agent" in final_response.lower():
    resolution_type = "escalated"
else:
    resolution_type = "resolved"

record_conversation_resolution(resolution_type)
```

### The North Star Metric

```
Cost per resolved ticket = Total LLM cost / Conversations resolved by AI agent

Current target:  < $0.05 per ticket
Haiku cost:      ~$0.001 per conversation (simple queries)
Sonnet cost:     ~$0.008 per conversation (complex queries)
Blended target:  $0.003–0.005 per resolved ticket
```

### Full Business Metrics Dashboard

| Metric | Description | Tool | Target |
|---|---|---|---|
| **resolution_rate** | % conversations resolved without human | Prometheus | ≥ 80% |
| **escalation_rate** | % conversations sent to human | Prometheus | ≤ 20% |
| **avg_time_to_resolution_ms** | Time from first message to final response | Prometheus | ≤ 3,000ms |
| **cost_per_resolved_ticket_usd** | LLM cost ÷ resolved tickets | Cost tracker | ≤ $0.05 |
| **tool_success_rate** | % tool calls returning success | Prometheus | ≥ 0.95 |
| **csat_proxy** | Conversation ended naturally vs abandoned | Langfuse | ≥ 4/5 |
| **intent_coverage** | % queries matched to a known intent | Prometheus | ≥ 0.90 |
| **hallucination_rate** | % responses containing fabricated facts | Eval pipeline | ≤ 0.02 |
| **latency_p95_ms** | 95th percentile end-to-end latency | Prometheus | ≤ 5,000ms |
| **cache_hit_rate** | % queries served from Redis cache | Prometheus | ≥ 0.25 |

### Conversation-Level Time Tracking

```python
# What we have in timings_ms:
{
    "guard_input": 12.3,
    "intent_classification": 187.0,
    "complexity_analysis": 210.0,
    "param_extraction": 95.0,
    "param_validation": 8.0,
    "tool:check_order": 42.0,
    "rag_retrieval": 310.0,
    "llm_generation": 6100.0,   # ← bottleneck
    "persist_response": 18.0
}

# What's missing:
# - Total conversation time (first message → final response)
# - Time to first token (streaming not implemented)
# - Queue wait time (if any)
```

---

## 10. Guardrails & Safety — Emotional & Behavioral Signals

### Current Guard Layer

```python
# guard/toxicity.py — keyword matching only
TOXIC_KEYWORDS = ["hate", "kill", "attack", "threat", "violence", "abuse", "harass", "spam", "scam"]

def check_toxicity(text: str) -> Tuple[bool, float]:
    text_lower = text.lower()
    for keyword in TOXIC_KEYWORDS:
        if keyword in text_lower:
            return True, 0.95
    return False, 0.0
```

### What's Missing: Customer Emotional State Detection

#### Dataset Needed

The system needs a labeled dataset of real customer support messages across emotional tones:

| Tone | Example | Required Response |
|---|---|---|
| **Angry** | "This is UNACCEPTABLE! I've been waiting 2 weeks!!!" | Acknowledge, prioritize, de-escalate |
| **Frustrated** | "I've contacted you 3 times about this already" | Acknowledge history, fast-track |
| **Polite** | "Hi, could you please help me with..." | Standard flow |
| **Demanding** | "I want a refund NOW or I'm going to..." | Acknowledge urgency, do not match tone |
| **Obscene** | Contains profanity, insults | Graceful redirect, do not engage |
| **Threatening** | "I'll destroy your reputation..." | Immediate escalation + log |
| **Distressed** | "This is the third time, I really need this money back" | Empathy first, fast resolution |
| **Arabic angry** | "أنا غاضب جداً من هذه الخدمة" | Same handling in Arabic |

#### Emotional State Node (Not Built)

```python
@trace_node("detect_emotion")
async def detect_emotion_node(state: ConversationState) -> Dict[str, Any]:
    """Detect customer emotional state and adjust response strategy."""
    query = state["raw_query"]
    messages = state["messages"]
    
    # Signals:
    # - Caps lock ratio > 0.3 → likely angry
    # - Exclamation density > 0.05 → frustrated
    # - Repeat contact (episodic memory) → frustrated
    # - Escalating message length across turns → building frustration
    # - Explicit phrases: "unacceptable", "worst", "never again"
    
    caps_ratio = sum(1 for c in query if c.isupper()) / max(len(query), 1)
    exclamation_count = query.count("!")
    
    if caps_ratio > 0.3 or exclamation_count > 2:
        emotion = "angry"
        priority = "high"
    elif state.get("episodic_context", {}).get("total_conversations", 0) > 2:
        emotion = "frustrated_repeat"
        priority = "high"
    else:
        emotion = "neutral"
        priority = "normal"
    
    return {
        "query_analysis": {
            **state.get("query_analysis", {}),
            "emotion": emotion,
            "priority": priority
        }
    }
```

#### Prompt Adjustment by Emotion

```python
# generate_response_node should read emotion and adjust tone
emotion = state.get("query_analysis", {}).get("emotion", "neutral")

if emotion == "angry":
    tone_instruction = "Begin with a sincere apology. Acknowledge the inconvenience. Do not be defensive."
elif emotion == "frustrated_repeat":
    tone_instruction = "Acknowledge they have contacted us before. Prioritize resolution. Offer compensation if eligible."
elif emotion == "neutral":
    tone_instruction = "Be professional, concise, and helpful."
```

### Guardrail Dataset Needed

Minimum 200 labeled examples per category:

| Category | Examples | Guard Action |
|---|---|---|
| Toxic | "you're all idiots..." | Block + escalate |
| Obscene | Profanity + support request | Soft redirect |
| Threatening | Legal threats, reputation threats | Log + escalate |
| Spam | Repeated identical queries | Rate limit |
| PII submission | "my credit card is 4111..." | Mask + process |
| Out of domain | Asking about competitors | Redirect politely |
| Jailbreak | "ignore previous instructions..." | Block |

---

## 11. Observability — Grafana, Langfuse, Prometheus

### Langfuse Status

**What's wired:**
- `@trace_node` decorator on every node → creates a span per node in Langfuse
- `LangfuseTracer.trace()` context manager on the top-level `support_query` handler
- Node metadata includes `conversation_id` and node name

**What's missing:**
- Prompt versions not being written to `state["prompt_versions"]` — the field exists but is never populated
- Token counts not sent to Langfuse (only logged locally)
- Score/feedback not sent when conversation resolves — Langfuse supports `langfuse.score()` for CSAT or resolution tracking
- Generation objects not used — Langfuse has a specific `generation` type that captures model name, prompt, response, token counts, and cost in a structured way

**What to verify:**
```bash
# Check if traces are appearing in cloud.langfuse.com
# Filter by: conversation_id = "ui-1"
# You should see: guard_input → intent_analyser → ... → persist_response
# Each span should have latency_ms in metadata
```

### Prometheus Status

**What's emitting (defined):**
```
intent_classifications_total{intent, status}
tool_calls_total{tool_name, status}
tool_latency_ms{tool_name}
circuit_breaker_state{tool_name}
conversation_resolution_total{resolution_type}
escalation_reason_total{reason}
llm_tokens_total{model, type}
cost_per_conversation_usd (histogram)
eval_accuracy{metric_name}
```

**What's NOT being called:**
- `record_conversation_resolution()` — never called
- `record_tool_call()` — never called from `execute_tools_node`
- `record_llm_tokens()` — never called from LLM connector
- `update_eval_accuracy()` — never called
- `record_cost_per_conversation()` — never called

**Fix for execute_tools_node:**
```python
from src.observability.metrics_exporter import record_tool_call

result = await tool.execute(params, state)
record_tool_call(
    tool_name=tool_name,
    status="success" if result.get("success") else "error",
    latency_ms=tool_elapsed
)
```

### Grafana Dashboard Panels Needed

| Panel | Metric Query | Type |
|---|---|---|
| Resolution Rate | `rate(conversation_resolution_total{resolution_type="resolved"}[5m])` | Stat |
| Escalation Rate | `rate(conversation_resolution_total{resolution_type="escalated"}[5m])` | Stat |
| Intent Distribution | `sum by (intent) (intent_classifications_total)` | Pie chart |
| Tool Latency P95 | `histogram_quantile(0.95, tool_latency_ms)` | Time series |
| LLM Cost/hr | `rate(cost_per_conversation_usd_sum[1h])` | Time series |
| Circuit Breaker | `circuit_breaker_state` | State timeline |
| Cache Hit Rate | Redis INFO stats | Stat |
| Error Rate | `rate(tool_calls_total{status="error"}[5m])` | Time series |

---

## 12. Context Management — Session, Topic Deviation

### Current Context Window

```python
# Every turn sends the full message history to the LLM
conversation_text = "\n".join([
    f"{msg.get('role')}: {msg.get('content')}"
    for msg in state.get("messages", [])
])
```

**Problem:** No context window management. A 50-turn conversation sends 50 messages to the LLM on every turn. At ~500 tokens per message, that's 25,000 tokens per LLM call = $0.075 per call on Sonnet.

**Fix — sliding window + summarization:**

```python
MAX_CONTEXT_TURNS = 10

def build_context(messages: List[Dict], summarizer) -> str:
    if len(messages) <= MAX_CONTEXT_TURNS:
        return format_messages(messages)
    
    # Summarize old turns, keep recent ones in full
    old_messages = messages[:-MAX_CONTEXT_TURNS]
    recent_messages = messages[-MAX_CONTEXT_TURNS:]
    
    summary = summarizer.summarize(old_messages)
    return f"[Conversation summary: {summary}]\n\n{format_messages(recent_messages)}"
```

### Topic Deviation Detection (Not Built)

When a customer switches topics mid-conversation:
- Turn 1: "where is my order"
- Turn 2: "I also want to return my laptop"

The system detects multi-intent via `split_into_intents()` but only within a single message. Across turns, there's no topic deviation detection.

**What's needed:**

```python
@trace_node("detect_topic_deviation")
async def detect_topic_deviation_node(state: ConversationState) -> Dict[str, Any]:
    current_intent = state.get("primary_intent")
    previous_intents = state.get("query_analysis", {}).get("intent_history", [])
    
    if previous_intents and current_intent != previous_intents[-1]:
        deviation_detected = True
        # Options:
        # 1. Complete previous intent first, then address new one
        # 2. Acknowledge pivot: "I see you also want to... let me address both"
        # 3. If security-relevant (user ID change mid-session), flag for review
    
    return {
        "query_analysis": {
            **state.get("query_analysis", {}),
            "intent_history": previous_intents + [current_intent],
            "topic_deviation": deviation_detected
        }
    }
```

### Session Identity and Security

**Current:** `user_id` is passed as a parameter, trusted as-is. No session token validation.

**Risk in production:** A user could pass any `user_id` and query another user's orders. The DB query does `WHERE order_id = ? AND user_id = ?` which is correct — but the `user_id` itself is not authenticated.

**What needs to be added:**
- JWT token validation middleware
- `user_id` extracted from validated token, not from request body
- Session binding: `user_id` must match across all turns in a `conversation_id`

---

## 13. Agent Memory Sharing — Multi-Agent Coordination

### Current Architecture

All "agents" (complexity_analyser, complex_intent_agent, complex_refine_agent) share state through `ConversationState`. This works because they all operate on the same LangGraph state object.

```python
# The join nodes rely on state merging
async def query_analyse_join_node(state: ConversationState) -> Dict[str, Any]:
    # At this point, intent_analyser and complexity_analyser have both written to state
    support_status = state.get("intent_support_status")
    return {"next_node": "complex_query_orchestrator"}
```

### The Shared State Problem

When `intent_analyser` and `complexity_analyser` run in parallel, they both update `state["query_analysis"]`. Because `query_analysis` uses `merge_dicts` reducer, the results are merged. But:

- `intent_analyser` sets `detected_intents`, `primary_intent`, `intent_confidence`
- `complexity_analyser` sets `query_analysis.complexity`
- Both set entries in `timings_ms` (safe, merged correctly)
- `primary_intent` — no reducer, last writer wins

### How Memory Is Shared Between Agents (Correct Pattern)

```python
# LangGraph's state object is the shared memory bus
# All agents read from and write to the SAME state object
# Reducers control how concurrent writes are merged

class ConversationState(TypedDict):
    # Parallel-safe: Annotated with merge reducer
    query_analysis: Annotated[Dict[str, Any], merge_dicts]
    timings_ms: Annotated[Dict[str, float], merge_dicts]
    
    # NOT parallel-safe: Last writer wins (bug)
    detected_intents: List[str]
    primary_intent: str
```

**In a true multi-agent system with independent agents:**
```python
# Each agent needs its own namespace in shared state
query_analysis: {
    "intent_analyser": {"intent": "order_status", "confidence": 0.92},
    "complexity_analyser": {"complexity": "simple", "word_count": 8},
    # Join node reads both and produces final decision
}
```

---

## 14. Parallel vs Sequential Agent Execution

### What's Intended (Graph Definition)

```python
# Intended: fan-out to two parallel agents
workflow.add_edge("query_analyser", "intent_analyser")
workflow.add_edge("query_analyser", "complexity_analyser")
workflow.add_edge("intent_analyser", "query_analyse_join")
workflow.add_edge("complexity_analyser", "query_analyse_join")
```

### What's Implemented vs What LangGraph Does

LangGraph does support fan-out with `add_edge` from one node to two nodes. Both nodes execute concurrently as coroutines. The join node waits for both to complete before proceeding.

**The issue is not concurrency — it's state merging.** `detected_intents` and `primary_intent` have no reducer, so the race condition is in state merging, not execution order.

### For Complex Query: Sequential Sub-Agents

```python
# complex_query_orchestrator → complex_intent_agent → complex_refine_agent
# These ARE sequential (joined via complex_query_join)
# complex_intent_agent gets: what are the intents?
# complex_refine_agent gets: what are the clean sub-queries?
# complex_query_join: merge and continue
```

This is correct and is a real multi-agent pattern. The orchestrator plans, sub-agents execute specialized tasks, the join merges results.

### What a True Parallel Agent System Would Look Like

```python
# For multi-intent: "I want a refund AND track my other order"
# Both intents execute in parallel:
from langgraph.types import Send

def fan_out_to_intents(state):
    intents = state["query_analysis"]["multi_intents"]
    return [Send("execute_tools", {"intent": intent, ...}) for intent in intents]

workflow.add_conditional_edges("extract_params", fan_out_to_intents, ["execute_tools"])
```

This is Level 2+ agency — the graph dynamically spawns N execution branches based on LLM analysis.

---

## 15. What to Say in the Interview

### Opening Statement (2 minutes)

*"In the last two weeks I've built a production-grade customer support agent for e-commerce. The stack is LangGraph for orchestration, Qdrant for vector retrieval, Postgres for operational data and conversation persistence, Redis for caching, Langfuse for observability, and Prometheus with Grafana for metrics.*

*The agent handles real multi-turn conversations with actual database queries — UAE customers, real order distributions, deliberate edge cases including delayed deliveries, ineligible refunds, and expired warranties.*

*I'll be honest about where it sits on the maturity curve: the pipeline is production-safe with deterministic routing for guard, intent, and param layers. The LLM has genuine decision authority in the complexity analyser and escalation logic. Adding a ReAct agent loop for refund and warranty flows is the next step — I've designed it, I know exactly what needs to change. The reason I didn't ship it yet is that I want eval coverage before expanding LLM autonomy."*

### On Agent Architecture

*"The system is a hybrid. For simple intents like order status and delivery tracking, it's a deterministic pipeline — guard, classify, extract, execute, respond. Predictable, fast, cheap. For complex intents like refund and warranty, I've designed a supervised ReAct agent that can pivot — if refund is ineligible, the LLM can decide to check warranty instead of escalating. The manifest acts as guardrails. We expand autonomy as eval scores improve."*

### On Memory

*"Four memory types: working memory is the LangGraph state object carrying context through a turn. Short-term session memory is Redis with TTL. Episodic memory is an episode store in Postgres — the class is built, the wiring to nodes is the next task. Semantic memory is Qdrant with FAQs and policy documents — collections are ready, ingestion pipeline is the gap I'm closing."*

### On Evaluation

*"North star metric is cost per resolved ticket, target under five cents. Supporting metrics are tool selection accuracy above 90%, param accuracy above 95%, goal success rate above 85%, hallucination rate below 2%. Recall@3 on RAG retrieval, groundedness score via LLM-as-judge. The eval pipeline and judge are built — the golden dataset is what I'm generating now."*

### On Production Readiness

*"Three things I'd fix before sending real traffic: one — move the refund idempotency key from in-memory to Redis, because the current implementation doesn't survive restarts or horizontal scaling. Two — wire the Prometheus counters that are defined but not called. Three — ingest the policy documents into Qdrant so RAG returns real content instead of empty results. Everything else is optimization."*

### On Latency (7 seconds)

*"Seven seconds in the demo is the subprocess spawn overhead from running Ollama locally. Switching to the Anthropic API directly drops it to under two seconds — I've already built the connector with circuit breaker and backoff logic. Adding response streaming cuts perceived latency further because the customer sees words appearing at 200ms instead of waiting 2 seconds for the full response."*

---

## 16. Master Priority List — What to Fix

### 🔴 Critical (Fix Before Interview)

| # | Fix | File | Time |
|---|---|---|---|
| 1 | Conditional tool chain execution (refund eligibility branching) | `nodes.py`, `manifest.py` | 45 min |
| 2 | Redis-backed idempotency keys for RefundTool | `refund_tool.py` | 30 min |
| 3 | Switch LLM from subprocess ollama to Anthropic API | `connector.py` | 15 min (already designed) |
| 4 | Wire Prometheus counters (record_tool_call, record_conversation_resolution) | `nodes.py` | 20 min |
| 5 | Fix parallel fan-out race condition (make sequential) | `graph.py` | 15 min |

### 🟡 High Priority (Within 48 hours)

| # | Fix | File | Time |
|---|---|---|---|
| 6 | Register ProductTool in manifest | `manifest.py` | 5 min |
| 7 | Ingest FAQ and policy documents into Qdrant | New script | 2 hours |
| 8 | Wire episodic memory (read at session start, write at session end) | `nodes.py`, `episodic.py` | 1 hour |
| 9 | Create golden dataset (5 scenarios minimum) | `eval/golden_sets/` | 2 hours |
| 10 | Fix PostgresCheckpointer (psycopg v3 pool + setup()) | `working.py` | 30 min |

### 🟢 Production Hardening (Week 1 at Noon)

| # | Fix | Description |
|---|---|---|
| 11 | Semantic caching | Qdrant-backed similarity cache, 0.92 threshold |
| 12 | Emotional state detection | Anger/frustration detection, priority routing |
| 13 | Context window management | Sliding window + summarization for long conversations |
| 14 | ReAct agent for refund/warranty | `create_react_agent` with tool pivoting |
| 15 | Recall@K and groundedness in eval | LLM-as-judge scoring for RAG quality |
| 16 | Full golden dataset (400+ examples) | All intents, Arabic, edge cases, emotional tones |
| 17 | JWT session validation | User ID from token, not request body |
| 18 | Topic deviation detection | Cross-turn intent shift awareness |
| 19 | Semantic intent classifier (Qdrant KNN) | Replace word overlap with vector search |
| 20 | Grafana dashboard panels | 8 panels covering all business metrics |

---

## Appendix: Key Architecture Decisions to Defend in Interview

| Decision | What You Chose | Why | Trade-off |
|---|---|---|---|
| LangGraph over raw Python | StateGraph with typed state | Built-in checkpointing, conditional edges, fan-out | Heavier than raw coroutines for simple flows |
| Deterministic pipeline + agent hybrid | Not fully agentic | Predictable in production, agents expand with confidence | Less flexible than pure ReAct |
| KNN over HNSW for intent index | Exact KNN | 1500 intents max, entire index fits in 9MB RAM, 2ms search | Doesn't scale past ~100K intents |
| Separate intent + RAG vector stores | noon_intents vs noon_faq | Different SLA (intent: <10ms, RAG: <300ms), different update frequency | More infra to manage |
| Haiku for speed, Sonnet for complex | Tiered model routing | 15x cost difference, speed vs quality tradeoff | More routing logic |
| Prompts in Langfuse, not code | PromptHub with 5-min TTL | A/B test prompts without code deploy | Latency on cache miss |
| Action-oriented intent labels | "get money back" vs "refund_request" | Empirically 0.921 vs 0.508 in BART-large-mnli | Harder to map to code |
| CQRS for episode store | Append-only events + materialized view | High write throughput, fast read queries | More complex schema |

---

*Document generated: March 2026 | ecom-cst-asst-agent v0.1.0 | Target: Noon AI Engineer Interview*