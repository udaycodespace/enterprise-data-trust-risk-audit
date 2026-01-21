"""
ED-BASE Utils Package
Shared utilities for crypto, database, and common operations.
"""

from utils.crypto import (
    sha256_hash,
    hmac_sign,
    hmac_verify,
    generate_token_hash,
    generate_request_hash,
    generate_idempotency_key,
    generate_request_id,
    sign_pagination_cursor,
    verify_pagination_cursor,
    sign_audit_entry,
    verify_audit_entry,
    constant_time_compare,
)

from utils.database import (
    init_connection_pool,
    close_connection_pool,
    get_connection,
    get_cursor,
    execute_query,
    is_within_clock_skew,
    soft_delete,
    health_check,
    DatabaseError,
    DatabaseConnectionError,
    QueryTimeoutError,
    SerializationError,
)

__all__ = [
    # Crypto
    'sha256_hash',
    'hmac_sign',
    'hmac_verify',
    'generate_token_hash',
    'generate_request_hash',
    'generate_idempotency_key',
    'generate_request_id',
    'sign_pagination_cursor',
    'verify_pagination_cursor',
    'sign_audit_entry',
    'verify_audit_entry',
    'constant_time_compare',
    # Database
    'init_connection_pool',
    'close_connection_pool',
    'get_connection',
    'get_cursor',
    'execute_query',
    'is_within_clock_skew',
    'soft_delete',
    'health_check',
    'DatabaseError',
    'DatabaseConnectionError',
    'QueryTimeoutError',
    'SerializationError',
]
