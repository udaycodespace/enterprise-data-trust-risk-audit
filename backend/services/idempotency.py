"""
ED-BASE Idempotency Service
Exactly-once execution for state-changing operations.

Invariant #2: A state-changing action executes exactly once.

WHY idempotency: Network failures cause retries. Without idempotency,
retries could duplicate payments, create duplicate records, etc.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import json
import structlog

from utils import (
    get_connection,
    get_cursor,
    generate_request_hash,
    DatabaseError,
)
from config import get_config

logger = structlog.get_logger(__name__)


class IdempotencyStatus(Enum):
    """Status of an idempotency key."""
    PENDING = "pending"      # Locked, processing in progress
    COMPLETED = "completed"  # Done, response cached
    FAILED = "failed"        # Processing failed


@dataclass
class IdempotencyRecord:
    """Stored idempotency record."""
    id: str
    key: str
    user_id: str
    request_hash: str
    response: Optional[dict]
    status: IdempotencyStatus
    created_at: datetime
    expires_at: datetime


class IdempotencyConflict(Exception):
    """
    Raised when same key is used with different request hash.
    
    WHY separate exception: This is a 409 Conflict, not a server error.
    Indicates malicious or buggy client behavior.
    """
    pass


class IdempotencyLocked(Exception):
    """
    Raised when key is locked by another request.
    
    WHY separate exception: Client should retry, not error out.
    """
    pass


def check_idempotency(
    key: str,
    user_id: str,
    request_body: bytes
) -> Tuple[bool, Optional[dict]]:
    """
    Check if request can proceed based on idempotency key.
    
    Flow:
    1. No record → return (True, None), caller should process
    2. Same key + same hash + completed → return (False, cached_response)
    3. Same key + different hash → raise IdempotencyConflict
    4. Same key + pending → raise IdempotencyLocked
    
    Args:
        key: Client-provided idempotency key
        user_id: User making the request
        request_body: Raw request body for hash comparison
        
    Returns:
        Tuple of (should_process, cached_response)
        
    Raises:
        IdempotencyConflict: Key reused with different payload
        IdempotencyLocked: Key being processed by another request
    """
    request_hash = generate_request_hash(request_body)
    
    query = """
        SELECT id, key, user_id, request_hash, response, status, created_at, expires_at
        FROM idempotency_keys
        WHERE key = %s AND user_id = %s AND expires_at > %s
    """
    
    now = datetime.now(timezone.utc)
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (key, user_id, now))
            row = cur.fetchone()
            
            if row is None:
                # No record, caller should process
                return (True, None)
            
            stored_hash = row['request_hash']
            status = IdempotencyStatus(row['status'])
            response = row['response']
            
            # Check if hash matches
            if stored_hash != request_hash:
                # WHY 409: Same key with different payload is suspicious
                # Could be replay attack or buggy client
                logger.warning(
                    "Idempotency conflict: hash mismatch",
                    key=key,
                    user_id=user_id
                )
                raise IdempotencyConflict(
                    f"Idempotency key '{key}' already used with different request"
                )
            
            # Hash matches - check status
            if status == IdempotencyStatus.COMPLETED:
                # Return cached response
                logger.info("Returning cached idempotent response", key=key)
                return (False, response)
            
            if status == IdempotencyStatus.PENDING:
                # Another request is processing
                logger.warning("Idempotency key locked", key=key)
                raise IdempotencyLocked(
                    f"Idempotency key '{key}' is being processed"
                )
            
            if status == IdempotencyStatus.FAILED:
                # Previous attempt failed, allow retry
                return (True, None)
            
            return (True, None)
            
    except (IdempotencyConflict, IdempotencyLocked):
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Idempotency check failed", key=key, error=str(e))
        raise DatabaseError(f"Idempotency check failed: {e}")


def acquire_idempotency_lock(
    key: str,
    user_id: str,
    request_body: bytes
) -> str:
    """
    Acquire lock on idempotency key before processing.
    
    WHY lock: Prevents race condition where multiple concurrent
    requests with same key could all pass the check.
    
    Args:
        key: Idempotency key
        user_id: User ID
        request_body: Request body for hash
        
    Returns:
        ID of created/updated record
        
    Raises:
        IdempotencyConflict: Key exists with different hash
        IdempotencyLocked: Key already locked
    """
    request_hash = generate_request_hash(request_body)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=48)
    
    # Use INSERT with ON CONFLICT to atomically check and lock
    query = """
        INSERT INTO idempotency_keys (key, user_id, request_hash, status, created_at, expires_at, locked_at)
        VALUES (%s, %s, %s, 'pending', %s, %s, %s)
        ON CONFLICT (user_id, key) DO UPDATE SET
            locked_at = CASE 
                WHEN idempotency_keys.status = 'failed' THEN EXCLUDED.locked_at
                WHEN idempotency_keys.status = 'pending' THEN idempotency_keys.locked_at
                ELSE idempotency_keys.locked_at
            END,
            status = CASE
                WHEN idempotency_keys.status = 'failed' THEN 'pending'
                ELSE idempotency_keys.status
            END
        WHERE idempotency_keys.request_hash = %s
        RETURNING id, status, request_hash
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (key, user_id, request_hash, now, expires_at, now, request_hash))
            row = cur.fetchone()
            
            if row is None:
                # ON CONFLICT but hash didn't match WHERE clause
                raise IdempotencyConflict(
                    f"Idempotency key '{key}' already used with different request"
                )
            
            logger.info("Idempotency lock acquired", key=key, record_id=row['id'])
            return row['id']
            
    except IdempotencyConflict:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to acquire idempotency lock", key=key, error=str(e))
        raise DatabaseError(f"Failed to acquire lock: {e}")


