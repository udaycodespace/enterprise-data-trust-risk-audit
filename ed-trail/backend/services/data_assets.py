"""
ED-TRAIL Data Assets Service
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
class DataAsset:
    id: str
    team_id: str
    source_id: Optional[str]
    name: str
    asset_type: str
    identifier: Optional[str]
    origin_unknown: bool
    version: int
    is_active: bool
    created_by: str
    created_at: datetime


def create_data_asset(
    team_id: str,
    user_id: str,
    name: str,
    asset_type: str,
    source_id: Optional[str] = None,
    identifier: Optional[str] = None
) -> DataAsset:
    """Register a new data asset."""
    require_team_access(user_id, team_id, Role.MEMBER)
    
    origin_unknown = source_id is None
    
    query = """
        INSERT INTO ed_trail_data_assets (team_id, source_id, name, asset_type, identifier, origin_unknown, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, team_id, source_id, name, asset_type, identifier, origin_unknown, version, is_active, created_by, created_at
    """
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(query, (team_id, source_id, name, asset_type, identifier, origin_unknown, user_id))
        row = cur.fetchone()
        
        log_event(
            event_type=EventType.STATE_CREATE,
            action="Registered data asset",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_data_asset",
            resource_id=row['id'],
            details={'name': name, 'asset_type': asset_type, 'origin_unknown': origin_unknown}
        )
        
        return DataAsset(
            id=row['id'],
            team_id=row['team_id'],
            source_id=row['source_id'],
            name=row['name'],
            asset_type=row['asset_type'],
            identifier=row['identifier'],
            origin_unknown=row['origin_unknown'],
            version=row['version'],
            is_active=row['is_active'],
            created_by=row['created_by'],
            created_at=row['created_at']
        )


def get_data_asset(asset_id: str, team_id: str, user_id: str) -> Optional[DataAsset]:
    """Get data asset by ID."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT id, team_id, source_id, name, asset_type, identifier, origin_unknown, version, is_active, created_by, created_at
        FROM ed_trail_data_assets
        WHERE id = %s AND team_id = %s
    """
    
    with get_cursor() as cur:
        cur.execute(query, (asset_id, team_id))
        row = cur.fetchone()
        if not row:
            return None
        return DataAsset(
            id=row['id'],
            team_id=row['team_id'],
            source_id=row['source_id'],
            name=row['name'],
            asset_type=row['asset_type'],
            identifier=row['identifier'],
            origin_unknown=row['origin_unknown'],
            version=row['version'],
            is_active=row['is_active'],
            created_by=row['created_by'],
            created_at=row['created_at']
        )


def list_data_assets(
    team_id: str,
    user_id: str,
    source_id: Optional[str] = None,
    orphans_only: bool = False
) -> List[DataAsset]:
    """List data assets for a team."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT id, team_id, source_id, name, asset_type, identifier, origin_unknown, version, is_active, created_by, created_at
        FROM ed_trail_data_assets
        WHERE team_id = %s AND is_active = true
    """
    params = [team_id]
    
    if source_id:
        query += " AND source_id = %s"
        params.append(source_id)
    
    if orphans_only:
        query += " AND origin_unknown = true"
    
    query += " ORDER BY created_at DESC"
    
    with get_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            DataAsset(
                id=row['id'],
                team_id=row['team_id'],
                source_id=row['source_id'],
                name=row['name'],
                asset_type=row['asset_type'],
                identifier=row['identifier'],
                origin_unknown=row['origin_unknown'],
                version=row['version'],
                is_active=row['is_active'],
                created_by=row['created_by'],
                created_at=row['created_at']
            )
            for row in rows
        ]
