"""Prompt hub client for Langfuse + cache"""
import time
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
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
        self.langfuse = None
        self._cache: Dict[str, CachedPrompt] = {}
        self._local_dir = Path("src/prompts")

        # Initialize Langfuse if credentials available
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                from langfuse import Langfuse
                self.langfuse = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host
                )
            except ImportError:
                pass

    def warm_cache(self):
        """Call at application startup"""
        for name in self.CRITICAL_PROMPTS:
            try:
                self._fetch_and_cache(name)
            except Exception as e:
                print(f"[PromptHub] WARNING: Could not warm {name}: {e}")

    def get(self, prompt_name: str, label: str = "production", **variables) -> str:
        """Get a prompt with variable substitution"""
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
        """Fetch from Langfuse and cache"""
        if not self.langfuse:
            raise RuntimeError("Langfuse not initialized")

        prompt = self.langfuse.get_prompt(name, label=label)
        template = prompt.prompt
        self._cache[name] = CachedPrompt(template, ttl=settings.prompt_cache_ttl_s)
        return template

    def _load_local(self, name: str) -> str:
        """Local fallback - reads from prompts/ directory"""
        path = self._local_dir / f"{name.replace('-', '_')}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")

        fallback_prompts = {
            "param_request": "To help with your {intent} request, I need: {missing_params}.",
            "output_safety_guard": "Review output for safety.",
            "intent-classifier": "Classify intent from user query.",
        }
        if name in fallback_prompts:
            return fallback_prompts[name]

        raise FileNotFoundError(f"No local prompt found for: {name}")


# Singleton
_prompt_hub = None


def get_prompt_hub() -> PromptHubClient:
    """Get or create the prompt hub"""
    global _prompt_hub
    if _prompt_hub is None:
        _prompt_hub = PromptHubClient()
    return _prompt_hub