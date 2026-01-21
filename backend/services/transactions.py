"""
ED-BASE Transaction Service
ACID transaction management with isolation level control.

Invariant #7: Partial failures never corrupt persistent state.
Invariant #8: Payments are either fully applied or rolled back.

WHY isolation levels: Different operations need different guarantees.
Payments need SERIALIZABLE to prevent double-spend.
"""

import contextlib
from datetime import datetime, timezone
from typing import Generator, Optional, Callable, Any
from enum import Enum
import time
import structlog

from utils import get_connection, DatabaseError, SerializationError
from config import get_config

logger = structlog.get_logger(__name__)


class IsolationLevel(Enum):
    """PostgreSQL transaction isolation levels per PRD §10."""
    
    # WHY for payments: Strictest isolation, prevents phantom reads
    # and all anomalies. Required for financial operations (Invariant #8)
    SERIALIZABLE = "SERIALIZABLE"
    
    # WHY for user updates: Prevents non-repeatable reads
    # Good balance of consistency and performance
    REPEATABLE_READ = "REPEATABLE READ"
    
    # WHY for audit logs: Sufficient for append-only operations
    # Best performance, each statement sees committed data
    READ_COMMITTED = "READ COMMITTED"


# Default retry configuration for serialization conflicts
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_MS = 100
DEFAULT_RETRY_BACKOFF = 2.0


class TransactionError(Exception):
    """Base exception for transaction errors."""
    pass


class TransactionAborted(TransactionError):
    """Raised when transaction is explicitly aborted."""
    pass


class MaxRetriesExceeded(TransactionError):
    """Raised when retries exhausted for serialization conflicts."""
    pass


@contextlib.contextmanager
def transaction(
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED,
    timeout: Optional[int] = None,
    readonly: bool = False
) -> Generator:
    """
    Context manager for database transactions.
    
    WHY context manager: Guarantees commit or rollback, even on exception.
    
    Args:
        isolation_level: Transaction isolation level
        timeout: Optional query timeout override
        readonly: If True, marks transaction as read-only
        
    Yields:
        Database cursor
        
    Raises:
        TransactionError: If transaction fails
        SerializationError: For serialization conflicts (retry recommended)
    """
    config = get_config().database
    timeout = timeout or config.default_timeout
    
    with get_connection(timeout) as conn:
        # Disable autocommit for explicit transaction control
        conn.autocommit = False
        
        try:
            with conn.cursor() as cur:
                # Set isolation level
                cur.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level.value}")
                
                if readonly:
                    cur.execute("SET TRANSACTION READ ONLY")
                
                logger.debug(
                    "Transaction started",
                    isolation=isolation_level.value,
                    readonly=readonly
                )
                
                yield cur
            
            # Commit if no exception
            conn.commit()
            logger.debug("Transaction committed")
            
        except SerializationError:
            # Don't catch - let it propagate for retry handling
            conn.rollback()
            raise
            
        except Exception as e:
            # Rollback on any error (Invariant #7)
            conn.rollback()
            logger.warning("Transaction rolled back", error=str(e))
            raise


@contextlib.contextmanager
def payment_transaction(timeout: Optional[int] = None) -> Generator:
    """
    Transaction context for payment operations.
    
    WHY separate function: Payments are critical, need maximum protection.
    Uses SERIALIZABLE and shorter timeout (fail fast).
    
    Args:
        timeout: Query timeout (default 10s per PRD §14)
        
    Yields:
        Database cursor
    """
    config = get_config().database
    timeout = timeout or config.payment_timeout
    
    with transaction(
        isolation_level=IsolationLevel.SERIALIZABLE,
        timeout=timeout
    ) as cur:
        yield cur


@contextlib.contextmanager
def audit_transaction() -> Generator:
    """
    Transaction context for audit log operations.
    
    Uses READ COMMITTED - sufficient for append-only writes.
    
    Yields:
        Database cursor
    """
    with transaction(isolation_level=IsolationLevel.READ_COMMITTED) as cur:
        yield cur