def complete_idempotency(
    key: str,
    user_id: str,
    response: dict
) -> None:
    """
    Mark idempotency key as completed with cached response.
    
    Args:
        key: Idempotency key
        user_id: User ID
        response: Response to cache
    """
    query = """
        UPDATE idempotency_keys
        SET status = 'completed', response = %s, locked_at = NULL
        WHERE key = %s AND user_id = %s
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (json.dumps(response), key, user_id))
            
        logger.info("Idempotency completed", key=key)
        
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to complete idempotency", key=key, error=str(e))
        raise DatabaseError(f"Failed to complete: {e}")


def fail_idempotency(
    key: str,
    user_id: str,
    error_message: Optional[str] = None
) -> None:
    """
    Mark idempotency key as failed to allow retry.
    
    Args:
        key: Idempotency key
        user_id: User ID
        error_message: Optional error details
    """
    response = {"error": error_message} if error_message else None
    
    query = """
        UPDATE idempotency_keys
        SET status = 'failed', response = %s, locked_at = NULL
        WHERE key = %s AND user_id = %s
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (json.dumps(response) if response else None, key, user_id))
            
        logger.info("Idempotency marked failed", key=key)
        
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to mark idempotency failed", key=key, error=str(e))
        # Don't raise - failing to update status shouldn't break the request


def cleanup_expired_keys(batch_size: int = 1000) -> int:
    """
    Delete expired idempotency keys.
    
    WHY cleanup: Prevent unbounded table growth.
    Run periodically from a scheduled job.
    
    Args:
        batch_size: Maximum keys to delete per call
        
    Returns:
        Number of keys deleted
    """
    query = """
        DELETE FROM idempotency_keys
        WHERE id IN (
            SELECT id FROM idempotency_keys
            WHERE expires_at < %s
            LIMIT %s
        )
    """
    
    now = datetime.now(timezone.utc)
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (now, batch_size))
            count = cur.rowcount
            
        logger.info("Expired idempotency keys cleaned up", count=count)
        return count
        
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to cleanup idempotency keys", error=str(e))
        raise DatabaseError(f"Cleanup failed: {e}")


class IdempotencyContext:
    """
    Context manager for idempotent operations.
    
    Usage:
        async with IdempotencyContext(key, user_id, request_body) as ctx:
            if ctx.should_process:
                result = do_work()
                ctx.set_response(result)
            return ctx.response
    """
    
    def __init__(self, key: str, user_id: str, request_body: bytes):
        self.key = key
        self.user_id = user_id
        self.request_body = request_body
        self.should_process = False
        self.response: Optional[dict] = None
        self._record_id: Optional[str] = None
    
    def __enter__(self):
        should_process, cached_response = check_idempotency(
            self.key, self.user_id, self.request_body
        )
        
        if not should_process:
            self.response = cached_response
            return self
        
        self._record_id = acquire_idempotency_lock(
            self.key, self.user_id, self.request_body
        )
        self.should_process = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.should_process:
            return False
        
        if exc_type is not None:
            # Exception occurred, mark as failed
            fail_idempotency(self.key, self.user_id, str(exc_val))
            return False
        
        if self.response is not None:
            complete_idempotency(self.key, self.user_id, self.response)
        
        return False
    
    def set_response(self, response: dict) -> None:
        """Set the response to cache."""
        self.response = response
