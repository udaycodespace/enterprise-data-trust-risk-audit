"""
ED-BASE Authorization Service
Role-based access control with team isolation.

Invariant #3: Users cannot cross team boundaries.
Invariant #6: Backend authorization overrides frontend state.

WHY query-time checks: No permission caching. Roles could change
between requests, cache would allow unauthorized access.
"""

from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum
import structlog

from utils import get_cursor, DatabaseError
from services.session import (
    revoke_sessions_by_team,
    revoke_all_user_sessions,
    RevocationReason,
)

logger = structlog.get_logger(__name__)


class Role(Enum):
    """Team roles in descending privilege order."""
    OWNER = "owner"      # Full control, can delete team
    ADMIN = "admin"      # Manage members, settings
    MEMBER = "member"    # Normal access
    VIEWER = "viewer"    # Read-only


# Role hierarchy for permission checks
ROLE_HIERARCHY = {
    Role.OWNER: 4,
    Role.ADMIN: 3,
    Role.MEMBER: 2,
    Role.VIEWER: 1,
}


@dataclass
class TeamMembership:
    """Team membership data."""
    id: str
    team_id: str
    user_id: str
    role: Role
    is_active: bool
    created_at: datetime


@dataclass
class AuthorizationContext:
    """
    Authorization context for a request.
    
    WHY context object: Centralizes all auth info needed for
    permission checks. Passed through request lifecycle.
    """
    user_id: str
    team_id: str
    role: Role
    is_active: bool
    
    def has_role(self, required_role: Role) -> bool:
        """Check if user has at least the required role level."""
        if not self.is_active:
            return False
        return ROLE_HIERARCHY[self.role] >= ROLE_HIERARCHY[required_role]
    
    def is_owner(self) -> bool:
        return self.role == Role.OWNER and self.is_active
    
    def is_admin(self) -> bool:
        return self.has_role(Role.ADMIN)
    
    def can_manage_members(self) -> bool:
        return self.has_role(Role.ADMIN)
    
    def can_view(self) -> bool:
        return self.has_role(Role.VIEWER)


class AuthorizationError(Exception):
    """Raised when authorization check fails."""
    pass


class TeamBoundaryError(AuthorizationError):
    """Raised when user tries to cross team boundary."""
    pass


class RoleError(AuthorizationError):
    """Raised when user lacks required role."""
    pass


def get_authorization_context(
    user_id: str,
    team_id: str
) -> Optional[AuthorizationContext]:
    """
    Get authorization context for user in team.
    
    WHY query time: No caching. Fresh from DB every request (Invariant #3).
    
    Args:
        user_id: User UUID
        team_id: Team UUID
        
    Returns:
        AuthorizationContext if user belongs to team, None otherwise
    """
    query = """
        SELECT tm.id, tm.team_id, tm.user_id, tm.role, tm.is_active, tm.created_at
        FROM team_memberships tm
        JOIN teams t ON tm.team_id = t.id
        WHERE tm.user_id = %s 
        AND tm.team_id = %s
        AND t.deleted_at IS NULL
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (user_id, team_id))
            row = cur.fetchone()
            
            if row is None:
                logger.warning(
                    "User not member of team",
                    user_id=user_id,
                    team_id=team_id
                )
                return None
            
            return AuthorizationContext(
                user_id=row['user_id'],
                team_id=row['team_id'],
                role=Role(row['role']),
                is_active=row['is_active']
            )
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Authorization context lookup failed", error=str(e))
        raise DatabaseError(f"Authorization failed: {e}")


def require_team_access(
    user_id: str,
    team_id: str,
    required_role: Optional[Role] = None
) -> AuthorizationContext:
    """
    Verify user has access to team with optional role check.
    
    WHY raise exceptions: Fail-closed security. If check fails,
    request processing stops immediately.
    
    Args:
        user_id: User UUID
        team_id: Team UUID
        required_role: Optional minimum role required
        
    Returns:
        AuthorizationContext if authorized
        
    Raises:
        TeamBoundaryError: If user not in team
        RoleError: If user lacks required role
    """
    context = get_authorization_context(user_id, team_id)
    
    if context is None:
        raise TeamBoundaryError(
            f"User {user_id} is not a member of team {team_id}"
        )
    
    if not context.is_active:
        raise TeamBoundaryError(
            f"User {user_id} membership in team {team_id} is inactive"
        )
    
    if required_role and not context.has_role(required_role):
        raise RoleError(
            f"User {user_id} requires role {required_role.value} in team {team_id}"
        )
    
    return context


def get_user_teams(user_id: str, active_only: bool = True) -> List[TeamMembership]:
    """
    Get all teams a user belongs to.
    
    Args:
        user_id: User UUID
        active_only: If True, only return active memberships
        
    Returns:
        List of TeamMembership objects
    """
    query = """
        SELECT tm.id, tm.team_id, tm.user_id, tm.role, tm.is_active, tm.created_at
        FROM team_memberships tm
        JOIN teams t ON tm.team_id = t.id
        WHERE tm.user_id = %s
        AND t.deleted_at IS NULL
    """
    
    if active_only:
        query += " AND tm.is_active = true"
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (user_id,))
            rows = cur.fetchall()
            
            return [
                TeamMembership(
                    id=row['id'],
                    team_id=row['team_id'],
                    user_id=row['user_id'],
                    role=Role(row['role']),
                    is_active=row['is_active'],
                    created_at=row['created_at']
                )
                for row in rows
            ]
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to get user teams", user_id=user_id, error=str(e))
        raise DatabaseError(f"Failed to get teams: {e}")


def add_team_member(
    team_id: str,
    user_id: str,
    role: Role,
    invited_by: str
) -> TeamMembership:
    """
    Add a member to a team.
    
    Args:
        team_id: Team UUID
        user_id: User UUID to add
        role: Role to assign
        invited_by: User UUID who is adding
        
    Returns:
        Created TeamMembership
        
    Raises:
        RoleError: If inviter lacks permission
    """
    # Verify inviter has permission
    inviter_context = require_team_access(invited_by, team_id, Role.ADMIN)
    
    # Cannot add someone as owner unless you're owner
    if role == Role.OWNER and not inviter_context.is_owner():
        raise RoleError("Only owners can add other owners")
    
    now = datetime.now(timezone.utc)
    
    query = """
        INSERT INTO team_memberships (team_id, user_id, role, is_active, invited_by, created_at, updated_at)
        VALUES (%s, %s, %s, true, %s, %s, %s)
        ON CONFLICT (team_id, user_id) DO UPDATE SET
            role = EXCLUDED.role,
            is_active = true,
            updated_at = EXCLUDED.updated_at
        RETURNING id, team_id, user_id, role, is_active, created_at
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (team_id, user_id, role.value, invited_by, now, now))
            row = cur.fetchone()
            
            logger.info(
                "Team member added",
                team_id=team_id,
                user_id=user_id,
                role=role.value,
                invited_by=invited_by
            )
            
            return TeamMembership(
                id=row['id'],
                team_id=row['team_id'],
                user_id=row['user_id'],
                role=Role(row['role']),
                is_active=row['is_active'],
                created_at=row['created_at']
            )
    except DatabaseError:
        raise
    except Exception as e:
        logger.error("Failed to add team member", error=str(e))
        raise DatabaseError(f"Failed to add member: {e}")


