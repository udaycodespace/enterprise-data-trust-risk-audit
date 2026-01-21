-- ED-BASE Migration 007: Payments
-- Purpose: Payment tracking with atomic state transitions
-- Invariant #8: Payments are either fully applied or rolled back

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- WHY team_id: All resources scoped to teams (Invariant #3)
    team_id UUID NOT NULL REFERENCES teams(id),
    
    -- WHY user_id: Track who initiated the payment (Invariant #10)
    user_id UUID NOT NULL REFERENCES auth.users(id),
    
    -- WHY cents: Avoid floating point precision issues
    -- $19.99 = 1999 cents
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    
    -- WHY state machine: Clear transition paths
    -- pending -> completed (success)
    -- pending -> failed (error)
    -- pending -> cancelled (user/admin action)
    -- completed -> refunded (after the fact)
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    
    -- WHY description: Human-readable for customer support
    description TEXT,
    
    -- WHY metadata: Flexible product-specific data
    metadata JSONB DEFAULT '{}',
    
    -- External payment processor reference
    stripe_payment_intent_id VARCHAR(255),
    stripe_charge_id VARCHAR(255),
    
    -- WHY idempotency_key: Prevents duplicate charges
    -- Passed to Stripe for their deduplication
    idempotency_key VARCHAR(255) UNIQUE,
    
    -- WHY error_* columns: Debug failed payments
    error_code VARCHAR(50),
    error_message TEXT,
    
    -- Timestamps for state transitions
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    
    -- WHY valid statuses constraint: Prevent invalid states
    CONSTRAINT valid_status CHECK (
        status IN ('pending', 'completed', 'failed', 'cancelled', 'refunded')
    )
);

-- WHY this index: Find payments by team for billing dashboards
CREATE INDEX IF NOT EXISTS idx_payments_team ON payments(team_id);

-- WHY this index: Find payments by user for account history
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);

-- WHY this index: Find pending payments for monitoring
CREATE INDEX IF NOT EXISTS idx_payments_pending 
ON payments(status) WHERE status = 'pending';

-- WHY this index: Lookup by Stripe ID for webhook processing
CREATE INDEX IF NOT EXISTS idx_payments_stripe 
ON payments(stripe_payment_intent_id) WHERE stripe_payment_intent_id IS NOT NULL;

-- WHY this index: Time-based queries for reporting
CREATE INDEX IF NOT EXISTS idx_payments_created ON payments(created_at);

-- WHY this trigger: Auto-update updated_at and state timestamps
CREATE OR REPLACE FUNCTION update_payment_timestamps()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    
    -- Set completion timestamp when transitioning to completed
    IF NEW.status = 'completed' AND OLD.status = 'pending' THEN
        NEW.completed_at := now();
    END IF;
    
    -- Set failure timestamp when transitioning to failed
    IF NEW.status = 'failed' AND OLD.status = 'pending' THEN
        NEW.failed_at := now();
    END IF;
    
    -- Set refund timestamp when transitioning to refunded
    IF NEW.status = 'refunded' AND OLD.status = 'completed' THEN
        NEW.refunded_at := now();
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS payments_update_timestamps ON payments;
CREATE TRIGGER payments_update_timestamps
    BEFORE UPDATE ON payments
    FOR EACH ROW
    EXECUTE FUNCTION update_payment_timestamps();

-- WHY this trigger: Prevent invalid state transitions
CREATE OR REPLACE FUNCTION validate_payment_transition()
RETURNS TRIGGER AS $$
BEGIN
    -- Valid transitions from pending
    IF OLD.status = 'pending' AND NEW.status NOT IN ('completed', 'failed', 'cancelled') THEN
        RAISE EXCEPTION 'Invalid payment transition from pending to %', NEW.status;
    END IF;
    
    -- Valid transitions from completed
    IF OLD.status = 'completed' AND NEW.status != 'refunded' THEN
        RAISE EXCEPTION 'Invalid payment transition from completed to %', NEW.status;
    END IF;
    
    -- Failed, cancelled, refunded are terminal states
    IF OLD.status IN ('failed', 'cancelled', 'refunded') THEN
        RAISE EXCEPTION 'Cannot transition from terminal state %', OLD.status;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS payments_validate_transition ON payments;
CREATE TRIGGER payments_validate_transition
    BEFORE UPDATE ON payments
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION validate_payment_transition();

COMMENT ON TABLE payments IS 'Payment records with atomic state machine. Use SERIALIZABLE isolation for updates.';
COMMENT ON COLUMN payments.amount_cents IS 'Amount in smallest currency unit (cents). Avoids float precision issues.';
COMMENT ON COLUMN payments.idempotency_key IS 'Prevents duplicate charges. Pass to Stripe API.';
