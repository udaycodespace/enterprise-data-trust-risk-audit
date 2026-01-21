# ED-BASE Incident Response Runbook

## Overview

This runbook covers response procedures for security incidents per PRD §17.
Each scenario includes: containment, investigation, recovery, communication.

---

## Scenario 1: Token Leak

### Detection
- Unusual API activity patterns
- Multiple sessions from unexpected locations
- Audit log anomalies

### Containment (Immediate)
1. Revoke all sessions for affected user(s):
   ```sql
   UPDATE sessions SET revoked_at = now(), revocation_reason = 'security_incident'
   WHERE user_id = '<affected_user_id>';
   ```
2. Invalidate affected tokens in Redis rate limit cache
3. Enable enhanced logging

### Investigation
1. Query audit logs for affected user:
   ```sql
   SELECT * FROM audit_logs 
   WHERE actor_id = '<user_id>' 
   ORDER BY created_at DESC LIMIT 100;
   ```
2. Identify token creation time and source IP
3. Determine scope of unauthorized access
4. Check for data exfiltration patterns

### Recovery
1. Force password reset for affected user
2. Review and rotate any exposed API keys
3. Verify HMAC signatures on recent audit logs
4. Monitor for continued suspicious activity

### Communication
- **Internal**: Security team notification, incident ticket
- **User**: Email notification of forced logout
- **If data breach**: Legal review, regulatory notification

---

## Scenario 2: Payment Reconciliation Mismatch

### Detection
- Stripe webhook reports successful charge not in DB
- Payment status discrepancy alerts
- Customer complaint of charge without service

### Containment (Immediate)
1. Pause automated payment processing if needed
2. Query mismatched payments:
   ```sql
   SELECT * FROM payments 
   WHERE stripe_payment_intent_id IS NOT NULL 
   AND status = 'pending' 
   AND created_at < now() - interval '1 hour';
   ```

### Investigation
1. Check processed_webhooks table for missing events
2. Verify webhook signature validation logs
3. Query idempotency_keys for stuck entries
4. Compare Stripe dashboard with local records

### Recovery
1. Manually reconcile payment states
2. Process any missed webhooks
3. Issue refunds if double-charged
4. Clear stuck idempotency keys

### Communication
- **Customer**: Apology, confirmation of correct state
- **Finance**: Reconciliation report
- **Engineering**: Post-mortem for process improvement

---

## Scenario 3: Database Outage

### Detection
- Health check returning 503
- Circuit breaker in OPEN state
- Connection pool exhaustion alerts

### Containment (Immediate)
1. Activate circuit breaker (automatic)
2. Return 503 with maintenance message
3. Scale down traffic via load balancer if needed

### Investigation
1. Check Supabase/PostgreSQL dashboard
2. Review connection pool metrics
3. Check for long-running queries
4. Review recent schema changes

### Recovery
1. Wait for circuit breaker half-open test
2. Gradually restore traffic
3. Monitor connection pool health
4. Clear any stuck transactions

### Communication
- **Users**: Status page update
- **Internal**: PagerDuty/Slack alerts
- **Post-recovery**: Incident report

---

## Scenario 4: Rate Limit Bypass

### Detection
- Requests bypassing rate limits
- Redis anomalies
- Unusual request patterns from single source

### Containment (Immediate)
1. Block offending IP at WAF/CDN level
2. Add IP to Redis blocklist:
   ```
   SET ratelimit:blocked:<ip> 1 EX 3600
   ```
3. Enable enhanced fingerprinting

### Investigation
1. Analyze request patterns
2. Check if X-Forwarded-For is being spoofed
3. Review fingerprint effectiveness
4. Check for compromised API keys

### Recovery
1. Update fingerprint algorithm if needed
2. Add new blocking rules to WAF
3. Rotate any compromised credentials
4. Update rate limit thresholds

### Communication
- **Security team**: Alert with details
- **Infra team**: WAF rule update request

---

## Escalation Matrix

| Severity | Response Time | Notification |
|----------|--------------|--------------|
| Critical (P1) | 15 minutes | On-call + Slack + Email |
| High (P2) | 1 hour | Slack + Email |
| Medium (P3) | 4 hours | Email |
| Low (P4) | 24 hours | Ticket |

---

## Post-Incident Checklist

- [ ] Incident timeline documented
- [ ] Root cause identified
- [ ] Audit log integrity verified
- [ ] Affected users notified (if applicable)
- [ ] Preventive measures defined
- [ ] Runbook updated with learnings
