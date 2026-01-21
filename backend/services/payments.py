"""
ED-BASE Payments Service
Payment state machine with atomic transitions.

Invariant #8: Payments are either fully applied or rolled back.
"""

from datetime import datetime, timezone
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import structlog

from utils import get_cursor, generate_idempotency_key, DatabaseError
from services.transactions import payment_transaction, with_retry
from services.audit import log_event, EventType, ActorType
from config import get_config

logger = structlog.get_logger(__name__)


class PaymentStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass
class Payment:
    id: str
    team_id: str
    user_id: str
    amount_cents: int
    currency: str
    status: PaymentStatus
    stripe_payment_intent_id: Optional[str]
    idempotency_key: str
    created_at: datetime


def create_payment(
    team_id: str,
    user_id: str,
    amount_cents: int,
    currency: str = "USD",
    description: Optional[str] = None,
    idempotency_key: Optional[str] = None
) -> Payment:
    """
    Create a pending payment record.
    
    Uses SERIALIZABLE isolation to prevent race conditions.
    """
    idempotency_key = idempotency_key or generate_idempotency_key()
    
    query = """
        INSERT INTO payments (
            team_id, user_id, amount_cents, currency, description, idempotency_key
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, team_id, user_id, amount_cents, currency, status,
                  stripe_payment_intent_id, idempotency_key, created_at
    """
    
    def execute():
        with payment_transaction() as cur:
            cur.execute(query, (
                team_id, user_id, amount_cents, currency,
                description, idempotency_key
            ))
            row = cur.fetchone()
            
            log_event(
                event_type=EventType.PAYMENT_INITIATED,
                action="Payment created",
                actor_id=user_id,
                actor_type=ActorType.USER,
                resource_type="payment",
                resource_id=row['id'],
                details={'amount_cents': amount_cents, 'currency': currency}
            )
            
            return Payment(
                id=row['id'],
                team_id=row['team_id'],
                user_id=row['user_id'],
                amount_cents=row['amount_cents'],
                currency=row['currency'],
                status=PaymentStatus(row['status']),
                stripe_payment_intent_id=row['stripe_payment_intent_id'],
                idempotency_key=row['idempotency_key'],
                created_at=row['created_at']
            )
    
    return with_retry(execute)


def complete_payment(
    payment_id: str,
    stripe_payment_intent_id: str,
    stripe_charge_id: Optional[str] = None
) -> bool:
    """
    Mark payment as completed.
    
    State transition: pending → completed
    """
    query = """
        UPDATE payments
        SET status = 'completed',
            stripe_payment_intent_id = %s,
            stripe_charge_id = %s,
            completed_at = %s
        WHERE id = %s AND status = 'pending'
    """
    
    def execute():
        with payment_transaction() as cur:
            cur.execute(query, (
                stripe_payment_intent_id, stripe_charge_id,
                datetime.now(timezone.utc), payment_id
            ))
            if cur.rowcount == 0:
                return False
            
            log_event(
                event_type=EventType.PAYMENT_COMPLETED,
                action="Payment completed",
                actor_type=ActorType.SYSTEM,
                resource_type="payment",
                resource_id=payment_id,
                details={'stripe_id': stripe_payment_intent_id}
            )
            return True
    
    return with_retry(execute)


def fail_payment(
    payment_id: str,
    error_code: str,
    error_message: str
) -> bool:
    """
    Mark payment as failed.
    
    State transition: pending → failed
    """
    query = """
        UPDATE payments
        SET status = 'failed',
            error_code = %s,
            error_message = %s,
            failed_at = %s
        WHERE id = %s AND status = 'pending'
    """
    
    def execute():
        with payment_transaction() as cur:
            cur.execute(query, (
                error_code, error_message,
                datetime.now(timezone.utc), payment_id
            ))
            if cur.rowcount == 0:
                return False
            
            log_event(
                event_type=EventType.PAYMENT_FAILED,
                action="Payment failed",
                actor_type=ActorType.SYSTEM,
                resource_type="payment",
                resource_id=payment_id,
                details={'error_code': error_code}
            )
            return True
    
    return with_retry(execute)


def get_payment(payment_id: str) -> Optional[Payment]:
    """Get payment by ID."""
    query = """
        SELECT id, team_id, user_id, amount_cents, currency, status,
               stripe_payment_intent_id, idempotency_key, created_at
        FROM payments WHERE id = %s
    """
    try:
        with get_cursor() as cur:
            cur.execute(query, (payment_id,))
            row = cur.fetchone()
            if not row:
                return None
            return Payment(
                id=row['id'],
                team_id=row['team_id'],
                user_id=row['user_id'],
                amount_cents=row['amount_cents'],
                currency=row['currency'],
                status=PaymentStatus(row['status']),
                stripe_payment_intent_id=row['stripe_payment_intent_id'],
                idempotency_key=row['idempotency_key'],
                created_at=row['created_at']
            )
    except Exception as e:
        raise DatabaseError(f"Failed to get payment: {e}")
