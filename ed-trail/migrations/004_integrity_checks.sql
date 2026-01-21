-- ED-TRAIL Migration 004: Integrity Checks
-- Validation rules for data integrity monitoring

CREATE TABLE IF NOT EXISTS ed_trail_integrity_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Team isolation
    team_id UUID NOT NULL REFERENCES teams(id),
    
    -- Check target
    asset_id UUID REFERENCES ed_trail_data_assets(id),
    edge_id UUID REFERENCES ed_trail_lineage_edges(id),
    
    -- Check definition
    name VARCHAR(255) NOT NULL,
    check_type VARCHAR(50) NOT NULL, -- 'completeness', 'timeliness', 'accuracy', 'consistency'
    rule_definition JSONB NOT NULL,
    
    -- Scheduling
    frequency_minutes INTEGER, -- NULL = manual only
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    
    -- Results
    last_result VARCHAR(20), -- 'pass', 'fail', 'warning', 'error'
    last_result_details JSONB,
    
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Audit fields
    created_by UUID NOT NULL REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(team_id, name),
    
    -- Must have either asset or edge target
    CONSTRAINT has_target CHECK (asset_id IS NOT NULL OR edge_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_ed_trail_checks_team ON ed_trail_integrity_checks(team_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_checks_asset ON ed_trail_integrity_checks(asset_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_checks_edge ON ed_trail_integrity_checks(edge_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_checks_next_run ON ed_trail_integrity_checks(next_run_at) WHERE is_active = true;

-- RLS Policy
ALTER TABLE ed_trail_integrity_checks ENABLE ROW LEVEL SECURITY;

CREATE POLICY ed_trail_checks_select ON ed_trail_integrity_checks
    FOR SELECT USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_checks_insert ON ed_trail_integrity_checks
    FOR INSERT WITH CHECK (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_checks_update ON ed_trail_integrity_checks
    FOR UPDATE USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true AND role IN ('owner', 'admin'))
    );
