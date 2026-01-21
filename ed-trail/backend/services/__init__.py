"""
ED-TRAIL Services Package
"""

from ed_trail.backend.services.data_sources import (
    DataSource,
    create_data_source,
    get_data_source,
    list_data_sources,
    update_last_seen,
)

from ed_trail.backend.services.data_assets import (
    DataAsset,
    create_data_asset,
    get_data_asset,
    list_data_assets,
)

from ed_trail.backend.services.lineage import (
    LineageEdge,
    create_lineage_edge,
    get_asset_lineage,
    validate_edge,
    would_create_cycle,
)

from ed_trail.backend.services.integrity import (
    IntegrityCheck,
    create_integrity_check,
    record_check_result,
    list_checks,
)

from ed_trail.backend.services.breaks import (
    BreakEvent,
    emit_break_event,
    resolve_break_event,
    list_break_events,
)

from ed_trail.backend.services.risk import (
    RiskScore,
    compute_risk_score,
    get_latest_score,
    list_scores_by_risk,
)
