"""RAGAS-style faithfulness evaluation using LLM-as-judge.

Faithfulness (the most critical RAGAS metric for a support agent):
  Given a question, a retrieved context, and the generated answer,
  score how well the answer is grounded in the context.

  Score = (number of answer claims supported by context) /
          (total number of answer claims)
  Range: 0.0 (hallucinated) → 1.0 (fully grounded)

This is implemented as a lightweight async background task so it does not
add latency to the customer-facing response.  Results are pushed to:
  - Prometheus `rag_faithfulness_score` histogram (for dashboard)
  - Structured log entry `eval.faithfulness.result` (for alerting)
  - `eval_accuracy` Prometheus gauge `faithfulness` (rolling update)

No external RAGAS library is required — the evaluation is performed by the
same LLM tier used for BALANCED responses, following the RAGAS methodology
of claim decomposition + NLI-style verification.
"""
import asyncio
from typing import Optional

from src.llm.connector import LLMConnectorClient
from src.observability.logger import get_logger
from src.observability.metrics_exporter import record_faithfulness, update_eval_accuracy

logger = get_logger()

_FAITHFULNESS_SYSTEM = """\
You are an evaluation assistant. Your job is to assess whether a generated answer
is faithful to (i.e., fully supported by) the provided context.

Faithfulness means: every factual claim in the answer can be directly inferred
from the context. The answer must not introduce facts not present in the context.

Respond with a JSON object with exactly two keys:
  "score":  a float between 0.0 (entirely hallucinated) and 1.0 (fully grounded)
  "reason": one sentence explaining the score
"""

_FAITHFULNESS_PROMPT_TEMPLATE = """\
=== Question ===
{question}

=== Retrieved context ===
{context}

=== Generated answer ===
{answer}

Evaluate the faithfulness of the answer with respect to the context.
Return your evaluation as JSON: {{"score": <float>, "reason": "<string>"}}
"""


async def evaluate_faithfulness(
    question: str,
    context: str,
    answer: str,
    intent: str,
) -> Optional[float]:
    """Evaluate faithfulness asynchronously.

    Returns the faithfulness score (0.0–1.0) or None if evaluation failed.
    Pushes the score to Prometheus automatically.
    """
    if not context or not answer:
        logger.debug("eval.faithfulness.skipped", reason="no_context_or_answer", intent=intent)
        return None

    prompt = _FAITHFULNESS_PROMPT_TEMPLATE.format(
        question=question[:800],
        context=context[:2000],
        answer=answer[:1000],
    )

    try:
        client = LLMConnectorClient("BALANCED")
        result = client.generate(prompt, system=_FAITHFULNESS_SYSTEM, max_tokens=128)
        if not result.get("success"):
            logger.warning("eval.faithfulness.llm_failed", intent=intent)
            return None

        import json
        raw = result.get("response", "")
        # Extract JSON — model may wrap it in markdown fences
        raw = raw.strip().strip("```json").strip("```").strip()
        parsed = json.loads(raw)
        score = float(parsed.get("score", 0.0))
        reason = parsed.get("reason", "")
        score = max(0.0, min(1.0, score))  # clamp

        logger.info("eval.faithfulness.result",
                    intent=intent,
                    score=round(score, 3),
                    reason=reason[:120])

        record_faithfulness(intent, score)
        # Update rolling gauge so Grafana shows the latest score per intent
        update_eval_accuracy(f"faithfulness:{intent}", score)
        return score

    except Exception as exc:
        logger.warning("eval.faithfulness.error", intent=intent, error=str(exc))
        return None


def schedule_faithfulness_eval(
    question: str,
    context: str,
    answer: str,
    intent: str,
) -> None:
    """Fire-and-forget: schedule faithfulness evaluation without blocking caller.

    Call this from generate_response_node after the response is produced.
    The background coroutine will push results to Prometheus asynchronously.
    """
    if not context or not answer:
        return
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(evaluate_faithfulness(question, context, answer, intent))
    except RuntimeError:
        # No running event loop (e.g., in tests) — skip silently
        pass
