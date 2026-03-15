"""Infra health checks after startup."""
import asyncio
import json
import subprocess
import urllib.request
from typing import Dict, Any

from src.config import settings
from src.db.connector import get_db_cursor
from src.cache.redis_client import get_redis_client
from src.llm.connector import LLMConnectorClient
from src.observability.logger import get_logger

logger = get_logger()


def _http_get(url: str, timeout_s: int = 5) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "body": body[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_db() -> Dict[str, Any]:
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
        return {"ok": True, "result": row}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_redis() -> Dict[str, Any]:
    client = get_redis_client()
    if client is None:
        return {"ok": False, "error": "redis-py not available"}
    try:
        return {"ok": True, "result": client.ping()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_qdrant() -> Dict[str, Any]:
    url = settings.qdrant_url.rstrip("/")
    if not url:
        return {"ok": False, "error": "qdrant_url not set"}
    return _http_get(f"{url}/collections")


def _check_grafana() -> Dict[str, Any]:
    if not settings.grafana_url:
        return {"ok": False, "error": "grafana_url not set"}
    url = settings.grafana_url.rstrip("/")
    return _http_get(f"{url}/api/health")


def _check_llm() -> Dict[str, Any]:
    client = LLMConnectorClient("SPEED")
    try:
        result = client.generate("healthcheck", max_tokens=1)
        return {"ok": result.get("success", False), "provider": result.get("raw", {}).get("provider"), "error": result.get("error")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_health_checks() -> Dict[str, Any]:
    results = {
        "db": _check_db(),
        "redis": _check_redis(),
        "qdrant": _check_qdrant(),
        "grafana": _check_grafana(),
        "llm": _check_llm(),
    }
    logger.info("infra.health.results", results=results)
    return results


async def run_health_checks_async() -> Dict[str, Any]:
    return await asyncio.to_thread(run_health_checks)
