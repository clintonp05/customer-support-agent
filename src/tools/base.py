import time
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.observability.tracer import trace_tool_call


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, recovery_s: int = 30):
        self.name = name
        self.failures = 0
        self.threshold = threshold
        self.recovery_s = recovery_s
        self.state = "CLOSED"
        self.last_failure: Optional[float] = None

    def can_execute(self) -> bool:
        if self.state == "OPEN":
            if self.last_failure and (time.time() - self.last_failure > self.recovery_s):
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.threshold:
            self.state = "OPEN"


class BaseTool(ABC):
    name: str
    circuit_breaker: CircuitBreaker

    def __init__(self, name: str, circuit_threshold: int = 5, circuit_recovery_s: int = 30):
        self.name = name
        self.circuit_breaker = CircuitBreaker(
            name=name,
            threshold=circuit_threshold,
            recovery_s=circuit_recovery_s
        )

    @retry(
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2)
    )
    async def execute(self, params: dict, state: dict) -> dict:
        if not self.circuit_breaker.can_execute():
            raise CircuitOpenError(f"{self.name} circuit is OPEN")

        try:
            start = time.time()
            result = await self._call(params, state)
            elapsed = (time.time() - start) * 1000

            self.circuit_breaker.record_success()
            await trace_tool_call(self.name, params, result, elapsed)

            return self._validate_result(result)

        except Exception as e:
            self.circuit_breaker.record_failure()
            raise

    @abstractmethod
    async def _call(self, params: dict, state: dict) -> dict:
        """Implement the actual tool logic"""
        pass

    def _validate_result(self, result: dict) -> dict:
        """Override to add result-specific validation"""
        return result