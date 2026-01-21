"""
ED-TRAIL Risk Scores Service
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
from ed_trail.backend.utils.currency import rupees_to_paise

logger = structlog.get_logger(__name__)


@dataclass
class RiskScore:
    id: str
    team_id: str
    asset_id: str
    overall_score: int
    completeness_score: Optional[int]
    timeliness_score: Optional[int]
    accuracy_score: Optional[int]
    score_factors: dict
    previous_score: Optional[int]
    score_change: Optional[int]
    exposure_amount_paise: Optional[int]
    currency: str
    computed_at: datetime
    valid_until: Optional[datetime]


def compute_risk_score(
    team_id: str,
    user_id: str,
    asset_id: str,
    overall_score: int,
    completeness_score: Optional[int] = None,
    timeliness_score: Optional[int] = None,
    accuracy_score: Optional[int] = None,
    score_factors: Optional[dict] = None,
    exposure_amount_rupees: Optional[float] = None,
    valid_hours: int = 24
) -> RiskScore:
    """Store a computed risk score for an asset."""
    require_team_access(user_id, team_id, Role.MEMBER)
    
    if overall_score < 0 or overall_score > 100:
        raise ValueError("Score must be between 0 and 100")
    
    exposure_paise = None
    if exposure_amount_rupees is not None:
        exposure_paise = rupees_to_paise(exposure_amount_rupees)
    
    previous_query = """
        SELECT overall_score FROM ed_trail_risk_scores
        WHERE team_id = %s AND asset_id = %s
        ORDER BY computed_at DESC LIMIT 1
    """
    
    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(hours=valid_hours)
    
    with transaction(IsolationLevel.READ_COMMITTED) as cur:
        cur.execute(previous_query, (team_id, asset_id))
        prev_row = cur.fetchone()
        
        previous_score = prev_row['overall_score'] if prev_row else None
        score_change = (overall_score - previous_score) if previous_score is not None else None
        
        insert_query = """
            INSERT INTO ed_trail_risk_scores (
                team_id, asset_id, overall_score, completeness_score, timeliness_score,
                accuracy_score, score_factors, previous_score, score_change,
                exposure_amount_paise, valid_until
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, team_id, asset_id, overall_score, completeness_score, timeliness_score,
                      accuracy_score, score_factors, previous_score, score_change,
                      exposure_amount_paise, currency, computed_at, valid_until
        """
        
        cur.execute(insert_query, (
            team_id, asset_id, overall_score, completeness_score, timeliness_score,
            accuracy_score, json.dumps(score_factors or {}), previous_score, score_change,
            exposure_paise, valid_until
        ))
        row = cur.fetchone()
        
        log_event(
            event_type=EventType.STATE_CREATE,
            action="Computed risk score",
            actor_id=user_id,
            actor_type=ActorType.USER,
            resource_type="ed_trail_risk_score",
            resource_id=row['id'],
            details={'asset_id': asset_id, 'overall_score': overall_score, 'change': score_change}
        )
        
        return RiskScore(
            id=row['id'],
            team_id=row['team_id'],
            asset_id=row['asset_id'],
            overall_score=row['overall_score'],
            completeness_score=row['completeness_score'],
            timeliness_score=row['timeliness_score'],
            accuracy_score=row['accuracy_score'],
            score_factors=row['score_factors'] or {},
            previous_score=row['previous_score'],
            score_change=row['score_change'],
            exposure_amount_paise=row['exposure_amount_paise'],
            currency=row['currency'],
            computed_at=row['computed_at'],
            valid_until=row['valid_until']
        )


def get_latest_score(team_id: str, user_id: str, asset_id: str) -> Optional[RiskScore]:
    """Get the latest risk score for an asset."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT id, team_id, asset_id, overall_score, completeness_score, timeliness_score,
               accuracy_score, score_factors, previous_score, score_change,
               exposure_amount_paise, currency, computed_at, valid_until
        FROM ed_trail_risk_scores
        WHERE team_id = %s AND asset_id = %s
        ORDER BY computed_at DESC LIMIT 1
    """
    
    with get_cursor() as cur:
        cur.execute(query, (team_id, asset_id))
        row = cur.fetchone()
        if not row:
            return None
        return RiskScore(
            id=row['id'],
            team_id=row['team_id'],
            asset_id=row['asset_id'],
            overall_score=row['overall_score'],
            completeness_score=row['completeness_score'],
            timeliness_score=row['timeliness_score'],
            accuracy_score=row['accuracy_score'],
            score_factors=row['score_factors'] or {},
            previous_score=row['previous_score'],
            score_change=row['score_change'],
            exposure_amount_paise=row['exposure_amount_paise'],
            currency=row['currency'],
            computed_at=row['computed_at'],
            valid_until=row['valid_until']
        )


def list_scores_by_risk(team_id: str, user_id: str, min_score: int = 0, limit: int = 50) -> List[RiskScore]:
    """List assets sorted by risk score (highest first)."""
    require_team_access(user_id, team_id, Role.VIEWER)
    
    query = """
        SELECT DISTINCT ON (asset_id)
            id, team_id, asset_id, overall_score, completeness_score, timeliness_score,
            accuracy_score, score_factors, previous_score, score_change,
            exposure_amount_paise, currency, computed_at, valid_until
        FROM ed_trail_risk_scores
        WHERE team_id = %s AND overall_score >= %s
        ORDER BY asset_id, computed_at DESC
    """
    
    with get_cursor() as cur:
        cur.execute(query, (team_id, min_score))
        rows = cur.fetchall()
        scores = [
            RiskScore(
                id=row['id'],
                team_id=row['team_id'],
                asset_id=row['asset_id'],
                overall_score=row['overall_score'],
                completeness_score=row['completeness_score'],
                timeliness_score=row['timeliness_score'],
                accuracy_score=row['accuracy_score'],
                score_factors=row['score_factors'] or {},
                previous_score=row['previous_score'],
                score_change=row['score_change'],
                exposure_amount_paise=row['exposure_amount_paise'],
                currency=row['currency'],
                computed_at=row['computed_at'],
                valid_until=row['valid_until']
            )
            for row in rows
        ]
        scores.sort(key=lambda s: s.overall_score, reverse=True)
        return scores[:limit]
