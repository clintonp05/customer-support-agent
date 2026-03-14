"""Redis client helper with safe fallback."""
from typing import Optional

from src.config import settings
from src.observability.logger import get_logger

logger = get_logger()

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

_client: Optional["redis.Redis"] = None


def get_redis_client():
    """Return a Redis client or None if redis-py is unavailable."""
    global _client
    if redis is None:
        logger.warning("redis.unavailable", reason="redis-py not installed")
        return None
    if _client is None:
        try:
            _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.warning("redis.connection_failed", error=str(exc))
            _client = None
    return _client
