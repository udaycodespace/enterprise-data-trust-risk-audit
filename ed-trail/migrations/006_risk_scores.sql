-- ED-TRAIL Migration 006: Risk Scores
-- Computed risk scores for data assets

CREATE TABLE IF NOT EXISTS ed_trail_risk_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Team isolation
    team_id UUID NOT NULL REFERENCES teams(id),
    
    -- Score target
    asset_id UUID NOT NULL REFERENCES ed_trail_data_assets(id),
    
    -- Score values (0-100 scale)
    overall_score INTEGER NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
    completeness_score INTEGER CHECK (completeness_score >= 0 AND completeness_score <= 100),
    timeliness_score INTEGER CHECK (timeliness_score >= 0 AND timeliness_score <= 100),
    accuracy_score INTEGER CHECK (accuracy_score >= 0 AND accuracy_score <= 100),
    
    -- Score breakdown
    score_factors JSONB DEFAULT '{}',
    
    -- Trend
    previous_score INTEGER,
    score_change INTEGER,
    
    -- Financial exposure (stored in paise for INR)
    exposure_amount_paise BIGINT,
    currency VARCHAR(3) DEFAULT 'INR',
    
    -- Computation metadata
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until TIMESTAMPTZ,
    
    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ed_trail_scores_team ON ed_trail_risk_scores(team_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_scores_asset ON ed_trail_risk_scores(asset_id);
CREATE INDEX IF NOT EXISTS idx_ed_trail_scores_overall ON ed_trail_risk_scores(overall_score);
CREATE INDEX IF NOT EXISTS idx_ed_trail_scores_computed ON ed_trail_risk_scores(computed_at);

-- Latest score per asset
CREATE INDEX IF NOT EXISTS idx_ed_trail_scores_latest ON ed_trail_risk_scores(asset_id, computed_at DESC);

-- RLS Policy
ALTER TABLE ed_trail_risk_scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY ed_trail_scores_select ON ed_trail_risk_scores
    FOR SELECT USING (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );

CREATE POLICY ed_trail_scores_insert ON ed_trail_risk_scores
    FOR INSERT WITH CHECK (
        team_id IN (SELECT team_id FROM team_memberships WHERE user_id = auth.uid() AND is_active = true)
    );
