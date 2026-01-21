-- ED-BASE Migration 006: Processed Webhooks
-- Purpose: Webhook deduplication and replay protection
-- Prevents double-processing of payment webhooks

CREATE TABLE IF NOT EXISTS processed_webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- WHY webhook_id from provider: Unique identifier from Stripe/etc
    -- This is the deduplication key
    webhook_id VARCHAR(255) NOT NULL,
    
    -- WHY provider: Support multiple webhook sources
    provider VARCHAR(50) NOT NULL, -- 'stripe', 'paypal', etc.
    
    -- WHY unique on (webhook_id, provider): Same ID from different providers
    -- should be treated as different webhooks
    
    event_type VARCHAR(100),
    
    -- WHY store payload: Enables investigation and replay if needed
    payload JSONB,
    
    -- Processing result
    status VARCHAR(20) NOT NULL DEFAULT 'processed', -- 'processed', 'failed', 'ignored'
    error_message TEXT,
    
    -- WHY signature_valid: Record if signature was verified
    signature_valid BOOLEAN NOT NULL DEFAULT false,
    
    -- WHY received_at vs processed_at: Track webhook lag
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(webhook_id, provider)
);

-- WHY this index: Fast deduplication check on incoming webhooks
CREATE INDEX IF NOT EXISTS idx_webhooks_lookup 
ON processed_webhooks(webhook_id, provider);

-- WHY this index: Find failed webhooks for retry
CREATE INDEX IF NOT EXISTS idx_webhooks_failed 
ON processed_webhooks(status) WHERE status = 'failed';

-- WHY this index: Time-based cleanup of old records
CREATE INDEX IF NOT EXISTS idx_webhooks_received 
ON processed_webhooks(received_at);

-- WHY this index: Filter by provider for monitoring dashboards
CREATE INDEX IF NOT EXISTS idx_webhooks_provider 
ON processed_webhooks(provider);

COMMENT ON TABLE processed_webhooks IS 'Webhook deduplication. Check before processing to prevent double-execution.';
COMMENT ON COLUMN processed_webhooks.webhook_id IS 'Provider-assigned unique ID. Primary deduplication key.';
COMMENT ON COLUMN processed_webhooks.signature_valid IS 'True only if cryptographic signature was verified.';
