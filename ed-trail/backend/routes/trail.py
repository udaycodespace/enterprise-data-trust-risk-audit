"""
ED-TRAIL API Routes
Uses ED-BASE middleware unchanged.
"""

from flask import Blueprint, request, jsonify, g
import structlog

import sys
sys.path.insert(0, '../../../backend')

from middleware import require_auth, require_team, safe_handler, rate_limit
from services import IdempotencyContext
from ed_trail.backend.services import (
    create_data_source, get_data_source, list_data_sources,
    create_data_asset, get_data_asset, list_data_assets,
    create_lineage_edge, get_asset_lineage, validate_edge,
    create_integrity_check, list_checks,
    emit_break_event, resolve_break_event, list_break_events,
    compute_risk_score, get_latest_score, list_scores_by_risk,
)
from ed_trail.backend.utils.currency import paise_to_rupees, format_inr

logger = structlog.get_logger(__name__)

trail_bp = Blueprint('trail', __name__, url_prefix='/api/trail')


# ============ DATA SOURCES ============

@trail_bp.route('/sources', methods=['POST'])
@require_auth
@require_team()
@rate_limit()
@safe_handler
def create_source():
    data = request.get_json() or {}
    
    idempotency_key = request.headers.get('Idempotency-Key')
    if idempotency_key:
        with IdempotencyContext(idempotency_key, g.user_id, request.get_data()) as ctx:
            if not ctx.should_process:
                return jsonify(ctx.response)
            
            source = create_data_source(
                team_id=g.team_id,
                user_id=g.user_id,
                name=data.get('name'),
                source_type=data.get('source_type'),
                connection_config=data.get('connection_config')
            )
            ctx.set_response({'id': source.id})
    else:
        source = create_data_source(
            team_id=g.team_id,
            user_id=g.user_id,
            name=data.get('name'),
            source_type=data.get('source_type'),
            connection_config=data.get('connection_config')
        )
    
    return jsonify({'id': source.id, 'name': source.name}), 201


@trail_bp.route('/sources', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_sources():
    sources = list_data_sources(g.team_id, g.user_id)
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'source_type': s.source_type,
        'is_active': s.is_active,
        'last_seen_at': s.last_seen_at.isoformat() if s.last_seen_at else None
    } for s in sources])


