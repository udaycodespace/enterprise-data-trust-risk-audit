"""
ED-BASE Auth Service
Authentication with Supabase and account lockout protection.

WHY Supabase Auth: Managed auth with industry-standard security.
We add our own session layer on top for revocation control.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass
import structlog
from supabase import create_client, Client

from config import get_config
from utils import get_cursor, DatabaseError
from services.session import (
    create_session,
    revoke_all_user_sessions,
    RevocationReason,
)
from services.audit import log_auth_attempt, log_security_event

logger = structlog.get_logger(__name__)


@dataclass
class AuthResult:
    """Authentication result."""
    success: bool
    user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    error: Optional[str] = None
    locked_until: Optional[datetime] = None


class AuthService:
    """
    Authentication service wrapping Supabase Auth.
    
    WHY wrapper: Adds lockout protection, session tracking,
    and audit logging that Supabase doesn't provide.
    """
    
    def __init__(self):
        config = get_config()
        self._config = config.auth
        
        # Initialize Supabase client
        self._client: Client = create_client(
            config.auth.supabase_url,
            config.auth.supabase_anon_key
        )
        
        # Admin client for privileged operations
        self._admin_client: Client = create_client(
            config.auth.supabase_url,
            config.auth.supabase_service_role_key
        )
    
    def authenticate_password(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuthResult:
        """
        Authenticate with email/password.
        
        Flow:
        1. Check lockout status
        2. Attempt Supabase auth
        3. On failure: increment failures, maybe lock
        4. On success: reset failures, create session
        
        Args:
            email: User email
            password: User password
            ip_address: Client IP for lockout and audit
            user_agent: Client UA for audit
            
        Returns:
            AuthResult with tokens or error
        """
        # Step 1: Check if locked out
        lockout = self._check_lockout(email=email, ip_address=ip_address)
        if lockout:
            log_auth_attempt(
                email=email,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="account_locked"
            )
            return AuthResult(
                success=False,
                error="Account is temporarily locked",
                locked_until=lockout
            )
        
        # Step 2: Attempt authentication
        try:
            response = self._client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            user = response.user
            session = response.session
            
            if not user or not session:
                self._record_failed_attempt(email=email, ip_address=ip_address)
                log_auth_attempt(
                    email=email,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="invalid_credentials"
                )
                return AuthResult(success=False, error="Invalid credentials")
            
            # Step 3: Success - reset failures and create session
            self._reset_failed_attempts(email=email, ip_address=ip_address)
            
            # Create session record for revocation tracking
            create_session(
                user_id=user.id,
                jwt_token=session.access_token,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            log_auth_attempt(
                email=email,
                user_id=user.id,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            logger.info("User authenticated", user_id=user.id, email=email)
            
            return AuthResult(
                success=True,
                user_id=user.id,
                access_token=session.access_token,
                refresh_token=session.refresh_token
            )
            
        except Exception as e:
            # Handle Supabase errors
            error_msg = str(e)
            self._record_failed_attempt(email=email, ip_address=ip_address)
            
            log_auth_attempt(
                email=email,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="auth_error"
            )
            
            logger.warning("Authentication failed", email=email, error=error_msg)
            return AuthResult(success=False, error="Authentication failed")
    
    def authenticate_otp(
        self,
        email: str,
        token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuthResult:
        """
        Authenticate with email OTP (magic link).
        
        Args:
            email: User email
            token: OTP token from magic link
            ip_address: Client IP
            user_agent: Client UA
            
        Returns:
            AuthResult with tokens or error
        """
        lockout = self._check_lockout(email=email, ip_address=ip_address)
        if lockout:
            return AuthResult(
                success=False,
                error="Account is temporarily locked",
                locked_until=lockout
            )
        
        try:
            response = self._client.auth.verify_otp({
                "email": email,
                "token": token,
                "type": "magiclink"
            })
            
            user = response.user
            session = response.session
            
            if not user or not session:
                self._record_failed_attempt(email=email, ip_address=ip_address)
                return AuthResult(success=False, error="Invalid or expired token")
            
            self._reset_failed_attempts(email=email, ip_address=ip_address)
            
            create_session(
                user_id=user.id,
                jwt_token=session.access_token,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            log_auth_attempt(
                email=email,
                user_id=user.id,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent,
                method="otp"
            )
            
            return AuthResult(
                success=True,
                user_id=user.id,
                access_token=session.access_token,
                refresh_token=session.refresh_token
            )
            
        except Exception as e:
            self._record_failed_attempt(email=email, ip_address=ip_address)
            logger.warning("OTP authentication failed", email=email, error=str(e))
            return AuthResult(success=False, error="Authentication failed")
    
    def refresh_tokens(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuthResult:
        """
        Refresh access token using refresh token.
        
        WHY create new session: Old access token should be revoked
        when new one is issued (token rotation per PRD §6).
        
        Args:
            refresh_token: Current refresh token
            ip_address: Client IP
            user_agent: Client UA
            
        Returns:
            AuthResult with new tokens
        """
        try:
            response = self._client.auth.refresh_session(refresh_token)
            
            user = response.user
            session = response.session
            
            if not user or not session:
                return AuthResult(success=False, error="Invalid refresh token")
            
            # Create session for new access token
            create_session(
                user_id=user.id,
                jwt_token=session.access_token,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            logger.info("Tokens refreshed", user_id=user.id)
            
            return AuthResult(
                success=True,
                user_id=user.id,
                access_token=session.access_token,
                refresh_token=session.refresh_token
            )
            
        except Exception as e:
            logger.warning("Token refresh failed", error=str(e))
            return AuthResult(success=False, error="Token refresh failed")
    
    def logout(
        self,
        user_id: str,
        access_token: str,
        logout_all: bool = False
    ) -> bool:
        """
        Log out user by revoking session(s).
        
        Args:
            user_id: User ID
            access_token: Current access token
            logout_all: If True, revoke all sessions (all devices)
            
        Returns:
            True if logout successful
        """
        try:
            if logout_all:
                # Revoke all user sessions
                count = revoke_all_user_sessions(
                    user_id=user_id,
                    reason=RevocationReason.MANUAL_LOGOUT
                )
                logger.info("User logged out from all sessions", 
                           user_id=user_id, sessions_revoked=count)
            else:
                # Revoke just current session
                from services.session import get_session_by_token, revoke_session
                session = get_session_by_token(access_token)
                if session:
                    revoke_session(session.id, RevocationReason.MANUAL_LOGOUT)
                logger.info("User logged out", user_id=user_id)
            
            return True
            
        except Exception as e:
            logger.error("Logout failed", user_id=user_id, error=str(e))
            return False
    
    def change_password(
        self,
        user_id: str,
        new_password: str,
        access_token: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Change user password and revoke all sessions.
        
        WHY revoke sessions: PRD §6 requires forced logout on password change.
        
        Args:
            user_id: User ID
            new_password: New password
            access_token: Current access token (to get user context)
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Update password in Supabase
            self._admin_client.auth.admin.update_user_by_id(
                user_id,
                {"password": new_password}
            )
            
            # Revoke ALL sessions (forced re-login)
            revoke_all_user_sessions(
                user_id=user_id,
                reason=RevocationReason.PASSWORD_CHANGE
            )
            
            log_security_event(
                event_type="password_change",
                user_id=user_id,
                details={"all_sessions_revoked": True}
            )
            
            logger.info("Password changed, all sessions revoked", user_id=user_id)
            return (True, None)
            
        except Exception as e:
            logger.error("Password change failed", user_id=user_id, error=str(e))
            return (False, "Password change failed")
    
    def _check_lockout(
        self,
        email: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Optional[datetime]:
        """
        Check if user/IP is locked out.
        
        Returns locked_until datetime if locked, None if not.
        """
        query = """
            SELECT locked_until FROM account_lockouts
            WHERE (
                (user_id = (SELECT id FROM auth.users WHERE email = %s LIMIT 1) AND %s IS NOT NULL)
                OR
                (ip_address = %s AND %s IS NOT NULL)
            )
            AND locked_until > %s
            LIMIT 1
        """
        
        now = datetime.now(timezone.utc)
        
        try:
            with get_cursor() as cur:
                cur.execute(query, (email, email, ip_address, ip_address, now))
                row = cur.fetchone()
                
                if row:
                    return row['locked_until']
                return None
        except Exception as e:
            logger.error("Lockout check failed", error=str(e))
            return None  # Fail open to not block legitimate users
    
    def _record_failed_attempt(
        self,
        email: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Record a failed authentication attempt.
        May trigger account lockout.
        """
        now = datetime.now(timezone.utc)
        max_attempts = self._config.max_failed_attempts
        lockout_duration = timedelta(minutes=self._config.lockout_duration_minutes)
        
        # Upsert lockout record
        query = """
            INSERT INTO account_lockouts (
                user_id, ip_address, failed_attempts, last_attempt_at, locked_until
            )
            SELECT 
                (SELECT id FROM auth.users WHERE email = %s LIMIT 1),
                %s,
                1,
                %s,
                CASE WHEN 1 >= %s THEN %s ELSE NULL END
            WHERE %s IS NOT NULL OR %s IS NOT NULL
            ON CONFLICT (user_id) WHERE user_id IS NOT NULL AND ip_address IS NULL 
            DO UPDATE SET
                failed_attempts = account_lockouts.failed_attempts + 1,
                last_attempt_at = %s,
                locked_until = CASE 
                    WHEN account_lockouts.failed_attempts + 1 >= %s THEN %s 
                    ELSE account_lockouts.locked_until 
                END
        """
        
        lock_time = now + lockout_duration
        
        try:
            with get_cursor() as cur:
                cur.execute(query, (
                    email, ip_address, now, max_attempts, lock_time,
                    email, ip_address,
                    now, max_attempts, lock_time
                ))
                
                # Check if we just locked the account
                if cur.rowcount > 0:
                    logger.warning("Failed auth attempt recorded", 
                                  email=email, ip=ip_address)
        except Exception as e:
            logger.error("Failed to record auth attempt", error=str(e))
    
    def _reset_failed_attempts(
        self,
        email: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """Reset failed attempt counter after successful auth."""
        query = """
            UPDATE account_lockouts
            SET failed_attempts = 0, locked_until = NULL
            WHERE (
                user_id = (SELECT id FROM auth.users WHERE email = %s LIMIT 1)
                OR ip_address = %s
            )
        """
        
        try:
            with get_cursor() as cur:
                cur.execute(query, (email, ip_address))
        except Exception as e:
            logger.error("Failed to reset attempts", error=str(e))


# Singleton instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get auth service singleton."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
