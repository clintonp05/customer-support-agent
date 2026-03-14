"""LLM connector client for routing by speed/accuracy tiers."""
import subprocess
import json
from typing import Dict, Any

from src.config import settings
from src.observability.logger import get_logger

logger = get_logger()

MODEL_TIER_MAP = {
    "SPEED": settings.llm_speed_model or "llama3.2:1b",
    "BALANCED": settings.llm_balanced_model or "llama3.2:1b",
    "ACCURACY": settings.llm_accuracy_model or "llama3.2:1b",
}


class LLMConnectorClient:
    def __init__(self, tier: str = "BALANCED"):
        self.tier = tier.upper()
        self.model = MODEL_TIER_MAP.get(self.tier, MODEL_TIER_MAP["BALANCED"])

    def get_model_name(self) -> str:
        return self.model

    def generate(self, prompt: str, max_tokens: int = 400) -> Dict[str, Any]:
        """Generate text by calling ollama run. Uses subprocess to keep dependency minimal."""
        model = self.get_model_name()
        try:
            logger.info("llm.generate.start", model=model, tier=self.tier)
            # Use ollama CLI for now
            cmd = [
                "ollama",
                "run",
                model,
                prompt,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode != 0:
                logger.error("llm.generate.error", model=model, stderr=result.stderr.strip(), stdout=result.stdout.strip())
                return {"success": False, "error": result.stderr.strip() or "LLM call failed"}

            text = result.stdout.strip()
            logger.info("llm.generate.complete", model=model, token_count=len(text), response_snippet=text[:100])
            return {"success": True, "model": model, "response": text, "raw": {"stdout": result.stdout, "stderr": result.stderr}}

        except subprocess.TimeoutExpired as exc:
            logger.error("llm.generate.timeout", model=model, error=str(exc))
            return {"success": False, "error": "LLM request timed out"}
        except Exception as exc:
            logger.exception("llm.generate.exception", error=str(exc))
            return {"success": False, "error": str(exc)}


def llm_generate_response(
    intent: str,
    conversation: str,
    tool_results: Dict[str, Any],
    params: Dict[str, Any],
    context: str = "",
    speed_tier: str = "BALANCED",
) -> str:
    client = LLMConnectorClient(speed_tier)
    prompt_lines = [
        f"Intent: {intent}",
        "You are a customer support assistant. Use the tool results and context to answer the user clearly.",
        "User conversation:",
        conversation,
        "",
        "Tool results:",
        json.dumps(tool_results, indent=2, ensure_ascii=False),
        "",
        "Extracted parameters:",
        json.dumps(params, indent=2, ensure_ascii=False),
    ]
    if context:
        prompt_lines.extend(["", "Retrieved knowledge:", context])
    prompt_lines.append(""" \
        You are customer support assistant. \
        Carefully use the tool results to answer the user's query." \
        Apologize for incorrect or incomplete information in the system conversation- [I apologize for any confusion. Answer from the tool_response]" \
        If you find the conversation to be confusing, ask the user for clarification in a polite way." \
        If you don't have enough information to answer, say 'I will transfer you to a human agent for further assistance. Please wait while I connect you.' and set escalation_required to true in the response.
    """)
    prompt = "\n".join(prompt_lines)

    result = client.generate(prompt)
    if result.get("success"):
        return result.get("response", "I have processed your request.")

    # fallback
    fallback = tool_results.get("check_order", {}).get("order", {})
    if intent == "order_status" and fallback:
        return f"Your order {fallback.get('order_id')} is currently {fallback.get('status', 'Unknown')}."

    return "I have processed your request. Please let me know if you need anything else."
