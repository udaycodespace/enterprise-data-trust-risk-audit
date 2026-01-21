"""
ED-BASE Database Utilities
Connection pooling, query execution, and database helpers.

WHY centralized DB access: Consistent timeout handling,
circuit breaker integration, and proper cleanup.
"""

import contextlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Generator
import psycopg2
from psycopg2 import pool, sql, errors
from psycopg2.extras import RealDictCursor
import structlog

from config import get_config, DatabaseConfig

logger = structlog.get_logger(__name__)

# Module-level connection pool (singleton pattern)
_connection_pool: Optional[pool.ThreadedConnectionPool] = None


class DatabaseError(Exception):
    """Base exception for database operations."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    pass


class QueryTimeoutError(DatabaseError):
    """Raised when query exceeds timeout."""
    pass


class SerializationError(DatabaseError):
    """Raised on serialization conflicts (retry recommended)."""
    pass


def init_connection_pool(config: Optional[DatabaseConfig] = None) -> None:
    """
    Initialize the database connection pool.
    
    WHY ThreadedConnectionPool: Safe for multi-threaded Flask apps.
    WHY pool: Reuse connections instead of creating new ones per request.
    
    Must be called once during application startup.
    """
    global _connection_pool
    
    if config is None:
        config = get_config().database
    
    if _connection_pool is not None:
        logger.warning("Connection pool already initialized, skipping")
        return
    
    try:
        # WHY these pool settings: Per PRD §14
        # min=5: Always have connections ready
        # max=20: Prevent connection exhaustion
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=config.pool_min,
            maxconn=config.pool_max,
            dsn=config.url,
            # WHY cursor_factory: Return dicts instead of tuples for clarity
            cursor_factory=RealDictCursor,
            # WHY connect_timeout: Fail fast if DB unreachable
            connect_timeout=5,
            # WHY application_name: Identify connections in pg_stat_activity
            options=f"-c application_name=ed-base"
        )
        logger.info("Database connection pool initialized", 
                   min_conn=config.pool_min, 
                   max_conn=config.pool_max)
    except psycopg2.Error as e:
        logger.error("Failed to initialize connection pool", error=str(e))
        raise DatabaseConnectionError(f"Failed to initialize pool: {e}")


def close_connection_pool() -> None:
    """
    Close all connections in the pool.
    Call during application shutdown.
    """
    global _connection_pool
    
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Database connection pool closed")


@contextlib.contextmanager
def get_connection(timeout: Optional[int] = None) -> Generator:
    """
    Get a database connection from the pool.
    
    WHY context manager: Guarantees connection is returned to pool,
    even if exception occurs.
    
    Args:
        timeout: Query timeout in seconds (default from config)
        
    Yields:
        Database connection
        
    Raises:
        DatabaseConnectionError: If pool not initialized or connection fails
    """
    if _connection_pool is None:
        raise DatabaseConnectionError("Connection pool not initialized")
    
    config = get_config().database
    timeout = timeout or config.default_timeout
    
    conn = None
    try:
        conn = _connection_pool.getconn()
        if conn is None:
            raise DatabaseConnectionError("Failed to get connection from pool")
        
        # WHY set statement_timeout per connection: Different operations
        # have different timeout requirements (PRD §14)
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = '{timeout * 1000}'")
        
        yield conn
        
    except pool.PoolError as e:
        logger.error("Pool error", error=str(e))
        raise DatabaseConnectionError(f"Pool error: {e}")
    finally:
        if conn is not None:
            _connection_pool.putconn(conn)


@contextlib.contextmanager
def get_cursor(
    timeout: Optional[int] = None,
    autocommit: bool = False
) -> Generator:
    """
    Get a database cursor with automatic connection handling.
    
    WHY separate cursor context: Most operations just need a cursor,
    not direct connection access.
    
    Args:
        timeout: Query timeout in seconds
        autocommit: If True, each statement commits immediately
        
    Yields:
        Database cursor (RealDictCursor)
    """
    with get_connection(timeout) as conn:
        conn.autocommit = autocommit
        with conn.cursor() as cur:
            yield cur
        if not autocommit:
            conn.commit()


def execute_query(
    query: str,
    params: Optional[tuple] = None,
    timeout: Optional[int] = None,
    fetch_one: bool = False,
    fetch_all: bool = True
) -> Optional[list | dict]:
    """
    Execute a query and return results.
    
    WHY wrapper function: Consistent error handling and logging.
    
    Args:
        query: SQL query string
        params: Query parameters (for parameterized queries)
        timeout: Query timeout
        fetch_one: Return single row
        fetch_all: Return all rows (default)
        
    Returns:
        Query results or None for non-SELECT queries
        
    Raises:
        QueryTimeoutError: If query times out
        DatabaseError: For other database errors
    """
    try:
        with get_cursor(timeout) as cur:
            cur.execute(query, params)
            
            if cur.description is None:  # Non-SELECT query
                return None
            
            if fetch_one:
                return cur.fetchone()
            if fetch_all:
                return cur.fetchall()
            return None
            
    except errors.QueryCanceled as e:
        logger.warning("Query timeout", query=query[:100])
        raise QueryTimeoutError(f"Query timed out: {e}")
    except errors.SerializationFailure as e:
        logger.warning("Serialization conflict", query=query[:100])
        raise SerializationError(f"Serialization conflict: {e}")
    except psycopg2.Error as e:
        logger.error("Database error", error=str(e), query=query[:100])
        raise DatabaseError(f"Database error: {e}")


def is_within_clock_skew(
    timestamp: datetime,
    tolerance_seconds: int = 300
) -> bool:
    """
    Check if timestamp is within acceptable clock skew.
    
    WHY: Distributed systems have clock drift. PRD §15 requires
    ±5 minute tolerance for webhook validation.
    
    Args:
        timestamp: Timestamp to check
        tolerance_seconds: Allowed skew (default 300 = 5 minutes)
        
    Returns:
        True if timestamp within tolerance of current time
    """
    now = datetime.now(timezone.utc)
    
    # Handle timezone-naive timestamps
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    
    delta = abs((now - timestamp).total_seconds())
    return delta <= tolerance_seconds


def soft_delete(
    table: str,
    id_column: str,
    id_value: Any,
    timeout: Optional[int] = None
) -> bool:
    """
    Soft delete a record by setting deleted_at timestamp.
    
    WHY soft delete per PRD §15: User deleted mid-request should
    not break referential integrity.
    
    Args:
        table: Table name
        id_column: Primary key column name
        id_value: Primary key value
        timeout: Query timeout
        
    Returns:
        True if record was soft deleted
    """
    query = sql.SQL("""
        UPDATE {table}
        SET deleted_at = %s, updated_at = %s
        WHERE {id_col} = %s AND deleted_at IS NULL
    """).format(
        table=sql.Identifier(table),
        id_col=sql.Identifier(id_column)
    )
    
    now = datetime.now(timezone.utc)
    
    try:
        with get_cursor(timeout) as cur:
            cur.execute(query, (now, now, id_value))
            return cur.rowcount > 0
    except psycopg2.Error as e:
        logger.error("Soft delete failed", table=table, id=str(id_value), error=str(e))
        raise DatabaseError(f"Soft delete failed: {e}")


def health_check() -> dict:
    """
    Perform database health check.
    
    Returns:
        Health status dict with is_healthy, latency_ms, and error
    """
    start = datetime.now(timezone.utc)
    
    try:
        # Simple query to verify connectivity
        result = execute_query("SELECT 1 as healthy", timeout=5)
        
        latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return {
            'is_healthy': True,
            'latency_ms': round(latency, 2),
            'error': None
        }
    except Exception as e:
        latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return {
            'is_healthy': False,
            'latency_ms': round(latency, 2),
            'error': str(e)
        }
