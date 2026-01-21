"""
ED-BASE Auth Routes
Authentication endpoints with rate limiting.
"""

from flask import Blueprint, request, jsonify, g
import structlog

from middleware import require_auth, rate_limit_login, safe_handler
from services import get_auth_service

logger = structlog.get_logger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['POST'])
@rate_limit_login
@safe_handler
def login():
    """
    Authenticate user with email/password.
    
    Rate limited: 10 requests/minute per IP.
    """
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({
            'error': 'Email and password required',
            'code': 'VALIDATION_ERROR'
        }), 400
    
    auth_service = get_auth_service()
    result = auth_service.authenticate_password(
        email=email,
        password=password,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    if not result.success:
        status = 423 if result.locked_until else 401
        response = {
            'error': result.error,
            'code': 'AUTH_FAILED'
        }
        if result.locked_until:
            response['locked_until'] = result.locked_until.isoformat()
        return jsonify(response), status
    
    return jsonify({
        'access_token': result.access_token,
        'refresh_token': result.refresh_token,
        'user_id': result.user_id
    })


@auth_bp.route('/logout', methods=['POST'])
@require_auth
@safe_handler
def logout():
    """Log out user by revoking session."""
    data = request.get_json() or {}
    logout_all = data.get('logout_all', False)
    
    auth_service = get_auth_service()
    auth_service.logout(
        user_id=g.user_id,
        access_token=g.token,
        logout_all=logout_all
    )
    
    return jsonify({'message': 'Logged out successfully'})


@auth_bp.route('/refresh', methods=['POST'])
@safe_handler
def refresh():
    """Refresh access token using refresh token."""
    data = request.get_json() or {}
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({
            'error': 'Refresh token required',
            'code': 'VALIDATION_ERROR'
        }), 400
    
    auth_service = get_auth_service()
    result = auth_service.refresh_tokens(
        refresh_token=refresh_token,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    if not result.success:
        return jsonify({
            'error': result.error,
            'code': 'REFRESH_FAILED'
        }), 401
    
    return jsonify({
        'access_token': result.access_token,
        'refresh_token': result.refresh_token
    })


@auth_bp.route('/password', methods=['PUT'])
@require_auth
@safe_handler
def change_password():
    """
    Change user password.
    
    Revokes all sessions after change (PRD §6).
    """
    data = request.get_json() or {}
    new_password = data.get('new_password')
    
    if not new_password or len(new_password) < 8:
        return jsonify({
            'error': 'Password must be at least 8 characters',
            'code': 'VALIDATION_ERROR'
        }), 400
    
    auth_service = get_auth_service()
    success, error = auth_service.change_password(
        user_id=g.user_id,
        new_password=new_password,
        access_token=g.token
    )
    
    if not success:
        return jsonify({
            'error': error,
            'code': 'PASSWORD_CHANGE_FAILED'
        }), 400
    
    return jsonify({
        'message': 'Password changed. All sessions revoked.'
    })
