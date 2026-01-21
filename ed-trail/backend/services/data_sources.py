"""
ED-TRAIL Data Sources Service
Uses ED-BASE services unchanged.
"""

from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass
import structlog

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
class DataSource:
    id: str
    team_id: str
    name: str
    source_type: str
    connection_config: dict
    is_active: bool
    last_seen_at: Optional[datetime]
    created_by: str
    created_at: datetime


def create_data_source(
    team_id: str,
    user_id: str,
    name: str,
    source_type: str,
    connection_config: Optional[dict] = None
) -> DataSource:
    """Create a new data source."""
    require_team_access(user_id, team_id, Role.MEMBER)
    
    query = """
        INSERT INTO ed_trail_data_sources (team_id, name, source_type, connection_config, created_by)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, team_id, name, source_type, connection_config, is_active, last_seen_at, created_by, created_at
    """
    
    import json
    config_json = json.dumps(connection_config or {})
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(query, (team_id, name, source_type, config_json, user_id))
        row = cur.fetchone()
        
        log_event(
            event_type=EventType.STATE_CREATE,
            action="Created data source",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_data_source",
            resource_id=row['id'],
            details={'name': name, 'source_type': source_type}
        )
        
        return DataSource(
            id=row['id'],
            team_id=row['team_id'],
            name=row['name'],
            source_type=row['source_type'],
            connection_config=row['connection_config'] or {},
            is_active=row['is_active'],
            last_seen_at=row['last_seen_at'],
            created_by=row['created_by'],
            created_at=row['created_at']
        )


def get_data_source(source_id: str, team_id: str, user_id: str) -> Optional[DataSource]:
    """Get data source by ID."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT id, team_id, name, source_type, connection_config, is_active, last_seen_at, created_by, created_at
        FROM ed_trail_data_sources
        WHERE id = %s AND team_id = %s
    """
    
    with get_cursor() as cur:
        cur.execute(query, (source_id, team_id))
        row = cur.fetchone()
        if not row:
            return None
        return DataSource(
            id=row['id'],
            team_id=row['team_id'],
            name=row['name'],
            source_type=row['source_type'],
            connection_config=row['connection_config'] or {},
            is_active=row['is_active'],
            last_seen_at=row['last_seen_at'],
            created_by=row['created_by'],
            created_at=row['created_at']
        )


def list_data_sources(team_id: str, user_id: str, active_only: bool = True) -> List[DataSource]:
    """List all data sources for a team."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT id, team_id, name, source_type, connection_config, is_active, last_seen_at, created_by, created_at
        FROM ed_trail_data_sources
        WHERE team_id = %s
    """
    if active_only:
        query += " AND is_active = true"
    query += " ORDER BY created_at DESC"
    
    with get_cursor() as cur:
        cur.execute(query, (team_id,))
        rows = cur.fetchall()
        return [
            DataSource(
                id=row['id'],
                team_id=row['team_id'],
                name=row['name'],
                source_type=row['source_type'],
                connection_config=row['connection_config'] or {},
                is_active=row['is_active'],
                last_seen_at=row['last_seen_at'],
                created_by=row['created_by'],
                created_at=row['created_at']
            )
            for row in rows
        ]


def update_last_seen(source_id: str, team_id: str) -> None:
    """Update last seen timestamp for a data source."""
    query = """
        UPDATE ed_trail_data_sources
        SET last_seen_at = %s, updated_at = %s
        WHERE id = %s AND team_id = %s
    """
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute(query, (now, now, source_id, team_id))
