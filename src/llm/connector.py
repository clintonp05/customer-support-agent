"""LLM connector client for routing by speed/accuracy tiers."""
import subprocess
import json
import time
from typing import Dict, Any, AsyncGenerator, List, Optional

from src.config import settings
from src.observability.logger import get_logger
from src.observability.metrics_exporter import record_llm_tokens

logger = get_logger()
ANTHROPIC_BACKOFF_S = 300
_anthropic_blocked_until = 0.0

try:
    import anthropic  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    logger.warning("anthropic_sdk_not_available", error="Anthropic SDK not installed. Install with `pip install anthropic` to enable Anthropic support.")
    anthropic = None
try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    logger.warning("gemini_sdk_not_available", error="google-generativeai SDK not installed. Install with `pip install google-generativeai` to enable Gemini support.")
    genai = None

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

    def _should_use_anthropic(self) -> bool:
        global _anthropic_blocked_until
        if not settings.anthropic_api_key:
            return False
        if time.time() < _anthropic_blocked_until:
            if self._anthropic_health_check():
                _anthropic_blocked_until = 0.0
                logger.info("llm.generate.anthropic_reopened")
            else:
                return False
        return True

    def _anthropic_health_check(self) -> bool:
        if anthropic is None or not settings.anthropic_api_key:
            return False
        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            result = client.messages.create(
                model=self.get_model_name(),
                max_tokens=1,
                messages=[{"role": "user", "content": "healthcheck"}],
            )
            return bool(getattr(result, "content", None))
        except Exception as exc:
            logger.warning("llm.generate.anthropic_health_failed", error=str(exc))
            return False

    def _generate_anthropic(self, prompt: str, max_tokens: int, model: str, system: str = "") -> Dict[str, Any]:
        if anthropic is None:
            return {"success": False, "error": "anthropic SDK not installed"}
        logger.info("llm.generate.anthropic_start", model=model)
        logger.debug("llm.generate.anthropic_prompt", prompt=prompt, max_tokens=max_tokens, has_system=bool(system))
        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            result = client.messages.create(**kwargs)
            content = getattr(result, "content", "")
            logger.debug("llm.generate.anthropic_response", response=content, raw_response=str(result))
            if isinstance(content, list):
                text = "".join([getattr(block, "text", str(block)) for block in content]).strip()
            else:
                text = str(content).strip()
            status_code = getattr(content, "status_code", None)
            transient_codes = {400, 408, 429, 500, 502, 503, 504}
            transient = status_code in transient_codes if status_code is not None else False
            if transient:
                return {
                    "success": False,
                    "error": str(result["error"]["message"]) if isinstance(result, dict) and "error" in result else "Transient error from Anthropic",
                    "status_code": status_code,
                    "transient": transient,
                }
            usage = getattr(result, "usage", None)
            if usage:
                record_llm_tokens(model, "input", getattr(usage, "input_tokens", 0))
                record_llm_tokens(model, "output", getattr(usage, "output_tokens", 0))
            return {
                "success": True,
                "model": model,
                "response": text,
                "raw": {
                    "provider": "anthropic",
                    "id": getattr(result, "id", None),
                    "model": getattr(result, "model", None),
                    "stop_reason": getattr(result, "stop_reason", None),
                },
            }
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            transient_codes = {408, 429, 500, 502, 503, 504}
            transient = status_code in transient_codes if status_code is not None else False
            if transient is False:
                global _anthropic_blocked_until
                _anthropic_blocked_until = time.time() + ANTHROPIC_BACKOFF_S
            return {
                "success": False,
                "error": str(exc),
                "status_code": status_code,
                "transient": transient,
            }

    async def _stream_generate_anthropic(
        self, prompt: str, max_tokens: int, model: str, system: str = ""
    ) -> AsyncGenerator[str, None]:
        """Stream text deltas from Anthropic using the async client."""
        if anthropic is None:
            yield ""
            return
        async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        try:
            async with async_client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            logger.warning("llm.stream.anthropic_failed", error=str(exc))
            return

    async def stream_generate(
        self, prompt: str, max_tokens: int = 400, system: str = ""
    ) -> AsyncGenerator[str, None]:
        """Stream tokens; falls back to single-shot emit for non-Anthropic providers."""
        model = self.get_model_name()
        if self._should_use_anthropic():
            logger.info("llm.stream.start", model=model, tier=self.tier)
            async for chunk in self._stream_generate_anthropic(prompt, max_tokens, model, system):
                yield chunk
            return

        # Gemini / Ollama: run blocking call then emit whole response as one chunk
        result = self.generate(prompt, max_tokens=max_tokens, system=system)
        text = result.get("response", "") if result.get("success") else ""
        if text:
            yield text

    def _should_use_gemini(self) -> bool:
        return bool(settings.gemini_api_key)

    def _resolve_gemini_model(self, model: str) -> str:
        return model if model.startswith("gemini") else "gemini-3.1-flash-lite-preview"

    def _generate_gemini(self, prompt: str, model: str) -> Dict[str, Any]:
        if genai is None:
            return {"success": False, "error": "google-generativeai SDK not installed"}
        logger.info("llm.generate.gemini_start", model=model)
        genai.configure(api_key=settings.gemini_api_key)
        resolved_model = self._resolve_gemini_model(model)
        gemini_model = genai.GenerativeModel(resolved_model)
        result = gemini_model.generate_content(prompt)
        text = getattr(result, "text", "")
        return {
            "success": True,
            "model": resolved_model,
            "response": (text or "").strip(),
            "raw": {
                "provider": "gemini",
                "model": resolved_model,
            },
        }

    def generate(self, prompt: str, max_tokens: int = 400, system: str = "") -> Dict[str, Any]:
        """Generate text by calling Anthropic (if configured), then Gemini, else ollama run."""
        model = self.get_model_name()
        try:
            start = time.perf_counter()
            logger.info("llm.generate.start", model=model, tier=self.tier, is_anthropic=self._should_use_anthropic(), is_gemini=self._should_use_gemini())
            if self._should_use_anthropic():
                result = self._generate_anthropic(prompt, max_tokens, model, system=system)
                if not result.get("success"):
                    logger.warning(
                        "llm.generate.anthropic_failed",
                        model=model,
                        error=result.get("error", "anthropic failed"),
                        status_code=result.get("status_code"),
                        transient=result.get("transient"),
                    )
                else:
                    result["elapsed_ms"] = (time.perf_counter() - start) * 1000
                    logger.info("llm.generate.complete", model=model, token_count=len(result.get("response", "")))
                    return result
            elif settings.anthropic_api_key:
                logger.info("llm.generate.anthropic_skipped", model=model, reason="backoff_active")

            if self._should_use_gemini():
                result = self._generate_gemini(prompt, model)
                if not result.get("success"):
                    logger.warning("llm.generate.gemini_failed", model=model, error=result.get("error", "gemini failed"))
                else:
                    result["elapsed_ms"] = (time.perf_counter() - start) * 1000
                    logger.info("llm.generate.complete", model=result.get("model", model), token_count=len(result.get("response", "")))
                    return result

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
            return {"success": True, "model": model, "response": text, "raw": {"stdout": result.stdout, "stderr": result.stderr}, "elapsed_ms": (time.perf_counter() - start) * 1000}

        except subprocess.TimeoutExpired as exc:
            logger.error("llm.generate.timeout", model=model, error=str(exc))
            return {"success": False, "error": "LLM request timed out"}
        except Exception as exc:
            logger.exception("llm.generate.exception", error=str(exc))
            return {"success": False, "error": str(exc)}


