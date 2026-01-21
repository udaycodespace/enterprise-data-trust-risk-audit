"""
ED-TRAIL Break Events Service
Uses ED-BASE services unchanged.
"""

from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass
import structlog
import json

import sys
sys.path.insert(0, '../../../backend')

from utils import get_cursor, DatabaseError
from services import (
    transaction,
    IsolationLevel,
    log_event,
    EventType,
    ActorType,
    require_team_access,
    Role,
)
from ed_trail.backend.utils.currency import rupees_to_paise

logger = structlog.get_logger(__name__)


@dataclass
class BreakEvent:
    id: str
    team_id: str
    check_id: Optional[str]
    asset_id: Optional[str]
    edge_id: Optional[str]
    break_type: str
    severity: str
    title: str
    description: Optional[str]
    details: Optional[dict]
    impact_amount_paise: Optional[int]
    currency: str
    status: str
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]
    resolution_notes: Optional[str]
    detected_at: datetime
    created_by: str
    created_at: datetime


def emit_break_event(
    team_id: str,
    user_id: str,
    break_type: str,
    title: str,
    severity: str = 'medium',
    description: Optional[str] = None,
    details: Optional[dict] = None,
    check_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    edge_id: Optional[str] = None,
    impact_amount_rupees: Optional[float] = None
) -> BreakEvent:
    """Emit a new break event."""
    require_team_access(user_id, team_id, Role.MEMBER)
    
    impact_paise = None
    if impact_amount_rupees is not None:
        impact_paise = rupees_to_paise(impact_amount_rupees)
    
    query = """
        INSERT INTO ed_trail_break_events (
            team_id, check_id, asset_id, edge_id, break_type, severity,
            title, description, details, impact_amount_paise, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, team_id, check_id, asset_id, edge_id, break_type, severity,
                  title, description, details, impact_amount_paise, currency, status,
                  resolved_at, resolved_by, resolution_notes, detected_at, created_by, created_at
    """
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(query, (
            team_id, check_id, asset_id, edge_id, break_type, severity,
            title, description, json.dumps(details) if details else None, impact_paise, user_id
        ))
        row = cur.fetchone()
        
        log_event(
            event_type=EventType.STATE_CREATE,
            action="Emitted break event",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_break_event",
            resource_id=row['id'],
            details={'break_type': break_type, 'severity': severity, 'title': title}
        )
        
        return BreakEvent(
            id=row['id'],
            team_id=row['team_id'],
            check_id=row['check_id'],
            asset_id=row['asset_id'],
            edge_id=row['edge_id'],
            break_type=row['break_type'],
            severity=row['severity'],
            title=row['title'],
            description=row['description'],
            details=row['details'],
            impact_amount_paise=row['impact_amount_paise'],
            currency=row['currency'],
            status=row['status'],
            resolved_at=row['resolved_at'],
            resolved_by=row['resolved_by'],
            resolution_notes=row['resolution_notes'],
            detected_at=row['detected_at'],
            created_by=row['created_by'],
            created_at=row['created_at']
        )


def resolve_break_event(
    team_id: str,
    user_id: str,
    event_id: str,
    resolution_notes: Optional[str] = None
) -> bool:
    """Resolve a break event."""
    require_team_access(user_id, team_id, Role.ADMIN)
    
    now = datetime.now(timezone.utc)
    
    query = """
        UPDATE ed_trail_break_events
        SET status = 'resolved', resolved_at = %s, resolved_by = %s, resolution_notes = %s, updated_at = %s
        WHERE id = %s AND team_id = %s AND status != 'resolved'
    """
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(query, (now, user_id, resolution_notes, now, event_id, team_id))
        if cur.rowcount == 0:
            return False
        
        log_event(
            event_type=EventType.STATE_UPDATE,
            action="Resolved break event",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_break_event",
            resource_id=event_id,
            details={'resolution_notes': resolution_notes}
        )
        return True


def list_break_events(
    team_id: str,
    user_id: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50
) -> List[BreakEvent]:
    """List break events for a team."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT id, team_id, check_id, asset_id, edge_id, break_type, severity,
               title, description, details, impact_amount_paise, currency, status,
               resolved_at, resolved_by, resolution_notes, detected_at, created_by, created_at
        FROM ed_trail_break_events
        WHERE team_id = %s
    """
    params = [team_id]
    
    if status:
        query += " AND status = %s"
        params.append(status)
    
    if severity:
        query += " AND severity = %s"
        params.append(severity)
    
    query += " ORDER BY detected_at DESC LIMIT %s"
    params.append(limit)
    
    with get_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            BreakEvent(
                id=row['id'],
                team_id=row['team_id'],
                check_id=row['check_id'],
                asset_id=row['asset_id'],
                edge_id=row['edge_id'],
                break_type=row['break_type'],
                severity=row['severity'],
                title=row['title'],
                description=row['description'],
                details=row['details'],
                impact_amount_paise=row['impact_amount_paise'],
                currency=row['currency'],
                status=row['status'],
                resolved_at=row['resolved_at'],
                resolved_by=row['resolved_by'],
                resolution_notes=row['resolution_notes'],
                detected_at=row['detected_at'],
                created_by=row['created_by'],
                created_at=row['created_at']
            )
            for row in rows
        ]
