-- ED-BASE Migration 005: Teams
-- Purpose: Team isolation for Invariant #3
-- Users cannot cross team boundaries

CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    name VARCHAR(255) NOT NULL,
    
    -- WHY slug: URL-friendly identifier for API routes
    slug VARCHAR(100) NOT NULL UNIQUE,
    
    -- WHY settings JSONB: Flexible per-team configuration
    -- Avoids schema changes for new settings
    settings JSONB DEFAULT '{}',
    
    -- WHY soft delete: Maintains referential integrity
    -- Hard delete could orphan records
    deleted_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- WHY this index: Lookup by slug for API routes
CREATE INDEX IF NOT EXISTS idx_teams_slug ON teams(slug);

-- WHY this index: Filter out deleted teams
CREATE INDEX IF NOT EXISTS idx_teams_active ON teams(id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS team_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- WHY role: RBAC within teams
    -- Common values: 'owner', 'admin', 'member', 'viewer'
    role VARCHAR(50) NOT NULL,
    
    -- WHY is_active: Soft disable without removing
    -- Allows temporary suspension
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- WHY invited_by: Audit trail for membership changes
    invited_by UUID REFERENCES auth.users(id),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- WHY unique: One membership per user per team
    UNIQUE(team_id, user_id)
);

-- WHY this index: Find all teams for a user
CREATE INDEX IF NOT EXISTS idx_memberships_user ON team_memberships(user_id);

-- WHY this index: Find all members of a team
CREATE INDEX IF NOT EXISTS idx_memberships_team ON team_memberships(team_id);

-- WHY this index: Filter active memberships only
CREATE INDEX IF NOT EXISTS idx_memberships_active ON team_memberships(user_id, team_id) 
WHERE is_active = true;

-- WHY this trigger: Auto-update updated_at
CREATE OR REPLACE FUNCTION update_team_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS teams_update_timestamp ON teams;
CREATE TRIGGER teams_update_timestamp
    BEFORE UPDATE ON teams
    FOR EACH ROW
    EXECUTE FUNCTION update_team_timestamp();

DROP TRIGGER IF EXISTS memberships_update_timestamp ON team_memberships;
CREATE TRIGGER memberships_update_timestamp
    BEFORE UPDATE ON team_memberships
    FOR EACH ROW
    EXECUTE FUNCTION update_team_timestamp();

COMMENT ON TABLE teams IS 'Multi-tenant team isolation. All resources are team-scoped.';
COMMENT ON TABLE team_memberships IS 'User-team associations with roles. Role checked at query time, never cached.';
COMMENT ON COLUMN team_memberships.role IS 'RBAC role. Check permissions at query time, not from cache (Invariant #4).';