@trail_bp.route('/sources/<source_id>', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_source(source_id):
    source = get_data_source(source_id, g.team_id, g.user_id)
    if not source:
        return jsonify({'error': 'Source not found'}), 404
    return jsonify({
        'id': source.id,
        'name': source.name,
        'source_type': source.source_type,
        'connection_config': source.connection_config,
        'is_active': source.is_active,
        'last_seen_at': source.last_seen_at.isoformat() if source.last_seen_at else None,
        'created_at': source.created_at.isoformat()
    })


# ============ DATA ASSETS ============

@trail_bp.route('/assets', methods=['POST'])
@require_auth
@require_team()
@rate_limit()
@safe_handler
def create_asset():
    data = request.get_json() or {}
    
    asset = create_data_asset(
        team_id=g.team_id,
        user_id=g.user_id,
        name=data.get('name'),
        asset_type=data.get('asset_type'),
        source_id=data.get('source_id'),
        identifier=data.get('identifier')
    )
    
    return jsonify({'id': asset.id, 'name': asset.name}), 201


@trail_bp.route('/assets', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_assets():
    source_id = request.args.get('source_id')
    orphans_only = request.args.get('orphans_only', 'false').lower() == 'true'
    
    assets = list_data_assets(g.team_id, g.user_id, source_id=source_id, orphans_only=orphans_only)
    return jsonify([{
        'id': a.id,
        'name': a.name,
        'asset_type': a.asset_type,
        'source_id': a.source_id,
        'origin_unknown': a.origin_unknown,
        'version': a.version
    } for a in assets])


# ============ LINEAGE EDGES ============

@trail_bp.route('/edges', methods=['POST'])
@require_auth
@require_team()
@rate_limit()
@safe_handler
def create_edge():
    data = request.get_json() or {}
    
    try:
        edge = create_lineage_edge(
            team_id=g.team_id,
            user_id=g.user_id,
            source_asset_id=data.get('source_asset_id'),
            target_asset_id=data.get('target_asset_id'),
            edge_type=data.get('edge_type'),
            transformation_description=data.get('transformation_description')
        )
        return jsonify({'id': edge.id}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@trail_bp.route('/assets/<asset_id>/lineage', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_lineage(asset_id):
    direction = request.args.get('direction', 'upstream')
    edges = get_asset_lineage(g.team_id, g.user_id, asset_id, direction)
    return jsonify([{
        'id': e.id,
        'source_asset_id': e.source_asset_id,
        'target_asset_id': e.target_asset_id,
        'edge_type': e.edge_type,
        'transformation_description': e.transformation_description,
        'is_validated': e.is_validated
    } for e in edges])


@trail_bp.route('/edges/<edge_id>/validate', methods=['POST'])
@require_auth
@require_team()
@safe_handler
def validate_lineage_edge(edge_id):
    success = validate_edge(g.team_id, g.user_id, edge_id)
    if not success:
        return jsonify({'error': 'Edge not found'}), 404
    return jsonify({'validated': True})


# ============ INTEGRITY CHECKS ============

@trail_bp.route('/checks', methods=['POST'])
@require_auth
@require_team()
@rate_limit()
@safe_handler
def create_check():
    data = request.get_json() or {}
    
    check = create_integrity_check(
        team_id=g.team_id,
        user_id=g.user_id,
        name=data.get('name'),
        check_type=data.get('check_type'),
        rule_definition=data.get('rule_definition', {}),
        asset_id=data.get('asset_id'),
        edge_id=data.get('edge_id'),
        frequency_minutes=data.get('frequency_minutes')
    )
    
    return jsonify({'id': check.id, 'name': check.name}), 201


@trail_bp.route('/checks', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_checks():
    asset_id = request.args.get('asset_id')
    failed_only = request.args.get('failed_only', 'false').lower() == 'true'
    
    checks = list_checks(g.team_id, g.user_id, asset_id=asset_id, failed_only=failed_only)
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'check_type': c.check_type,
        'asset_id': c.asset_id,
        'last_result': c.last_result,
        'next_run_at': c.next_run_at.isoformat() if c.next_run_at else None
    } for c in checks])


# ============ BREAK EVENTS ============

@trail_bp.route('/breaks', methods=['POST'])
@require_auth
@require_team()
@rate_limit()
@safe_handler
def create_break():
    data = request.get_json() or {}
    
    event = emit_break_event(
        team_id=g.team_id,
        user_id=g.user_id,
        break_type=data.get('break_type'),
        title=data.get('title'),
        severity=data.get('severity', 'medium'),
        description=data.get('description'),
        details=data.get('details'),
        check_id=data.get('check_id'),
        asset_id=data.get('asset_id'),
        edge_id=data.get('edge_id'),
        impact_amount_rupees=data.get('impact_amount_rupees')
    )
    
    return jsonify({'id': event.id, 'title': event.title}), 201


@trail_bp.route('/breaks', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_breaks():
    status = request.args.get('status')
    severity = request.args.get('severity')
    
    events = list_break_events(g.team_id, g.user_id, status=status, severity=severity)
    return jsonify([{
        'id': e.id,
        'break_type': e.break_type,
        'severity': e.severity,
        'title': e.title,
        'status': e.status,
        'impact_amount_display': format_inr(e.impact_amount_paise) if e.impact_amount_paise else None,
        'detected_at': e.detected_at.isoformat()
    } for e in events])


@trail_bp.route('/breaks/<event_id>/resolve', methods=['POST'])
@require_auth
@require_team()
@safe_handler
def resolve_break(event_id):
    data = request.get_json() or {}
    
    success = resolve_break_event(
        team_id=g.team_id,
        user_id=g.user_id,
        event_id=event_id,
        resolution_notes=data.get('resolution_notes')
    )
    
    if not success:
        return jsonify({'error': 'Event not found or already resolved'}), 404
    return jsonify({'resolved': True})


# ============ RISK SCORES ============

@trail_bp.route('/scores', methods=['POST'])
@require_auth
@require_team()
@rate_limit()
@safe_handler
def store_score():
    data = request.get_json() or {}
    
    score = compute_risk_score(
        team_id=g.team_id,
        user_id=g.user_id,
        asset_id=data.get('asset_id'),
        overall_score=data.get('overall_score'),
        completeness_score=data.get('completeness_score'),
        timeliness_score=data.get('timeliness_score'),
        accuracy_score=data.get('accuracy_score'),
        score_factors=data.get('score_factors'),
        exposure_amount_rupees=data.get('exposure_amount_rupees')
    )
    
    return jsonify({
        'id': score.id,
        'overall_score': score.overall_score,
        'score_change': score.score_change
    }), 201


@trail_bp.route('/assets/<asset_id>/score', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_asset_score(asset_id):
    score = get_latest_score(g.team_id, g.user_id, asset_id)
    if not score:
        return jsonify({'error': 'No score found'}), 404
    return jsonify({
        'id': score.id,
        'overall_score': score.overall_score,
        'completeness_score': score.completeness_score,
        'timeliness_score': score.timeliness_score,
        'accuracy_score': score.accuracy_score,
        'score_change': score.score_change,
        'exposure_display': format_inr(score.exposure_amount_paise) if score.exposure_amount_paise else None,
        'computed_at': score.computed_at.isoformat()
    })


@trail_bp.route('/scores/high-risk', methods=['GET'])
@require_auth
@require_team()
@safe_handler
def get_high_risk():
    min_score = int(request.args.get('min_score', 50))
    scores = list_scores_by_risk(g.team_id, g.user_id, min_score=min_score)
    return jsonify([{
        'asset_id': s.asset_id,
        'overall_score': s.overall_score,
        'score_change': s.score_change,
        'exposure_display': format_inr(s.exposure_amount_paise) if s.exposure_amount_paise else None
    } for s in scores])
