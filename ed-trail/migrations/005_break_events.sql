-- ED-TRAIL Migration 005: Break Events
-- Detected integrity failures

CREATE TABLE IF NOT EXISTS ed_trail_break_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Team isolation
    team_id UUID NOT NULL REFERENCES teams(id),
    
    -- Break source
    check_id UUID REFERENCES ed_trail_integrity_checks(id),
    asset_id UUID REFERENCES ed_trail_data_assets(id),
    edge_id UUID REFERENCES ed_trail_lineage_edges(id),
    
    -- Break details
    break_type VARCHAR(50) NOT NULL, -- 'missing_source', 'data_mismatch', 'late_arrival', 'orphaned_asset', 'cycle_detected'
    severity VARCHAR(20) NOT NULL DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    
    -- Description
    title VARCHAR(255) NOT NULL,
    description TEXT,
    details JSONB,
    
    -- Financial impact (stored in paise for INR)
    impact_amount_paise BIGINT,
    currency VARCHAR(3) DEFAULT 'INR',
    
    -- Resolution
    status VARCHAR(20) NOT NULL DEFAULT 'open', -- 'open', 'investigating', 'resolved', 'dismissed'
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES auth.users(id),
    resolution_notes TEXT,
    
    -- Timing
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Audit fields
    created_by UUID NOT NULL REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ed_trail_breaks_team ON ed_trail_break_events(team_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_breaks_check ON ed_trail_break_events(check_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_breaks_asset ON ed_trail_break_events(asset_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_breaks_status ON ed_trail_break_events(status);
CREATE INDEX IF NOT EXISTS idx_ed_trail_breaks_severity ON ed_trail_break_events(severity);
CREATE INDEX IF NOT EXISTS idx_ed_trail_breaks_detected ON ed_trail_break_events(detected_at);

-- RLS Policy
ALTER TABLE ed_trail_break_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY ed_trail_breaks_select ON ed_trail_break_events
    FOR SELECT USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_breaks_insert ON ed_trail_break_events
    FOR INSERT WITH CHECK (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_breaks_update ON ed_trail_break_events
    FOR UPDATE USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true AND role IN ('owner', 'admin'))
    );
