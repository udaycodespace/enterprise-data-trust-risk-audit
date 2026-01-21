# ED-BASE Threat Model

## Overview

This document defines the threat model for ED-BASE per PRD §5.
All listed threat classes are covered by implemented controls.

---

## Covered Threat Classes

### 1. Account Takeover

**Description**: Attacker gains access to user account via stolen credentials, session hijacking, or social engineering.

**Mitigations**:
- Account lockout after 5 failed attempts
- Session revocation on password change
- Token rotation on refresh
- HMAC-signed session tokens

---

### 2. Session Replay & Fixation

**Description**: Attacker uses stolen/old tokens to impersonate user.

**Mitigations**:
- Session revocation table checked on every request
- Token hashes stored, not tokens themselves
- Short-lived access tokens (15 min)
- Refresh token rotation

---

### 3. Authorization Bypass (IDOR)

**Description**: User accesses resources belonging to other users/teams.

**Mitigations**:
- PostgreSQL Row-Level Security (RLS)
- Team boundary enforcement in middleware
- Role checked at query time (no caching)
- Backend authorization overrides frontend

---

### 4. Double Spending & Race Conditions

**Description**: Concurrent requests cause duplicate processing.

**Mitigations**:
- Idempotency keys for all mutations
- SERIALIZABLE isolation for payments
- DB-level locks for concurrent operations
- Exactly-once execution guarantees

---

### 5. API Abuse & Scraping

**Description**: Automated attacks exhaust resources or extract data.

**Mitigations**:
- Rate limiting per IP/user/endpoint
- Fingerprint-based tracking (not just IP)
- All violations logged
- 429 responses with Retry-After

---

### 6. Webhook Replay

**Description**: Old webhook events re-sent to trigger duplicate actions.

**Mitigations**:
- Webhook ID deduplication table
- Signature verification (Stripe)
- ±5 minute clock skew tolerance
- Transactional processing

---

### 7. Insider Misuse

**Description**: Admin or employee abuses access.

**Mitigations**:
- Append-only audit logs
- HMAC-signed log entries
- All actions attributable to actor
- Role-based access control

---

### 8. Information Disclosure

**Description**: Error messages or responses leak internal details.

**Mitigations**:
- Generic client-facing error messages
- Internal details logged, not returned
- Never expose: stack traces, DB errors, file paths

---

### 9. Partial Infrastructure Failure

**Description**: Database or service outage causes inconsistent state.

**Mitigations**:
- Circuit breaker pattern
- Health check endpoints
- Connection pool with timeouts
- Automatic transaction rollback

---

## Residual Risks (Explicitly Accepted)

Per PRD §19, these risks are accepted with compensating controls:

| Risk | Compensating Control |
|------|---------------------|
| Phishing | User education, audit logging |
| User malware | Audit logging, short token life |
| Account sharing | Audit logging, rate limits |
| Large-scale DDoS | CDN/WAF (external) |
| Insider admin abuse | Detected via audit, not prevented |

---

## Security Iteration Policy

Per PRD §20, ED-BASE modifications follow this loop:

1. Declare invariants
2. Assume attacker capability
3. Enumerate attacks
4. Attempt invariant violation
5. Observe logs & behavior
6. Patch root cause only
7. Lock iteration (no rework)
8. Record residual risk

**ED-BASE is modified only after real incidents.**
