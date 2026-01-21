-- ED-TRAIL Migration 001: Data Sources
-- Origin points for data lineage tracking

CREATE TABLE IF NOT EXISTS ed_trail_data_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Team isolation (inherits ED-BASE pattern)
    team_id UUID NOT NULL REFERENCES teams(id),
    
    -- Source identification
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL, -- 'database', 'api', 'file', 'stream', 'manual'
    
    -- Connection/location metadata
    connection_config JSONB DEFAULT '{}',
    
    -- Status tracking
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_seen_at TIMESTAMPTZ,
    
    -- Audit fields
    created_by UUID NOT NULL REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(team_id, name)
);

CREATE INDEX IF NOT EXISTS idx_ed_trail_sources_team ON ed_trail_data_sources(team_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_sources_type ON ed_trail_data_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_ed_trail_sources_active ON ed_trail_data_sources(team_id) WHERE is_active = true;

-- RLS Policy (team isolation)
ALTER TABLE ed_trail_data_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY ed_trail_sources_select ON ed_trail_data_sources
    FOR SELECT USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_sources_insert ON ed_trail_data_sources
    FOR INSERT WITH CHECK (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_sources_update ON ed_trail_data_sources
    FOR UPDATE USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true AND role IN ('owner', 'admin'))
    );