def with_retry(
    func: Callable[[], Any],
    max_retries: int = DEFAULT_MAX_RETRIES,
    delay_ms: int = DEFAULT_RETRY_DELAY_MS,
    backoff: float = DEFAULT_RETRY_BACKOFF
) -> Any:
    """
    Execute function with retry on serialization conflicts.
    
    WHY retry: Serialization conflicts are expected under high concurrency.
    They're not errors - they mean the DB prevented a conflict.
    Retry with backoff usually succeeds.
    
    Args:
        func: Function to execute (should use transaction context)
        max_retries: Maximum retry attempts
        delay_ms: Initial delay between retries
        backoff: Backoff multiplier for each retry
        
    Returns:
        Function result
        
    Raises:
        MaxRetriesExceeded: If all retries fail
    """
    last_error = None
    delay = delay_ms / 1000.0  # Convert to seconds
    
    for attempt in range(max_retries + 1):
        try:
            return func()
            
        except SerializationError as e:
            last_error = e
            
            if attempt < max_retries:
                logger.info(
                    "Serialization conflict, retrying",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay_ms=int(delay * 1000)
                )
                time.sleep(delay)
                delay *= backoff
            else:
                logger.warning(
                    "Max retries exceeded for serialization conflict",
                    attempts=max_retries + 1
                )
    
    raise MaxRetriesExceeded(
        f"Transaction failed after {max_retries + 1} attempts: {last_error}"
    )


def execute_transactional(
    isolation_level: IsolationLevel,
    func: Callable[[Any], Any],
    max_retries: int = DEFAULT_MAX_RETRIES
) -> Any:
    """
    Execute a function within a transaction with retry handling.
    
    Convenience wrapper combining transaction and retry.
    
    Args:
        isolation_level: Transaction isolation level
        func: Function taking cursor, returns result
        max_retries: Maximum retry attempts
        
    Returns:
        Function result
    """
    def wrapped():
        with transaction(isolation_level=isolation_level) as cur:
            return func(cur)
    
    return with_retry(wrapped, max_retries=max_retries)


class TransactionContext:
    """
    Transaction context with savepoint support.
    
    WHY savepoints: Enable partial rollback within a transaction.
    Useful for complex operations where some failures are recoverable.
    """
    
    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED,
        timeout: Optional[int] = None
    ):
        self.isolation_level = isolation_level
        self.timeout = timeout
        self._conn = None
        self._cursor = None
        self._savepoint_counter = 0
    
    def __enter__(self):
        config = get_config().database
        timeout = self.timeout or config.default_timeout
        
        # Get connection from pool
        from utils.database import _connection_pool
        if _connection_pool is None:
            raise DatabaseError("Connection pool not initialized")
        
        self._conn = _connection_pool.getconn()
        self._conn.autocommit = False
        
        self._cursor = self._conn.cursor()
        self._cursor.execute(
            f"SET TRANSACTION ISOLATION LEVEL {self.isolation_level.value}"
        )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._conn.rollback()
                logger.warning("Transaction rolled back", error=str(exc_val))
            else:
                self._conn.commit()
        finally:
            if self._cursor:
                self._cursor.close()
            if self._conn:
                from utils.database import _connection_pool
                _connection_pool.putconn(self._conn)
        
        return False
    
    @property
    def cursor(self):
        """Get the transaction cursor."""
        return self._cursor
    
    @contextlib.contextmanager
    def savepoint(self, name: Optional[str] = None):
        """
        Create a savepoint within the transaction.
        
        WHY savepoint: Allows partial rollback without aborting
        the entire transaction.
        
        Args:
            name: Optional savepoint name (auto-generated if not provided)
            
        Yields:
            Savepoint name
        """
        if name is None:
            self._savepoint_counter += 1
            name = f"sp_{self._savepoint_counter}"
        
        self._cursor.execute(f"SAVEPOINT {name}")
        
        try:
            yield name
        except Exception as e:
            self._cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")
            raise
        else:
            self._cursor.execute(f"RELEASE SAVEPOINT {name}")
    
    def abort(self, reason: str = "Explicitly aborted"):
        """
        Abort the transaction explicitly.
        
        Use when business logic determines transaction should not commit.
        """
        raise TransactionAborted(reason)