_SYSTEM_PROMPT = """\
You are a professional customer support assistant for Noon, a leading Middle Eastern e-commerce platform.

Rules you must always follow:
- Respond in the same language the customer is using (English or Arabic).
- All amounts are in AED (UAE Dirham). Never use USD or the $ symbol.
- Be concise, empathetic, and accurate. Do not pad your reply with unnecessary filler.
- Use ONLY the tool results provided. Never fabricate order details, prices, statuses, or dates.
- Payment method "cod" means Cash on Delivery — the customer pays upon receipt, not in advance.
  If payment status is "pending" it means no payment has been collected yet.
- If the customer's claim contradicts the tool results, politely clarify using the actual data.
- If you cannot resolve the issue, offer: "I'll connect you with a human agent for further assistance."
- Do not repeat the question back to the customer verbatim.
"""

_INTENT_GUIDANCE: Dict[str, str] = {
    "order_status": (
        "Report the current order status and total in AED. "
        "If the customer asks about payment, explain the payment method and its status."
    ),
    "delivery_tracking": (
        "Provide delivery status, current location, estimated arrival, and carrier if available."
    ),
    "refund_request": (
        "Check whether a refund was initiated. If yes, share the refund ID and timeline. "
        "If not eligible, explain why and offer to escalate."
    ),
    "warranty_claim": (
        "Summarise the warranty claim outcome. If a claim was started, give the claim ID and next steps."
    ),
    "product_inquiry": (
        "Provide the product details requested. Include availability, price in AED, and key specs."
    ),
    "general_inquiry": (
        "Answer the customer's question using the policy/knowledge context provided. "
        "Cite the relevant policy where applicable."
    ),
}