def change_member_role(
    team_id: str,
    user_id: str,
    new_role: Role,
    changed_by: str
) -> None:
    """
    Change a team member's role.
    
    WHY revoke sessions: Invariant #4 - role changes invalidate sessions.
    User must re-authenticate to get new permissions.
    
    Args:
        team_id: Team UUID
        user_id: User UUID whose role is changing
        new_role: New role to assign
        changed_by: User UUID making the change
    """
    # Verify changer has permission
    changer_context = require_team_access(changed_by, team_id, Role.ADMIN)
    
    # Cannot change owner unless you're owner
    target_context = get_authorization_context(user_id, team_id)
    if target_context and target_context.role == Role.OWNER and not changer_context.is_owner():
        raise RoleError("Only owners can change owner roles")
    
    if new_role == Role.OWNER and not changer_context.is_owner():
        raise RoleError("Only owners can promote to owner")
    
    now = datetime.now(timezone.utc)
    
    query = """
        UPDATE team_memberships
        SET role = %s, updated_at = %s
        WHERE team_id = %s AND user_id = %s
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (new_role.value, now, team_id, user_id))
            
            if cur.rowcount == 0:
                raise TeamBoundaryError(f"User {user_id} not in team {team_id}")
        
        # CRITICAL: Revoke all sessions for affected user (Invariant #4)
        revoke_all_user_sessions(
            user_id=user_id,
            reason=RevocationReason.ROLE_CHANGE,
            actor_id=changed_by
        )
        
        logger.info(
            "Member role changed, sessions revoked",
            team_id=team_id,
            user_id=user_id,
            new_role=new_role.value,
            changed_by=changed_by
        )
        
    except (DatabaseError, AuthorizationError):
        raise
    except Exception as e:
        logger.error("Failed to change role", error=str(e))
        raise DatabaseError(f"Failed to change role: {e}")


def remove_team_member(
    team_id: str,
    user_id: str,
    removed_by: str
) -> None:
    """
    Remove a member from a team.
    
    Uses soft deactivation, not hard delete.
    
    Args:
        team_id: Team UUID
        user_id: User UUID to remove
        removed_by: User UUID doing the removal
    """
    remover_context = require_team_access(removed_by, team_id, Role.ADMIN)
    
    target_context = get_authorization_context(user_id, team_id)
    if target_context and target_context.role == Role.OWNER and not remover_context.is_owner():
        raise RoleError("Only owners can remove owners")
    
    now = datetime.now(timezone.utc)
    
    query = """
        UPDATE team_memberships
        SET is_active = false, updated_at = %s
        WHERE team_id = %s AND user_id = %s
    """
    
    try:
        with get_cursor() as cur:
            cur.execute(query, (now, team_id, user_id))
        
        # Revoke sessions for removed user's team access
        revoke_all_user_sessions(
            user_id=user_id,
            reason=RevocationReason.TEAM_CHANGE,
            actor_id=removed_by
        )
        
        logger.info(
            "Member removed from team",
            team_id=team_id,
            user_id=user_id,
            removed_by=removed_by
        )
        
    except (DatabaseError, AuthorizationError):
        raise
    except Exception as e:
        logger.error("Failed to remove member", error=str(e))
        raise DatabaseError(f"Failed to remove member: {e}")
