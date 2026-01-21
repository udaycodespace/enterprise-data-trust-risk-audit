-- ED-TRAIL Migration 002: Data Assets
-- Tracked data elements in the lineage graph

CREATE TABLE IF NOT EXISTS ed_trail_data_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Team isolation
    team_id UUID NOT NULL REFERENCES teams(id),
    
    -- Source reference
    source_id UUID REFERENCES ed_trail_data_sources(id),
    
    -- Asset identification
    name VARCHAR(255) NOT NULL,
    asset_type VARCHAR(50) NOT NULL, -- 'table', 'column', 'file', 'record', 'field'
    identifier VARCHAR(500), -- External identifier (table name, file path, etc.)
    
    -- Lineage metadata
    origin_unknown BOOLEAN NOT NULL DEFAULT false,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Audit fields
    created_by UUID NOT NULL REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(team_id, name, version)
);

CREATE INDEX IF NOT EXISTS idx_ed_trail_assets_team ON ed_trail_data_assets(team_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_assets_source ON ed_trail_data_assets(source_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_assets_type ON ed_trail_data_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_ed_trail_assets_origin ON ed_trail_data_assets(team_id) WHERE origin_unknown = true;

-- RLS Policy
ALTER TABLE ed_trail_data_assets ENABLE ROW LEVEL SECURITY;

CREATE POLICY ed_trail_assets_select ON ed_trail_data_assets
    FOR SELECT USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_assets_insert ON ed_trail_data_assets
    FOR INSERT WITH CHECK (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_assets_update ON ed_trail_data_assets
    FOR UPDATE USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true AND role IN ('owner', 'admin'))
    );
