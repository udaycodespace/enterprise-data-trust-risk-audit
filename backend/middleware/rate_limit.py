"""
ED-BASE Rate Limiting Middleware
Redis-based sliding window rate limiting per PRD §8.
"""

import time
import hashlib
from functools import wraps
from typing import Optional, Callable, Tuple
from flask import request, g, jsonify, Response
import redis
import structlog

from config import get_config
from services.audit import log_security_event

logger = structlog.get_logger(__name__)

# Redis connection pool
_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


def init_redis() -> None:
    """Initialize Redis connection pool."""
    global _redis_pool, _redis_client
    
    config = get_config().redis
    _redis_pool = redis.ConnectionPool.from_url(
        config.url,
        max_connections=config.max_connections,
        socket_timeout=config.socket_timeout,
        socket_connect_timeout=config.socket_connect_timeout
    )
    _redis_client = redis.Redis(connection_pool=_redis_pool)
    logger.info("Redis connection pool initialized")


def get_redis() -> redis.Redis:
    """Get Redis client."""
    if _redis_client is None:
        init_redis()
    return _redis_client


def get_client_fingerprint() -> str:
    """
    Generate client fingerprint from multiple signals.
    
    WHY not just IP: X-Forwarded-For can be spoofed (PRD §8).
    Combine IP + User-Agent + custom header for better identification.
    """
    ip = request.remote_addr or 'unknown'
    user_agent = request.headers.get('User-Agent', 'unknown')
    
    # Custom fingerprint header (optional)
    custom = request.headers.get('X-Client-Fingerprint', '')
    
    # Combine and hash
    data = f"{ip}|{user_agent}|{custom}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def check_rate_limit(
    key_prefix: str,
    identifier: str,
    limit: int,
    window_seconds: int = 60
) -> Tuple[bool, int, int]:
    """
    Check sliding window rate limit.
    
    Args:
        key_prefix: Rate limit category (ip, user, endpoint)
        identifier: Unique identifier for the entity
        limit: Maximum requests per window
        window_seconds: Window size in seconds
        
    Returns:
        Tuple of (is_allowed, current_count, retry_after_seconds)
    """
    now = time.time()
    window_start = now - window_seconds
    key = f"ratelimit:{key_prefix}:{identifier}"
    
    try:
        r = get_redis()
        pipe = r.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Add current request
        pipe.zadd(key, {str(now): now})
        
        # Count requests in window
        pipe.zcard(key)
        
        # Set expiry on key
        pipe.expire(key, window_seconds + 10)
        
        results = pipe.execute()
        count = results[2]
        
        if count > limit:
            # Calculate retry-after
            oldest = r.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = int(window_seconds - (now - oldest[0][1])) + 1
            else:
                retry_after = window_seconds
            
            return (False, count, retry_after)
        
        return (True, count, 0)
        
    except redis.RedisError as e:
        # WHY fail open: Rate limit failure should not block requests
        # Log and monitor, but allow the request
        logger.error("Rate limit check failed", error=str(e))
        return (True, 0, 0)


def rate_limit_response(retry_after: int) -> Response:
    """Create 429 response with Retry-After header."""
    response = jsonify({
        'error': 'Too many requests',
        'code': 'RATE_LIMITED',
        'retry_after': retry_after,
        'request_id': g.get('request_id')
    })
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    return response


def rate_limit(
    per_ip: Optional[int] = None,
    per_user: Optional[int] = None,
    per_endpoint: Optional[int] = None
):
    """
    Rate limiting decorator.
    
    Args:
        per_ip: Requests per minute per IP (default 100)
        per_user: Requests per minute per user (default 50)
        per_endpoint: Requests per minute per endpoint
    """
    config = get_config().rate_limit
    
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            ip_limit = per_ip or config.ip_requests_per_minute
            user_limit = per_user or config.user_requests_per_minute
            
            fingerprint = get_client_fingerprint()
            
            # Check IP rate limit
            allowed, count, retry_after = check_rate_limit(
                'ip', fingerprint, ip_limit
            )
            if not allowed:
                log_security_event(
                    event_type="rate_limit",
                    details={'type': 'ip', 'count': count, 'limit': ip_limit},
                    ip_address=request.remote_addr
                )
                logger.warning("IP rate limit hit", ip=fingerprint)
                return rate_limit_response(retry_after)
            
            # Check per-user rate limit if authenticated
            user_id = g.get('user_id')
            if user_id:
                allowed, count, retry_after = check_rate_limit(
                    'user', user_id, user_limit
                )
                if not allowed:
                    log_security_event(
                        event_type="rate_limit",
                        user_id=user_id,
                        details={'type': 'user', 'count': count, 'limit': user_limit}
                    )
                    logger.warning("User rate limit hit", user_id=user_id)
                    return rate_limit_response(retry_after)
            
            # Check per-endpoint rate limit
            if per_endpoint:
                endpoint_key = f"{request.method}:{request.endpoint}"
                identifier = f"{fingerprint}:{endpoint_key}"
                
                allowed, count, retry_after = check_rate_limit(
                    'endpoint', identifier, per_endpoint
                )
                if not allowed:
                    logger.warning("Endpoint rate limit hit", endpoint=endpoint_key)
                    return rate_limit_response(retry_after)
            
            return f(*args, **kwargs)
        return decorated
    return decorator


def rate_limit_login(f: Callable) -> Callable:
    """Rate limit for login endpoint: 10/min per PRD §8."""
    return rate_limit(per_ip=10, per_endpoint=10)(f)


def rate_limit_payment(f: Callable) -> Callable:
    """Rate limit for payment endpoint: 5/min per PRD §8."""
    return rate_limit(per_user=5, per_endpoint=5)(f)
