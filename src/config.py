import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.example", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    default_model: str = Field(default="claude-sonnet-4-20250514", alias="DEFAULT_MODEL")
    fast_model: str = Field(default="claude-haiku-4-5-20251001", alias="FAST_MODEL")

    # Database
    database_url: str = Field(default="postgresql://clinton@localhost:5432/noon_agent", alias="DATABASE_URL")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    redis_query_ttl_s: int = Field(default=86400, alias="REDIS_QUERY_TTL_S")
    grafana_url: str = Field(default="", alias="GRAFANA_URL")

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection_faq: str = Field(default="noon_faq", alias="QDRANT_COLLECTION_FAQ")
    qdrant_collection_policies: str = Field(default="noon_policies", alias="QDRANT_COLLECTION_POLICIES")

    # LLM / Ollama
    llm_speed_model: str = Field(default="claude-haiku-4-5-20251001", alias="LLM_SPEED_MODEL")
    llm_balanced_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_BALANCED_MODEL")
    llm_accuracy_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_ACCURACY_MODEL")

    # Langfuse
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")

    # Agent config
    intent_confidence_threshold: float = Field(default=0.80, alias="INTENT_CONFIDENCE_THRESHOLD")
    max_conversation_turn_ms: int = Field(default=8000, alias="MAX_CONVERSATION_TURN_MS")
    tool_retry_max_attempts: int = Field(default=2, alias="TOOL_RETRY_MAX_ATTEMPTS")
    circuit_breaker_threshold: int = Field(default=5, alias="CIRCUIT_BREAKER_THRESHOLD")
    circuit_breaker_recovery_s: int = Field(default=30, alias="CIRCUIT_BREAKER_RECOVERY_S")
    prompt_cache_ttl_s: int = Field(default=300, alias="PROMPT_CACHE_TTL_S")

    # Eval
    eval_tool_accuracy_min: float = Field(default=0.90, alias="EVAL_TOOL_ACCURACY_MIN")
    eval_param_accuracy_min: float = Field(default=0.95, alias="EVAL_PARAM_ACCURACY_MIN")
    eval_goal_success_min: float = Field(default=0.85, alias="EVAL_GOAL_SUCCESS_MIN")
    eval_hallucination_max: float = Field(default=0.02, alias="EVAL_HALLUCINATION_MAX")

    # Cost targets
    target_cost_per_ticket_usd: float = Field(default=0.05, alias="TARGET_COST_PER_TICKET_USD")


settings = Settings()
