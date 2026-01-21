"""
ED-BASE Webhooks Service
Webhook deduplication and signature verification.

Prevents double-processing of payment webhooks.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import hmac
import hashlib
import structlog

from utils import get_cursor, is_within_clock_skew, DatabaseError
from config import get_config

logger = structlog.get_logger(__name__)


class WebhookError(Exception):
    """Base webhook error."""
    pass


class WebhookSignatureError(WebhookError):
    """Invalid webhook signature."""
    pass


class WebhookDuplicateError(WebhookError):
    """Webhook already processed."""
    pass


def verify_stripe_signature(
    payload: bytes,
    signature_header: str,
    tolerance_seconds: int = 300
) -> Tuple[bool, Optional[str]]:
    """
    Verify Stripe webhook signature.
    
    Args:
        payload: Raw request body
        signature_header: Stripe-Signature header value
        tolerance_seconds: Clock skew tolerance (±5 min per PRD)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    config = get_config().payment
    secret = config.stripe_webhook_secret
    
    if not secret:
        return (False, "Webhook secret not configured")
    
    try:
        # Parse signature header
        elements = dict(item.split("=", 1) for item in signature_header.split(","))
        timestamp = int(elements.get("t", "0"))
        signatures = [v for k, v in elements.items() if k.startswith("v1")]
        
        if not signatures:
            return (False, "No v1 signature found")
        
        # Check timestamp tolerance
        webhook_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if not is_within_clock_skew(webhook_time, tolerance_seconds):
            return (False, "Timestamp outside tolerance")
        
        # Compute expected signature
        signed_payload = f"{timestamp}.".encode() + payload
        expected_sig = hmac.new(
            secret.encode(),
            signed_payload,
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison
        for sig in signatures:
            if hmac.compare_digest(expected_sig, sig):
                return (True, None)
        
        return (False, "Signature mismatch")
        
    except Exception as e:
        logger.error("Signature verification failed", error=str(e))
        return (False, f"Verification error: {e}")


def check_webhook_processed(
    webhook_id: str,
    provider: str = "stripe"
) -> bool:
    """Check if webhook was already processed."""
    query = """
        SELECT id FROM processed_webhooks
        WHERE webhook_id = %s AND provider = %s
    """
    try:
        with get_cursor() as cur:
            cur.execute(query, (webhook_id, provider))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("Webhook check failed", webhook_id=webhook_id, error=str(e))
        return False


def record_webhook(
    webhook_id: str,
    provider: str,
    event_type: str,
    payload: dict,
    status: str = "processed",
    signature_valid: bool = True
) -> str:
    """Record processed webhook for deduplication."""
    import json
    query = """
        INSERT INTO processed_webhooks (
            webhook_id, provider, event_type, payload, status, signature_valid
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (webhook_id, provider) DO NOTHING
        RETURNING id
    """
    try:
        with get_cursor() as cur:
            cur.execute(query, (
                webhook_id, provider, event_type,
                json.dumps(payload), status, signature_valid
            ))
            row = cur.fetchone()
            if row:
                return str(row['id'])
            raise WebhookDuplicateError(f"Webhook {webhook_id} already processed")
    except WebhookDuplicateError:
        raise
    except Exception as e:
        raise DatabaseError(f"Failed to record webhook: {e}")


def process_stripe_webhook(
    payload: bytes,
    signature_header: str
) -> Tuple[dict, str]:
    """
    Process incoming Stripe webhook with deduplication.
    
    Args:
        payload: Raw request body
        signature_header: Stripe-Signature header
        
    Returns:
        Tuple of (event_data, webhook_id)
        
    Raises:
        WebhookSignatureError: Invalid signature
        WebhookDuplicateError: Already processed
    """
    import json
    
    # Verify signature
    is_valid, error = verify_stripe_signature(payload, signature_header)
    if not is_valid:
        raise WebhookSignatureError(error)
    
    # Parse event
    event = json.loads(payload)
    webhook_id = event.get("id")
    event_type = event.get("type")
    
    if not webhook_id:
        raise WebhookError("Missing webhook ID")
    
    # Check for duplicate
    if check_webhook_processed(webhook_id, "stripe"):
        raise WebhookDuplicateError(f"Webhook {webhook_id} already processed")
    
    # Record webhook
    record_webhook(
        webhook_id=webhook_id,
        provider="stripe",
        event_type=event_type,
        payload=event,
        signature_valid=True
    )
    
    logger.info("Webhook processed", webhook_id=webhook_id, event_type=event_type)
    return (event, webhook_id)
