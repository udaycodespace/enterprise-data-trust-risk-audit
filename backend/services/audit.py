"""
ED-BASE Audit Service
Immutable, append-only audit logging with HMAC signing.

Invariant #5: Audit logs are append-only and immutable.
Invariant #10: All critical actions are attributable to an actor.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
import json
import structlog

from utils import get_cursor, sign_audit_entry, verify_audit_entry, DatabaseError
from services.transactions import audit_transaction
from config import get_config

logger = structlog.get_logger(__name__)


class EventType(Enum):
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_PASSWORD_CHANGE = "auth.password.change"
    AUTH_ACCOUNT_LOCKED = "auth.account.locked"
    AUTHZ_ACCESS_DENIED = "authz.access.denied"
    AUTHZ_ROLE_CHANGE = "authz.role.change"
    STATE_CREATE = "state.create"
    STATE_UPDATE = "state.update"
    STATE_DELETE = "state.delete"
    CONFIG_UPDATE = "config.update"
    SECURITY_SESSION_REVOKED = "security.session.revoked"
    SECURITY_RATE_LIMIT_HIT = "security.rate_limit.hit"
    SECURITY_SUSPICIOUS_ACTIVITY = "security.suspicious"
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"


class ActorType(Enum):
    USER = "user"
    SYSTEM = "system"
    WEBHOOK = "webhook"
    ADMIN = "admin"
    ANONYMOUS = "anonymous"


def log_event(
    event_type: EventType,
    action: str,
    actor_id: Optional[str] = None,
    actor_type: ActorType = ActorType.SYSTEM,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None
) -> str:
    """Log an audit event with HMAC signing."""
    config = get_config()
    now = datetime.now(timezone.utc)
    
    entry_data = {
        'event_type': event_type.value,
        'actor_id': actor_id,
        'actor_type': actor_type.value,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'action': action,
        'details': details,
        'created_at': now.isoformat()
    }
    
    signature = sign_audit_entry(entry_data, config.audit.hmac_secret)
    
    query = """
        INSERT INTO audit_logs (
            event_type, actor_id, actor_type, resource_type, resource_id,
            action, details, ip_address, user_agent, request_id, hmac_signature
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    
    try:
        with audit_transaction() as cur:
            cur.execute(query, (
                event_type.value, actor_id, actor_type.value,
                resource_type, resource_id, action,
                json.dumps(details) if details else None,
                ip_address, user_agent, request_id, signature
            ))
            return str(cur.fetchone()['id'])
    except Exception as e:
        logger.critical("AUDIT LOG FAILED", event_type=event_type.value, error=str(e))
        raise DatabaseError(f"Audit logging failed: {e}")


def log_auth_attempt(
    email: str, success: bool, user_id: Optional[str] = None,
    ip_address: Optional[str] = None, user_agent: Optional[str] = None,
    failure_reason: Optional[str] = None, method: str = "password"
) -> str:
    event_type = EventType.AUTH_LOGIN_SUCCESS if success else EventType.AUTH_LOGIN_FAILURE
    details = {'method': method}
    if failure_reason:
        details['failure_reason'] = failure_reason
    return log_event(
        event_type=event_type,
        action=f"{'Successful' if success else 'Failed'} {method} auth",
        actor_id=user_id,
        actor_type=ActorType.USER if user_id else ActorType.ANONYMOUS,
        details=details, ip_address=ip_address, user_agent=user_agent
    )


def log_security_event(
    event_type: str, user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None, ip_address: Optional[str] = None
) -> str:
    event_enum = EventType.SECURITY_SUSPICIOUS_ACTIVITY
    if event_type == "session_revoked":
        event_enum = EventType.SECURITY_SESSION_REVOKED
    elif event_type == "rate_limit":
        event_enum = EventType.SECURITY_RATE_LIMIT_HIT
    return log_event(
        event_type=event_enum, action=f"Security: {event_type}",
        actor_id=user_id, actor_type=ActorType.USER if user_id else ActorType.SYSTEM,
        details=details, ip_address=ip_address
    )


def verify_log_integrity(log_id: int) -> bool:
    """Verify audit log entry has not been tampered with."""
    config = get_config()
    query = """
        SELECT event_type, actor_id, actor_type, resource_type, resource_id,
               action, details, created_at, hmac_signature
        FROM audit_logs WHERE id = %s
    """
    try:
        with get_cursor() as cur:
            cur.execute(query, (log_id,))
            row = cur.fetchone()
            if not row:
                return False
            entry_data = {
                'event_type': row['event_type'], 'actor_id': row['actor_id'],
                'actor_type': row['actor_type'], 'resource_type': row['resource_type'],
                'resource_id': row['resource_id'], 'action': row['action'],
                'details': row['details'], 'created_at': row['created_at'].isoformat()
            }
            return verify_audit_entry(entry_data, row['hmac_signature'], config.audit.hmac_secret)
    except Exception as e:
        logger.error("Integrity check failed", log_id=log_id, error=str(e))
        return False
