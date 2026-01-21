"""
ED-BASE Session Service
Session management with revocation enforcement.

Invariant #1: A revoked session can NEVER perform a write.
Invariant #4: Role changes invalidate sessions immediately.

WHY session table separate from JWT: JWT validity does NOT imply
session validity (PRD §6). We check both.
"""

from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass
from enum import Enum
import structlog

from utils import (
    get_cursor,
    generate_token_hash,
    DatabaseError,
)
from config import get_config

logger = structlog.get_logger(__name__)


class RevocationReason(Enum):
    """Reasons for session revocation per PRD §6."""
    PASSWORD_CHANGE = "password_change"
    ROLE_CHANGE = "role_change"
    TEAM_CHANGE = "team_change"
    MANUAL_LOGOUT = "manual_logout"
    ACCOUNT_LOCK = "account_lock"
    SECURITY_INCIDENT = "security_incident"
    TOKEN_REFRESH = "token_refresh"
    ADMIN_ACTION = "admin_action"
    SESSION_EXPIRED = "session_expired"


@dataclass
class Session:
    """Session data structure."""
    id: str
    user_id: str
    token_hash: str
    team_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    last_used_at: datetime
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    
    @property
    def is_valid(self) -> bool:
        """Session is valid if not revoked."""
        return self.revoked_at is None


def create_session(
    user_id: str,
    jwt_token: str,
    team_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Session:
    """
    Create a new session record for a JWT token.
    
    WHY store token hash: If DB is compromised, attacker cannot
    reconstruct valid tokens from hashes.
    
    Args:
        user_id: Supabase Auth user ID
        jwt_token: Raw JWT access token
        team_id: Optional active team ID
        ip_address: Client IP for audit
        user_agent: Client UA for audit
        
    Returns:
        Created Session object
    """
    token_hash = generate_token_hash(jwt_token)
    now = datetime.now(timezone.utc)
    
    query = """
        INSERT INTO sessions (user_id, token_hash, team_id, ip_address, user_agent, created_at, last_used_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, user_id, token_hash, team_id, ip_address, user_agent, created_at, last_used_at, revoked_at, revocation_reason
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (user_id, token_hash, team_id, ip_address, user_agent, now, now))
            row = cur.fetchone()
            
            logger.info("Session created", user_id=user_id, session_id=row['id'])
            
            return Session(**row)
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to create session", user_id=user_id, error=str(e))
        raise DatabaseError(f"Failed to create session: {e}")


def get_session_by_token(jwt_token: str) -> Optional[Session]:
    """
    Look up session by JWT token.
    
    WHY check revoked_at: Invariant #1 - must reject revoked sessions.
    
    Args:
        jwt_token: Raw JWT access token
        
    Returns:
        Session if found, None otherwise
    """
    token_hash = generate_token_hash(jwt_token)
    
    query = """
        SELECT id, user_id, token_hash, team_id, ip_address, user_agent, 
               created_at, last_used_at, revoked_at, revocation_reason
        FROM sessions
        WHERE token_hash = %s
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (token_hash,))
            row = cur.fetchone()
            
            if row is None:
                return None
            
            return Session(**row)
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to get session", error=str(e))
        raise DatabaseError(f"Failed to get session: {e}")


def validate_session(jwt_token: str) -> tuple[bool, Optional[Session], Optional[str]]:
    """
    Validate session for an authenticated request.
    
    This MUST be called on EVERY authenticated request (Invariant #1).
    
    Args:
        jwt_token: Raw JWT access token
        
    Returns:
        Tuple of (is_valid, session, error_message)
    """
    session = get_session_by_token(jwt_token)
    
    if session is None:
        # WHY reject missing: Token not in our session table is suspicious
        # Could be token from before we started tracking, or forged token
        logger.warning("Session not found for token")
        return (False, None, "Session not found")
    
    if not session.is_valid:
        # WHY log: Track revoked session usage for security monitoring
        logger.warning(
            "Revoked session used",
            session_id=session.id,
            user_id=session.user_id,
            revoked_at=session.revoked_at.isoformat(),
            reason=session.revocation_reason
        )
        return (False, session, f"Session revoked: {session.revocation_reason}")
    
    # Update last_used_at for session activity tracking
    _update_session_activity(session.id)
    
    return (True, session, None)


