"""
ED-TRAIL Lineage Edges Service
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
class LineageEdge:
    id: str
    team_id: str
    source_asset_id: str
    target_asset_id: str
    edge_type: str
    transformation_description: Optional[str]
    is_validated: bool
    validated_at: Optional[datetime]
    validated_by: Optional[str]
    is_active: bool
    created_by: str
    created_at: datetime


def would_create_cycle(team_id: str, source_asset_id: str, target_asset_id: str) -> bool:
    """Check if adding this edge would create a cycle."""
    query = """
        WITH RECURSIVE lineage AS (
            SELECT source_asset_id, target_asset_id, 1 as depth
            FROM ed_trail_lineage_edges
            WHERE team_id = %s AND target_asset_id = %s AND is_active = true
            
            UNION ALL
            
            SELECT e.source_asset_id, e.target_asset_id, l.depth + 1
            FROM ed_trail_lineage_edges e
            JOIN lineage l ON e.target_asset_id = l.source_asset_id
            WHERE e.team_id = %s AND e.is_active = true AND l.depth < 100
        )
        SELECT 1 FROM lineage WHERE source_asset_id = %s LIMIT 1
    """
    
    with get_cursor() as cur:
        cur.execute(query, (team_id, source_asset_id, team_id, target_asset_id))
        return cur.fetchone() is not None


def create_lineage_edge(
    team_id: str,
    user_id: str,
    source_asset_id: str,
    target_asset_id: str,
    edge_type: str,
    transformation_description: Optional[str] = None
) -> LineageEdge:
    """Link two data assets with a lineage edge."""
    require_team_access(user_id, team_id, Role.MEMBER)
    
    if source_asset_id == target_asset_id:
        raise ValueError("Cannot create self-loop edge")
    
    if would_create_cycle(team_id, source_asset_id, target_asset_id):
        raise ValueError("Edge would create cycle in lineage graph")
    
    query = """
        INSERT INTO ed_trail_lineage_edges (team_id, source_asset_id, target_asset_id, edge_type, transformation_description, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, team_id, source_asset_id, target_asset_id, edge_type, transformation_description,
                  is_validated, validated_at, validated_by, is_active, created_by, created_at
    """
    
    with transaction(IsolationLevel.REPEATABLE_READ) as cur:
        cur.execute(query, (team_id, source_asset_id, target_asset_id, edge_type, transformation_description, user_id))
        row = cur.fetchone()
        
        log_event(
            event_type=EventType.STATE_CREATE,
            action="Created lineage edge",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_lineage_edge",
            resource_id=row['id'],
            details={'source': source_asset_id, 'target': target_asset_id, 'edge_type': edge_type}
        )
        
        return LineageEdge(
            id=row['id'],
            team_id=row['team_id'],
            source_asset_id=row['source_asset_id'],
            target_asset_id=row['target_asset_id'],
            edge_type=row['edge_type'],
            transformation_description=row['transformation_description'],
            is_validated=row['is_validated'],
            validated_at=row['validated_at'],
            validated_by=row['validated_by'],
            is_active=row['is_active'],
            created_by=row['created_by'],
            created_at=row['created_at']
        )


def get_asset_lineage(team_id: str, user_id: str, asset_id: str, direction: str = 'upstream') -> List[LineageEdge]:
    """Get lineage edges for an asset (upstream or downstream)."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    if direction == 'upstream':
        query = """
            SELECT id, team_id, source_asset_id, target_asset_id, edge_type, transformation_description,
                   is_validated, validated_at, validated_by, is_active, created_by, created_at
            FROM ed_trail_lineage_edges
            WHERE team_id = %s AND target_asset_id = %s AND is_active = true
        """
    else:
        query = """
            SELECT id, team_id, source_asset_id, target_asset_id, edge_type, transformation_description,
                   is_validated, validated_at, validated_by, is_active, created_by, created_at
            FROM ed_trail_lineage_edges
            WHERE team_id = %s AND source_asset_id = %s AND is_active = true
        """
    
    with get_cursor() as cur:
        cur.execute(query, (team_id, asset_id))
        rows = cur.fetchall()
        return [
            LineageEdge(
                id=row['id'],
                team_id=row['team_id'],
                source_asset_id=row['source_asset_id'],
                target_asset_id=row['target_asset_id'],
                edge_type=row['edge_type'],
                transformation_description=row['transformation_description'],
                is_validated=row['is_validated'],
                validated_at=row['validated_at'],
                validated_by=row['validated_by'],
                is_active=row['is_active'],
                created_by=row['created_by'],
                created_at=row['created_at']
            )
            for row in rows
        ]


def validate_edge(team_id: str, user_id: str, edge_id: str) -> bool:
    """Mark an edge as validated."""
    require_team_access(user_id, team_id, Role.ADMIN)
    
    query = """
        UPDATE ed_trail_lineage_edges
        SET is_validated = true, validated_at = %s, validated_by = %s, updated_at = %s
        WHERE id = %s AND team_id = %s
    """
    
    now = datetime.now(timezone.utc)
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(query, (now, user_id, now, edge_id, team_id))
        if cur.rowcount == 0:
            return False
        
        log_event(
            event_type=EventType.STATE_UPDATE,
            action="Validated lineage edge",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_lineage_edge",
            resource_id=edge_id
        )
        return True
