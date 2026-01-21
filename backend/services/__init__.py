"""
ED-BASE Services Package
Core business logic services.
"""

from services.session import (
    create_session,
    get_session_by_token,
    validate_session,
    revoke_session,
    revoke_all_user_sessions,
    revoke_sessions_by_team,
    RevocationReason,
    Session,
)

from services.auth import (
    AuthService,
    AuthResult,
    get_auth_service,
)

from services.authorization import (
    Role,
    AuthorizationContext,
    TeamMembership,
    get_authorization_context,
    require_team_access,
    get_user_teams,
    add_team_member,
    change_member_role,
    remove_team_member,
    AuthorizationError,
    TeamBoundaryError,
    RoleError,
)

from services.idempotency import (
    check_idempotency,
    acquire_idempotency_lock,
    complete_idempotency,
    fail_idempotency,
    IdempotencyContext,
    IdempotencyConflict,
    IdempotencyLocked,
)

from services.transactions import (
    IsolationLevel,
    transaction,
    payment_transaction,
    audit_transaction,
    with_retry,
    TransactionError,
)

from services.audit import (
    EventType,
    ActorType,
    log_event,
    log_auth_attempt,
    log_security_event,
)

from services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    get_circuit,
    with_circuit_breaker,
)

from services.payments import (
    Payment,
    PaymentStatus,
    create_payment,
    complete_payment,
    fail_payment,
    get_payment,
)

from services.webhooks import (
    verify_stripe_signature,
    check_webhook_processed,
    record_webhook,
    process_stripe_webhook,
    WebhookError,
    WebhookSignatureError,
    WebhookDuplicateError,
)
