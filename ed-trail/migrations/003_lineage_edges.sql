-- ED-TRAIL Migration 003: Lineage Edges
-- Connections between data assets forming the lineage graph

CREATE TABLE IF NOT EXISTS ed_trail_lineage_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Team isolation
    team_id UUID NOT NULL REFERENCES teams(id),
    
    -- Edge endpoints
    source_asset_id UUID NOT NULL REFERENCES ed_trail_data_assets(id),
    target_asset_id UUID NOT NULL REFERENCES ed_trail_data_assets(id),
    
    -- Edge metadata
    edge_type VARCHAR(50) NOT NULL, -- 'derives_from', 'transforms_to', 'copies_to', 'aggregates_from'
    transformation_description TEXT,
    
    -- Validation
    is_validated BOOLEAN NOT NULL DEFAULT false,
    validated_at TIMESTAMPTZ,
    validated_by UUID REFERENCES auth.users(id),
    
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Audit fields
    created_by UUID NOT NULL REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Prevent duplicate edges
    UNIQUE(team_id, source_asset_id, target_asset_id, edge_type),
    
    -- Prevent self-loops
    CONSTRAINT no_self_loop CHECK (source_asset_id != target_asset_id)
);

CREATE INDEX IF NOT EXISTS idx_ed_trail_edges_team ON ed_trail_lineage_edges(team_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_edges_source ON ed_trail_lineage_edges(source_asset_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_edges_target ON ed_trail_lineage_edges(target_asset_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_edges_type ON ed_trail_lineage_edges(edge_type);

-- RLS Policy
ALTER TABLE ed_trail_lineage_edges ENABLE ROW LEVEL SECURITY;

CREATE POLICY ed_trail_edges_select ON ed_trail_lineage_edges
    FOR SELECT USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_edges_insert ON ed_trail_lineage_edges
    FOR INSERT WITH CHECK (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_edges_update ON ed_trail_lineage_edges
    FOR UPDATE USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true AND role IN ('owner', 'admin'))
    );
