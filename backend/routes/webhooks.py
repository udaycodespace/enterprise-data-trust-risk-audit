"""
ED-BASE Webhook Routes
Stripe webhook receiver with deduplication.
"""

from flask import Blueprint, request, jsonify
import structlog

from services import (
    process_stripe_webhook,
    WebhookSignatureError,
    WebhookDuplicateError,
    complete_payment,
    fail_payment,
)
from middleware import safe_handler

logger = structlog.get_logger(__name__)

webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/api/webhooks')


@webhooks_bp.route('/stripe', methods=['POST'])
@safe_handler
def stripe_webhook():
    """
    Stripe webhook receiver.
    
    Verifies signature, deduplicates, and processes events.
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    
    try:
        event, webhook_id = process_stripe_webhook(payload, sig_header)
    except WebhookSignatureError as e:
        logger.warning("Webhook signature invalid", error=str(e))
        return jsonify({'error': 'Invalid signature'}), 400
    except WebhookDuplicateError as e:
        logger.info("Webhook duplicate", webhook_id=str(e))
        return jsonify({'received': True, 'duplicate': True}), 200
    except Exception as e:
        logger.error("Webhook processing failed", error=str(e))
        return jsonify({'error': 'Processing failed'}), 500
    
    # Handle specific event types
    event_type = event.get('type')
    data = event.get('data', {}).get('object', {})
    
    if event_type == 'payment_intent.succeeded':
        handle_payment_succeeded(data)
    elif event_type == 'payment_intent.payment_failed':
        handle_payment_failed(data)
    
    return jsonify({'received': True}), 200


def handle_payment_succeeded(data: dict) -> None:
    """Handle successful payment webhook."""
    payment_intent_id = data.get('id')
    
    # Find payment by stripe ID and complete it
    # In production, query by stripe_payment_intent_id
    logger.info("Payment succeeded webhook", payment_id=payment_intent_id)
    
    # Example: complete_payment(payment_id, payment_intent_id)


def handle_payment_failed(data: dict) -> None:
    """Handle failed payment webhook."""
    payment_intent_id = data.get('id')
    error = data.get('last_payment_error', {})
    
    logger.info(
        "Payment failed webhook",
        payment_id=payment_intent_id,
        error_code=error.get('code')
    )
    
    # Example: fail_payment(payment_id, error.get('code'), error.get('message'))
