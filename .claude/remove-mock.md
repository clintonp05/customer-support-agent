Replace mock implementations in this exact order.
Do not move to next step until current step runs without errors.

Step 1 — embedder.py
Replace mock embeddings with sentence-transformers.
Model: paraphrase-multilingual-MiniLM-L12-v2
Handles: Arabic + English
Install: pip install sentence-transformers
Test: python -c "from src.rag.embedder import Embedder; e = Embedder(); 
      print(e.embed('test query'))"

Step 2 — retriever.py
Replace mock retrieval with Qdrant client.
Create two collections on startup if not exists:
  → noon_intents  (size: 384, distance: Cosine)  ← intent KNN
  → noon_faq      (size: 384, distance: Cosine)  ← RAG retrieval
Install: pip install qdrant-client
QDRANT_URL from settings
Test: curl http://localhost:6333/collections
      → should show noon_intents and noon_faq

Step 3 — working.py
Replace mock checkpointer with LangGraph PostgresSaver.
DATABASE_URL from settings
Install: pip install langgraph-checkpoint-postgres
Test: run a two-turn conversation and verify 
      state persists between turns

Step 4 — tracer.py
Replace mock tracer with Langfuse SDK.
LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, 
LANGFUSE_HOST from settings
Install: pip install langfuse
Every trace must log:
  → conversation_id
  → node name
  → latency_ms
  → token count
  → cost_usd
  → prompt_version
Test: send one message through agent
      → verify trace appears in cloud.langfuse.com

toxicity.py — DO NOT REPLACE
Keep keyword-based mock for now.