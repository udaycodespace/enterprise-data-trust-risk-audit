"""
ED-TRAIL Integrity Checks Service
Uses ED-BASE services unchanged.
"""

from datetime import datetime, timezone, timedelta
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

logger = structlog.get_logger(__name__)


@dataclass
class IntegrityCheck:
    id: str
    team_id: str
    asset_id: Optional[str]
    edge_id: Optional[str]
    name: str
    check_type: str
    rule_definition: dict
    frequency_minutes: Optional[int]
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_result: Optional[str]
    last_result_details: Optional[dict]
    is_active: bool
    created_by: str
    created_at: datetime


def create_integrity_check(
    team_id: str,
    user_id: str,
    name: str,
    check_type: str,
    rule_definition: dict,
    asset_id: Optional[str] = None,
    edge_id: Optional[str] = None,
    frequency_minutes: Optional[int] = None
) -> IntegrityCheck:
    """Record a new integrity check."""
    require_team_access(user_id, team_id, Role.MEMBER)
    
    if not asset_id and not edge_id:
        raise ValueError("Must specify either asset_id or edge_id")
    
    next_run = None
    if frequency_minutes:
        next_run = datetime.now(timezone.utc) + timedelta(minutes=frequency_minutes)
    
    query = """
        INSERT INTO ed_trail_integrity_checks (
            team_id, asset_id, edge_id, name, check_type, rule_definition,
            frequency_minutes, next_run_at, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, team_id, asset_id, edge_id, name, check_type, rule_definition,
                  frequency_minutes, last_run_at, next_run_at, last_result, last_result_details,
                  is_active, created_by, created_at
    """
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(query, (
            team_id, asset_id, edge_id, name, check_type, json.dumps(rule_definition),
            frequency_minutes, next_run, user_id
        ))
        row = cur.fetchone()
        
        log_event(
            event_type=EventType.STATE_CREATE,
            action="Created integrity check",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_integrity_check",
            resource_id=row['id'],
            details={'name': name, 'check_type': check_type}
        )
        
        return IntegrityCheck(
            id=row['id'],
            team_id=row['team_id'],
            asset_id=row['asset_id'],
            edge_id=row['edge_id'],
            name=row['name'],
            check_type=row['check_type'],
            rule_definition=row['rule_definition'],
            frequency_minutes=row['frequency_minutes'],
            last_run_at=row['last_run_at'],
            next_run_at=row['next_run_at'],
            last_result=row['last_result'],
            last_result_details=row['last_result_details'],
            is_active=row['is_active'],
            created_by=row['created_by'],
            created_at=row['created_at']
        )


def record_check_result(
    check_id: str,
    team_id: str,
    result: str,
    result_details: Optional[dict] = None
) -> None:
    """Record the result of an integrity check run."""
    now = datetime.now(timezone.utc)
    
    query = """
        UPDATE ed_trail_integrity_checks
        SET last_run_at = %s,
            last_result = %s,
            last_result_details = %s,
            next_run_at = CASE 
                WHEN frequency_minutes IS NOT NULL 
                THEN %s + (frequency_minutes * interval '1 minute')
                ELSE NULL
            END,
            updated_at = %s
        WHERE id = %s AND team_id = %s
    """
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(query, (
            now, result, json.dumps(result_details) if result_details else None,
            now, now, check_id, team_id
        ))


def list_checks(
    team_id: str,
    user_id: str,
    asset_id: Optional[str] = None,
    failed_only: bool = False
) -> List[IntegrityCheck]:
    """List integrity checks for a team."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT id, team_id, asset_id, edge_id, name, check_type, rule_definition,
               frequency_minutes, last_run_at, next_run_at, last_result, last_result_details,
               is_active, created_by, created_at
        FROM ed_trail_integrity_checks
        WHERE team_id = %s AND is_active = true
    """
    params = [team_id]
    
    if asset_id:
        query += " AND asset_id = %s"
        params.append(asset_id)
    
    if failed_only:
        query += " AND last_result IN ('fail', 'error')"
    
    query += " ORDER BY created_at DESC"
    
    with get_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            IntegrityCheck(
                id=row['id'],
                team_id=row['team_id'],
                asset_id=row['asset_id'],
                edge_id=row['edge_id'],
                name=row['name'],
                check_type=row['check_type'],
                rule_definition=row['rule_definition'],
                frequency_minutes=row['frequency_minutes'],
                last_run_at=row['last_run_at'],
                next_run_at=row['next_run_at'],
                last_result=row['last_result'],
                last_result_details=row['last_result_details'],
                is_active=row['is_active'],
                created_by=row['created_by'],
                created_at=row['created_at']
            )
            for row in rows
        ]