def _build_system_prompt(primary_intent: str, detected_intents: Optional[List[str]] = None) -> str:
    """Build system prompt with guidance for all detected intents.

    For multi-intent queries, every detected intent's guidance is included so
    the model addresses the full scope of the customer's question in one reply.
    """
    system = _SYSTEM_PROMPT
    intents_for_guidance = detected_intents if detected_intents else [primary_intent]

    if len(intents_for_guidance) == 1:
        hint = _INTENT_GUIDANCE.get(intents_for_guidance[0], "")
        if hint:
            system += f"\nFor this request (intent: {intents_for_guidance[0]}):\n{hint}"
    else:
        hints = []
        for intent in intents_for_guidance:
            hint = _INTENT_GUIDANCE.get(intent, "")
            if hint:
                hints.append(f"- [{intent}]: {hint}")
        if hints:
            system += (
                "\nThis customer has asked about multiple topics. "
                "Address EACH one in your response:\n" + "\n".join(hints)
            )
    return system


def _build_user_message(
    intent: str,
    conversation: str,
    tool_results: Dict[str, Any],
    params: Dict[str, Any],
    context: str,
    detected_intents: Optional[List[str]] = None,
) -> str:
    """Build the structured user message for the LLM."""
    intents_label = (
        ", ".join(detected_intents) if detected_intents and len(detected_intents) > 1 else intent
    )
    user_lines = [
        "=== Conversation history ===",
        conversation,
        "",
        f"=== System data (intents: {intents_label}) ===",
        json.dumps(tool_results, indent=2, ensure_ascii=False),
        "",
        "=== Extracted parameters ===",
        json.dumps(params, indent=2, ensure_ascii=False),
    ]
    if context:
        user_lines.extend(["", "=== Policy / knowledge context ===", context])
    user_lines.extend([
        "",
        "Based on the data above, respond to the customer's latest message.",
        "Use only the data provided. Do not invent information.",
    ])
    return "\n".join(user_lines)


def llm_generate_response(
    intent: str,
    conversation: str,
    tool_results: Dict[str, Any],
    params: Dict[str, Any],
    context: str = "",
    speed_tier: str = "BALANCED",
    return_meta: bool = False,
    detected_intents: Optional[List[str]] = None,
    system_override: Optional[str] = None,
) -> Dict[str, Any]:
    client = LLMConnectorClient(speed_tier)
    system = system_override if system_override else _build_system_prompt(intent, detected_intents)
    user_message = _build_user_message(intent, conversation, tool_results, params, context, detected_intents)

    result = client.generate(user_message, system=system)
    if result.get("success"):
        payload = {"response": result.get("response", "I have processed your request."), "elapsed_ms": result.get("elapsed_ms")}
        return payload if return_meta else payload

    # Fallback when LLM call fails
    fallback_order = tool_results.get("check_order", {}).get("order", {})
    if intent == "order_status" and fallback_order:
        total = fallback_order.get("total_aed", "N/A")
        return {
            "response": (
                f"Your order {fallback_order.get('order_id')} is currently "
                f"{fallback_order.get('status', 'Unknown')}. Total: {total} AED"
            ),
            "elapsed_ms": None,
        }

    return {"response": "I have processed your request. Please let me know if you need anything else.", "elapsed_ms": None}


async def llm_stream_generate_response(
    intent: str,
    conversation: str,
    tool_results: Dict[str, Any],
    params: Dict[str, Any],
    context: str = "",
    speed_tier: str = "BALANCED",
    detected_intents: Optional[List[str]] = None,
    system_override: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Streaming counterpart to llm_generate_response — yields text chunks as they arrive.

    detected_intents: when set, multi-intent guidance is included in the system prompt
    so the model addresses every topic the customer raised.
    system_override: when set, replaces the default system prompt entirely.
    """
    client = LLMConnectorClient(speed_tier)
    system = system_override if system_override else _build_system_prompt(intent, detected_intents)
    user_message = _build_user_message(intent, conversation, tool_results, params, context, detected_intents)

    async for chunk in client.stream_generate(user_message, system=system):
        yield chunk
