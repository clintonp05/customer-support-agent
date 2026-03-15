"""Langfuse trace wrapper for observability"""
import time
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from src.observability.logger import get_logger
from src.config import settings


class LangfuseTracer:
    """Wrapper for Langfuse tracing"""

    def __init__(self):
        self.client = None
        logger = get_logger()
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                from langfuse import Langfuse
                self.client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
            except ImportError:
                
                logger.warning("langfuse_sdk_not_available", error="Langfuse SDK not installed")
                self.client = None


    @asynccontextmanager
    async def trace(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        """Async context manager for tracing."""
        class MockTrace:
            def span(self, name: str, **kwargs):
                return self

            def log(self, **kwargs):
                return None

            def set_status(self, status: str):
                return None

        trace_obj = None
        if self.client and hasattr(self.client, "start_as_current_observation"):
            try:
                trace_obj = self.client.start_as_current_observation(
                    name=name,
                    metadata=metadata or {},
                    as_type="span",
                )
            except Exception as exc:
                logger = get_logger()
                logger.warning("langfuse_trace_failed", error=str(exc))
                trace_obj = MockTrace()
        else:
            trace_obj = MockTrace()

        try:
            if hasattr(trace_obj, "__enter__"):
                with trace_obj as trace:
                    yield trace
            else:
                yield trace_obj
        finally:
            return


# Singleton
_tracer = None


def get_tracer() -> LangfuseTracer:
    """Get or create the tracer"""
    global _tracer
    if _tracer is None:
        _tracer = LangfuseTracer()
    return _tracer


def trace_node(node_name: str):
    """Decorator for tracing LangGraph nodes"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            metadata = {
                "node": node_name,
                "conversation_id": args[0].get("conversation_id") if args else None,
            }
            start = time.time()
            async with tracer.trace(node_name, metadata=metadata) as trace:
                result = await func(*args, **kwargs)
            elapsed_ms = (time.time() - start) * 1000
            if hasattr(trace, "log"):
                trace.log(latency_ms=elapsed_ms)
            return result
        return wrapper
    return decorator


async def trace_tool_call(tool_name: str, params: dict, result: dict, elapsed_ms: float):
    """Trace tool execution"""
    tracer = get_tracer()
    metadata = {
        "tool_name": tool_name,
        "elapsed_ms": elapsed_ms,
        "success": result.get("success", False),
    }
    async with tracer.trace(f"tool_call.{tool_name}", metadata=metadata):
        pass
