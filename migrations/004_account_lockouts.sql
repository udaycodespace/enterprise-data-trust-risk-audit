-- ED-BASE Migration 004: Account Lockouts
-- Purpose: Brute-force protection for authentication
-- Rate limits login attempts per user and per IP

CREATE TABLE IF NOT EXISTS account_lockouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- WHY separate user_id and ip_address: Allows locking either or both
    -- Credential stuffing attacks try many users from one IP
    -- Account takeover tries one user from many IPs
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    ip_address INET,
    
    -- WHY both nullable: At least one must be set
    -- This constraint enforced below
    
    -- Track consecutive failures
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    
    -- WHY locked_until vs permanent lock:
    -- Temporary lockouts frustrate attackers without blocking legitimate users forever
    locked_until TIMESTAMPTZ,
    
    -- WHY last_attempt: Enables time-based decay of failed attempts
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- WHY this constraint: Lockout must target something
    CONSTRAINT lockout_has_target CHECK (user_id IS NOT NULL OR ip_address IS NOT NULL)
);

-- WHY this index: Fast lookup by user during login
CREATE INDEX IF NOT EXISTS idx_lockouts_user_id ON account_lockouts(user_id) 
WHERE user_id IS NOT NULL;

-- WHY this index: Fast lookup by IP during login
CREATE INDEX IF NOT EXISTS idx_lockouts_ip ON account_lockouts(ip_address) 
WHERE ip_address IS NOT NULL;

-- WHY this index: Finding expired lockouts for cleanup
CREATE INDEX IF NOT EXISTS idx_lockouts_locked_until ON account_lockouts(locked_until) 
WHERE locked_until IS NOT NULL;

-- WHY unique constraints: One lockout record per target
CREATE UNIQUE INDEX IF NOT EXISTS idx_lockouts_user_unique 
ON account_lockouts(user_id) WHERE user_id IS NOT NULL AND ip_address IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_lockouts_ip_unique 
ON account_lockouts(ip_address) WHERE ip_address IS NOT NULL AND user_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_lockouts_user_ip_unique 
ON account_lockouts(user_id, ip_address) WHERE user_id IS NOT NULL AND ip_address IS NOT NULL;

-- WHY this trigger: Auto-update updated_at
CREATE OR REPLACE FUNCTION update_lockout_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS lockouts_update_timestamp ON account_lockouts;
CREATE TRIGGER lockouts_update_timestamp
    BEFORE UPDATE ON account_lockouts
    FOR EACH ROW
    EXECUTE FUNCTION update_lockout_timestamp();

COMMENT ON TABLE account_lockouts IS 'Brute-force protection. Lock accounts/IPs after repeated failures.';
COMMENT ON COLUMN account_lockouts.failed_attempts IS 'Consecutive failures. Reset on successful login.';
COMMENT ON COLUMN account_lockouts.locked_until IS 'NULL = not locked. Future timestamp = locked until then.';
