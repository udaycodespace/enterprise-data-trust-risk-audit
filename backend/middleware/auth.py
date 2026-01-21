"""
ED-BASE Auth Middleware
Session revocation enforcement on every request.

Invariant #1: A revoked session can NEVER perform a write.
"""

from functools import wraps
from typing import Optional, Callable
from flask import request, g, jsonify
import structlog

from services.session import validate_session, Session
from services.authorization import (
    get_authorization_context,
    require_team_access,
    Role,
    AuthorizationContext,
    TeamBoundaryError,
    RoleError,
)
from services.audit import log_security_event
from utils import generate_request_id

logger = structlog.get_logger(__name__)


def extract_token() -> Optional[str]:
    """Extract JWT from Authorization header."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def require_auth(f: Callable) -> Callable:
    """
    Decorator requiring valid, non-revoked session.
    
    Checks both JWT validity AND session revocation status
    on EVERY request (Invariant #1).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Generate request ID for correlation
        request_id = generate_request_id()
        g.request_id = request_id
        
        # Extract token
        token = extract_token()
        if not token:
            return jsonify({
                'error': 'Authentication required',
                'code': 'AUTH_REQUIRED',
                'request_id': request_id
            }), 401
        
        # Validate session (Invariant #1)
        is_valid, session, error = validate_session(token)
        
        if not is_valid:
            log_security_event(
                event_type="session_revoked",
                user_id=session.user_id if session else None,
                details={'error': error},
                ip_address=request.remote_addr
            )
            return jsonify({
                'error': 'Session invalid or revoked',
                'code': 'SESSION_INVALID',
                'request_id': request_id
            }), 401
        
        # Store session in request context
        g.session = session
        g.user_id = session.user_id
        g.token = token
        
        return f(*args, **kwargs)
    
    return decorated


def require_team(team_id_param: str = 'team_id', required_role: Optional[Role] = None):
    """
    Decorator requiring valid team membership.
    
    Enforces team boundary (Invariant #3) and optional role check.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            # Get team_id from URL params, query string, or JSON body
            team_id = (
                kwargs.get(team_id_param) or
                request.args.get(team_id_param) or
                (request.json or {}).get(team_id_param)
            )
            
            if not team_id:
                return jsonify({
                    'error': 'Team ID required',
                    'code': 'TEAM_REQUIRED',
                    'request_id': g.get('request_id')
                }), 400
            
            try:
                # Check team access (Invariant #3)
                context = require_team_access(
                    user_id=g.user_id,
                    team_id=team_id,
                    required_role=required_role
                )
                g.team_id = team_id
                g.auth_context = context
                
            except TeamBoundaryError as e:
                logger.warning("Team boundary violation",
                              user_id=g.user_id, team_id=team_id)
                return jsonify({
                    'error': 'Access denied',
                    'code': 'TEAM_ACCESS_DENIED',
                    'request_id': g.get('request_id')
                }), 403
                
            except RoleError as e:
                logger.warning("Role check failed",
                              user_id=g.user_id, required=required_role.value)
                return jsonify({
                    'error': 'Insufficient permissions',
                    'code': 'ROLE_REQUIRED',
                    'request_id': g.get('request_id')
                }), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_admin(f: Callable) -> Callable:
    """Decorator requiring admin role."""
    return require_team(required_role=Role.ADMIN)(f)


def require_owner(f: Callable) -> Callable:
    """Decorator requiring owner role."""
    return require_team(required_role=Role.OWNER)(f)
