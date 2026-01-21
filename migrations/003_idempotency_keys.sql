-- ED-BASE Migration 003: Idempotency Keys
-- Purpose: Exactly-once state changes for Invariant #2
-- Prevents replay attacks and duplicate processing

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- WHY client-provided key: Allows client to detect/prevent duplicates
    -- before they hit the database
    key VARCHAR(255) NOT NULL UNIQUE,
    
    -- WHY user_id: Keys are user-scoped to prevent cross-user collisions
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- WHY request_hash: Detects payload tampering with same key
    -- Same key + different hash = 409 Conflict (malicious replay attempt)
    request_hash VARCHAR(64) NOT NULL,
    
    -- WHY JSONB response: Cache the response to return on replay
    -- This makes replays safe and fast
    response JSONB,
    
    -- WHY status: Tracks processing state for recovery
    -- 'pending' = locked for processing
    -- 'completed' = done, response cached
    -- 'failed' = processing failed, can retry
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- WHY expires_at: Prevents unbounded table growth
    -- 48 hours is sufficient for retry scenarios
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '48 hours',
    
    -- WHY locked_at: Implements pessimistic locking for race conditions
    locked_at TIMESTAMPTZ,
    locked_by VARCHAR(255)
);

-- WHY this index: Primary lookup path for idempotency checks
CREATE INDEX IF NOT EXISTS idx_idempotency_key ON idempotency_keys(key);

-- WHY this index: Cleanup job finds expired keys
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys(expires_at);

-- WHY this index: User can list their pending operations
CREATE INDEX IF NOT EXISTS idx_idempotency_user ON idempotency_keys(user_id);

-- WHY this index: Finding stuck locks for recovery
CREATE INDEX IF NOT EXISTS idx_idempotency_locked ON idempotency_keys(locked_at) 
WHERE locked_at IS NOT NULL AND status = 'pending';

-- WHY unique constraint on (key, user_id): 
-- Different users can use the same key value
ALTER TABLE idempotency_keys 
DROP CONSTRAINT IF EXISTS idempotency_keys_key_key;

ALTER TABLE idempotency_keys 
ADD CONSTRAINT idempotency_keys_user_key_unique UNIQUE (user_id, key);

COMMENT ON TABLE idempotency_keys IS 'Exactly-once execution. Same key + same hash = cached response. Same key + different hash = 409 Conflict.';
COMMENT ON COLUMN idempotency_keys.request_hash IS 'SHA-256 of request body. Detects payload tampering attempts.';
COMMENT ON COLUMN idempotency_keys.expires_at IS 'Keys auto-expire after 48h. Run cleanup job periodically.';