def _update_session_activity(session_id: str) -> None:
    """Update last_used_at timestamp for session."""
    query = """
        UPDATE sessions
        SET last_used_at = %s
        WHERE id = %s
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (datetime.now(timezone.utc), session_id))
    except Exception as e:
        # WHY not raise: Activity tracking failure should not break request
        logger.warning("Failed to update session activity", session_id=session_id, error=str(e))


def revoke_session(
    session_id: str,
    reason: RevocationReason,
    actor_id: Optional[str] = None
) -> bool:
    """
    Revoke a specific session.
    
    Args:
        session_id: Session UUID
        reason: Revocation reason
        actor_id: Who initiated revocation (for audit)
        
    Returns:
        True if session was revoked
    """
    query = """
        UPDATE sessions
        SET revoked_at = %s, revocation_reason = %s
        WHERE id = %s AND revoked_at IS NULL
    """
    
    now = datetime.now(timezone.utc)
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (now, reason.value, session_id))
            revoked = cur.rowcount > 0
            
            if revoked:
                logger.info(
                    "Session revoked",
                    session_id=session_id,
                    reason=reason.value,
                    actor_id=actor_id
                )
            
            return revoked
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to revoke session", session_id=session_id, error=str(e))
        raise DatabaseError(f"Failed to revoke session: {e}")


def revoke_all_user_sessions(
    user_id: str,
    reason: RevocationReason,
    exclude_session_id: Optional[str] = None,
    actor_id: Optional[str] = None
) -> int:
    """
    Revoke all sessions for a user (forced logout).
    
    Used when:
    - Password changes (PRD §6)
    - Account lock
    - Security incident
    
    Args:
        user_id: User UUID
        reason: Revocation reason
        exclude_session_id: Optional session to keep (current session)
        actor_id: Who initiated revocation
        
    Returns:
        Number of sessions revoked
    """
    now = datetime.now(timezone.utc)
    
    if exclude_session_id:
        query = """
            UPDATE sessions
            SET revoked_at = %s, revocation_reason = %s
            WHERE user_id = %s AND revoked_at IS NULL AND id != %s
        """
        params = (now, reason.value, user_id, exclude_session_id)
    else:
        query = """
            UPDATE sessions
            SET revoked_at = %s, revocation_reason = %s
            WHERE user_id = %s AND revoked_at IS NULL
        """
        params = (now, reason.value, user_id)
    
    try:
        with get_cursor() as cur:
            cur.execute(query, params)
            count = cur.rowcount
            
            logger.info(
                "User sessions revoked",
                user_id=user_id,
                count=count,
                reason=reason.value,
                actor_id=actor_id
            )
            
            return count
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to revoke user sessions", user_id=user_id, error=str(e))
        raise DatabaseError(f"Failed to revoke sessions: {e}")


def revoke_sessions_by_team(
    team_id: str,
    reason: RevocationReason,
    actor_id: Optional[str] = None
) -> int:
    """
    Revoke all sessions for a team.
    
    Used when team membership changes (Invariant #4).
    
    Args:
        team_id: Team UUID
        reason: Revocation reason
        actor_id: Who initiated revocation
        
    Returns:
        Number of sessions revoked
    """
    query = """
        UPDATE sessions
        SET revoked_at = %s, revocation_reason = %s
        WHERE team_id = %s AND revoked_at IS NULL
    """
    
    now = datetime.now(timezone.utc)
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (now, reason.value, team_id))
            count = cur.rowcount
            
            logger.info(
                "Team sessions revoked",
                team_id=team_id,
                count=count,
                reason=reason.value,
                actor_id=actor_id
            )
            
            return count
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to revoke team sessions", team_id=team_id, error=str(e))
        raise DatabaseError(f"Failed to revoke sessions: {e}")


def cleanup_expired_sessions(days_old: int = 30) -> int:
    """
    Remove old revoked sessions for cleanup.
    
    WHY keep revoked sessions: Audit trail for security investigation.
    WHY cleanup: Prevent unbounded table growth.
    
    Args:
        days_old: Delete revoked sessions older than this
        
    Returns:
        Number of sessions deleted
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
    
    query = """
        DELETE FROM sessions
        WHERE revoked_at IS NOT NULL AND revoked_at < %s
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (cutoff,))
            count = cur.rowcount
            
            logger.info("Expired sessions cleaned up", count=count, cutoff=cutoff.isoformat())
            
            return count
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to cleanup sessions", error=str(e))
        raise DatabaseError(f"Failed to cleanup sessions: {e}")


# Import timedelta for cleanup function
from datetime import timedelta
