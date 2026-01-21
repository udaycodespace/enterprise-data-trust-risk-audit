"""
ED-BASE Error Handler Middleware
Generic error responses without information disclosure.

Invariant #9: Errors never leak internal system details.
"""

from functools import wraps
from typing import Callable, Optional
from flask import jsonify, g, Flask
import traceback
import structlog

logger = structlog.get_logger(__name__)


# Standard error codes
ERROR_CODES = {
    'AUTH_REQUIRED': 'Authentication is required',
    'SESSION_INVALID': 'Session is invalid or expired',
    'TEAM_REQUIRED': 'Team context is required',
    'TEAM_ACCESS_DENIED': 'Access to this team is denied',
    'ROLE_REQUIRED': 'Insufficient permissions for this action',
    'RATE_LIMITED': 'Too many requests, please slow down',
    'VALIDATION_ERROR': 'Invalid request data',
    'NOT_FOUND': 'Resource not found',
    'CONFLICT': 'Request conflicts with current state',
    'IDEMPOTENCY_CONFLICT': 'Idempotency key reused with different payload',
    'PAYMENT_ERROR': 'Payment processing error',
    'INTERNAL_ERROR': 'An unexpected error occurred',
}


def error_response(
    code: str,
    message: Optional[str] = None,
    status: int = 400,
    details: Optional[dict] = None
):
    """
    Create standardized error response.
    
    WHY standardized: Consistent client error handling.
    Generic messages prevent information disclosure (Invariant #9).
    """
    response_body = {
        'error': message or ERROR_CODES.get(code, 'An error occurred'),
        'code': code,
        'request_id': g.get('request_id')
    }
    
    # Only include safe details
    if details and isinstance(details, dict):
        safe_details = {
            k: v for k, v in details.items()
            if k in ('field', 'retry_after', 'max_value', 'min_value')
        }
        if safe_details:
            response_body['details'] = safe_details
    
    return jsonify(response_body), status


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers on Flask app."""
    
    @app.errorhandler(400)
    def bad_request(error):
        return error_response('VALIDATION_ERROR', status=400)
    
    @app.errorhandler(401)
    def unauthorized(error):
        return error_response('AUTH_REQUIRED', status=401)
    
    @app.errorhandler(403)
    def forbidden(error):
        return error_response('TEAM_ACCESS_DENIED', status=403)
    
    @app.errorhandler(404)
    def not_found(error):
        return error_response('NOT_FOUND', 'Resource not found', status=404)
    
    @app.errorhandler(409)
    def conflict(error):
        return error_response('CONFLICT', status=409)
    
    @app.errorhandler(429)
    def rate_limited(error):
        return error_response('RATE_LIMITED', status=429)
    
    @app.errorhandler(500)
    def internal_error(error):
        # Log full error internally
        logger.error(
            "Internal server error",
            error=str(error),
            request_id=g.get('request_id'),
            traceback=traceback.format_exc()
        )
        
        # Return generic message (Invariant #9)
        return error_response(
            'INTERNAL_ERROR',
            'An unexpected error occurred',
            status=500
        )
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        # Log full details internally
        logger.error(
            "Unhandled exception",
            error=str(error),
            error_type=type(error).__name__,
            request_id=g.get('request_id'),
            traceback=traceback.format_exc()
        )
        
        # Never expose internal details (Invariant #9)
        return error_response(
            'INTERNAL_ERROR',
            'An unexpected error occurred',
            status=500
        )


def safe_handler(f: Callable) -> Callable:
    """
    Decorator for safe exception handling.
    
    Catches exceptions and returns generic error response.
    Logs full details internally.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning("Validation error", error=str(e))
            return error_response('VALIDATION_ERROR', str(e), status=400)
        except Exception as e:
            logger.error(
                "Handler exception",
                error=str(e),
                handler=f.__name__,
                traceback=traceback.format_exc()
            )
            return error_response('INTERNAL_ERROR', status=500)
    
    return decorated
