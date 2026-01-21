-- ED-BASE Migration 002: Audit Logs
-- Purpose: Immutable, append-only audit trail for Invariant #5 and #10
-- Audit logs are APPEND-ONLY and IMMUTABLE
-- All critical actions are attributable to an actor

-- WHY BIGSERIAL: Audit logs can grow very large. UUID would waste space
-- and SERIAL (32-bit) could overflow in high-volume systems.

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    
    -- Event classification for filtering and alerting
    event_type VARCHAR(50) NOT NULL,
    
    -- WHO performed the action (Invariant #10)
    actor_id UUID,
    actor_type VARCHAR(20) NOT NULL, -- 'user', 'system', 'webhook', 'admin'
    
    -- WHAT was affected
    resource_type VARCHAR(50),
    resource_id UUID,
    action VARCHAR(50) NOT NULL,
    
    -- WHY JSONB: Flexible schema for event-specific details
    -- Allows querying into nested structures when needed
    details JSONB,
    
    -- WHY HMAC signature: Tamper detection for Invariant #5
    -- If this doesn't match computed HMAC, log has been tampered
    hmac_signature VARCHAR(64) NOT NULL,
    
    -- Request context for incident investigation
    ip_address INET,
    user_agent TEXT,
    request_id VARCHAR(36),
    
    -- WHY DEFAULT now(): Server-side timestamp prevents client manipulation
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- WHY this index: Filtering by event type for monitoring dashboards
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type);

-- WHY this index: Finding all actions by a specific actor
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_id ON audit_logs(actor_id);

-- WHY this index: Finding all actions on a specific resource
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- WHY this index: Time-range queries for incident investigation
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- WHY this trigger: PREVENTS UPDATE/DELETE operations
-- This enforces Invariant #5 at the database level
-- Even if application code has a bug, the DB prevents mutation

CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    -- WHY RAISE EXCEPTION: Hard fail, no silent bypass
    RAISE EXCEPTION 'SECURITY VIOLATION: Audit logs are immutable. UPDATE and DELETE operations are forbidden.';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to block UPDATE
DROP TRIGGER IF EXISTS audit_logs_prevent_update ON audit_logs;
CREATE TRIGGER audit_logs_prevent_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_modification();

-- Apply trigger to block DELETE
DROP TRIGGER IF EXISTS audit_logs_prevent_delete ON audit_logs;
CREATE TRIGGER audit_logs_prevent_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_modification();

-- WHY this trigger: Auto-populates created_at to prevent manipulation
CREATE OR REPLACE FUNCTION set_audit_log_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    -- WHY override: Client cannot set their own timestamp
    NEW.created_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_logs_set_timestamp ON audit_logs;
CREATE TRIGGER audit_logs_set_timestamp
    BEFORE INSERT ON audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION set_audit_log_timestamp();

COMMENT ON TABLE audit_logs IS 'IMMUTABLE audit trail. Triggers prevent UPDATE/DELETE. HMAC signature enables tamper detection.';
COMMENT ON COLUMN audit_logs.hmac_signature IS 'HMAC-SHA256 of log entry. Verify on read to detect tampering.';
