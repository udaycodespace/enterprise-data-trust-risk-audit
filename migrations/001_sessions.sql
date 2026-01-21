-- ED-BASE Migration 001: Sessions
-- Purpose: Session revocation table for Invariant #1
-- A revoked session can NEVER perform a write

-- WHY token_hash instead of raw token:
-- Tokens are sensitive credentials. Storing SHA-256 hashes prevents
-- token theft if the database is compromised.

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Links session to Supabase Auth user
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- SHA-256 hash of the JWT access token
    -- WHY unique: Each token should map to exactly one session record
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    
    -- WHY team_id stored: Enables team boundary checks without re-querying
    -- membership on every request
    team_id UUID,
    
    -- Session metadata for audit trail
    ip_address INET,
    user_agent TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- WHY nullable: NULL means session is valid, non-NULL means revoked
    -- This design allows fast index scans for valid sessions
    revoked_at TIMESTAMPTZ,
    
    -- Helps debugging and incident response
    revocation_reason VARCHAR(50)
);

-- WHY this index: Every authenticated request checks session validity
-- by token hash. This must be O(1) not O(n).
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);

-- WHY this index: Finding all sessions for a user during forced logout
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

-- WHY this index: Efficient cleanup of old revoked sessions
CREATE INDEX IF NOT EXISTS idx_sessions_revoked_at ON sessions(revoked_at) 
WHERE revoked_at IS NOT NULL;

-- WHY this index: Team-based session queries for admin operations
CREATE INDEX IF NOT EXISTS idx_sessions_team_id ON sessions(team_id);

COMMENT ON TABLE sessions IS 'Session revocation table - JWT validity does NOT imply session validity. Check this table on EVERY request.';
COMMENT ON COLUMN sessions.token_hash IS 'SHA-256 hash of JWT access token. Never store raw tokens.';
COMMENT ON COLUMN sessions.revoked_at IS 'NULL = valid session. Non-NULL = revoked. Revoked sessions MUST be rejected.';
