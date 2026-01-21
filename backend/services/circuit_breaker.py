"""
ED-BASE Circuit Breaker Service
Fail-fast pattern for external service calls.

Per PRD §14: 5 failures → open (30s), half-open test, fail fast with 503.
"""

import time
from datetime import datetime, timezone
from typing import Optional, Callable, Any
from enum import Enum
from dataclasses import dataclass, field
from threading import Lock
import structlog

from config import get_config

logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast, not calling service
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for external service calls.
    
    WHY circuit breaker: Prevents cascade failures. If a service is down,
    keep failing fast instead of timing out on every request.
    """
    name: str
    failure_threshold: int = 5
    reset_timeout_seconds: int = 30
    half_open_max_calls: int = 1
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    
    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._get_state()
    
    def _get_state(self) -> CircuitState:
        """Get current state, checking for timeout reset."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.reset_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(f"Circuit {self.name} transitioning to HALF_OPEN")
        return self._state
    
    def is_available(self) -> bool:
        """Check if circuit allows calls."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
        return False
    
    def record_success(self) -> None:
        """Record successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info(f"Circuit {self.name} CLOSED after recovery")
            self._failure_count = 0
    
    def record_failure(self) -> None:
        """Record failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit {self.name} OPEN after half-open failure")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit {self.name} OPEN after {self._failure_count} failures")
    
    def call(self, func: Callable[[], Any]) -> Any:
        """Execute function with circuit breaker protection."""
        if not self.is_available():
            raise CircuitOpenError(f"Circuit {self.name} is OPEN")
        
        try:
            result = func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise


class CircuitOpenError(Exception):
    """Raised when circuit is open and blocking calls."""
    pass


# Global circuit breakers for key services
_circuits: dict[str, CircuitBreaker] = {}
_circuits_lock = Lock()


def get_circuit(name: str) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    config = get_config().circuit_breaker
    
    with _circuits_lock:
        if name not in _circuits:
            _circuits[name] = CircuitBreaker(
                name=name,
                failure_threshold=config.failure_threshold,
                reset_timeout_seconds=config.reset_timeout_seconds,
                half_open_max_calls=config.half_open_max_calls
            )
        return _circuits[name]


def with_circuit_breaker(circuit_name: str):
    """Decorator for circuit breaker protection."""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            circuit = get_circuit(circuit_name)
            return circuit.call(lambda: func(*args, **kwargs))
        return wrapper
    return decorator
