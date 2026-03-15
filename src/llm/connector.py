"""LLM connector client for routing by speed/accuracy tiers."""
import subprocess
import json
import time
from typing import Dict, Any

from src.config import settings
from src.observability.logger import get_logger

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

    def _generate_anthropic(self, prompt: str, max_tokens: int, model: str) -> Dict[str, Any]:
        if anthropic is None:
            return {"success": False, "error": "anthropic SDK not installed"}
        logger.info("llm.generate.anthropic_start", model=model)
        logger.debug("llm.generate.anthropic_prompt", prompt=prompt, max_tokens=max_tokens)
        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            result = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
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

    def generate(self, prompt: str, max_tokens: int = 400) -> Dict[str, Any]:
        """Generate text by calling Anthropic (if configured), then Gemini, else ollama run."""
        model = self.get_model_name()
        try:
            start = time.perf_counter()
            logger.info("llm.generate.start", model=model, tier=self.tier, is_anthropic=self._should_use_anthropic(), is_gemini=self._should_use_gemini())
            if self._should_use_anthropic():
                result = self._generate_anthropic(prompt, max_tokens, model)
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


def llm_generate_response(
    intent: str,
    conversation: str,
    tool_results: Dict[str, Any],
    params: Dict[str, Any],
    context: str = "",
    speed_tier: str = "BALANCED",
    return_meta: bool = False,
) -> Dict[str, Any]:
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
    prompt_lines.extend(
        [
            "",
            "Instructions:",
            "1. You are a customer support assistant.",
            "2. Use the tool results and context to answer the user's query clearly and concisely.",
            "3. If tool results contradict the conversation, apologize and answer using tool results.",
            "4. If the conversation is confusing, ask a polite clarification question.",
            "5. If you lack enough information, say: 'I will transfer you to a human agent for further assistance. Please wait while I connect you.'",
        ]
    )
    prompt = "\n".join(prompt_lines)

    result = client.generate(prompt)
    if result.get("success"):
        payload = {"response": result.get("response", "I have processed your request."), "elapsed_ms": result.get("elapsed_ms")}
        return payload if return_meta else payload

    # fallback
    fallback = tool_results.get("check_order", {}).get("order", {})
    if intent == "order_status" and fallback:
        return {"response": f"Your order {fallback.get('order_id')} is currently {fallback.get('status', 'Unknown')}.", "elapsed_ms": None}

    return {"response": "I have processed your request. Please let me know if you need anything else.", "elapsed_ms": None}
