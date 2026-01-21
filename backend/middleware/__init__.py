"""
ED-BASE Middleware Package
Security middleware for request processing.
"""

from middleware.auth import (
    require_auth,
    require_team,
    require_admin,
    require_owner,
    extract_token,
)

from middleware.rate_limit import (
    init_redis,
    rate_limit,
    rate_limit_login,
    rate_limit_payment,
    check_rate_limit,
)

from middleware.error_handler import (
    error_response,
    register_error_handlers,
    safe_handler,
    ERROR_CODES,
)

__all__ = [
    # Auth
    'require_auth',
    'require_team',
    'require_admin',
    'require_owner',
    'extract_token',
    # Rate limiting
    'init_redis',
    'rate_limit',
    'rate_limit_login',
    'rate_limit_payment',
    'check_rate_limit',
    # Error handling
    'error_response',
    'register_error_handlers',
    'safe_handler',
    'ERROR_CODES',
]
