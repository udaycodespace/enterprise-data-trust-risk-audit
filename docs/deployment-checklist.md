# ED-BASE Deployment Checklist

## Pre-Deployment Verification

Complete all items before deploying to production.

---

## Environment Variables

- [ ] `FLASK_ENV=production`
- [ ] `FLASK_DEBUG=false`
- [ ] `FLASK_SECRET_KEY` set (min 32 chars, random)
- [ ] `DATABASE_URL` set with SSL mode
- [ ] `REDIS_URL` set
- [ ] `SUPABASE_URL` set
- [ ] `SUPABASE_ANON_KEY` set
- [ ] `SUPABASE_SERVICE_ROLE_KEY` set (never expose to client)
- [ ] `JWT_SECRET` set
- [ ] `AUDIT_HMAC_SECRET` set
- [ ] `STRIPE_API_KEY` set
- [ ] `STRIPE_WEBHOOK_SECRET` set
- [ ] `CORS_ORIGINS` restricted to production domains

---

## Database

- [ ] All migrations applied
- [ ] RLS enabled on all tables
- [ ] `audit_logs` triggers active (preventing UPDATE/DELETE)
- [ ] Indexes created for token_hash, idempotency keys
- [ ] Connection pool sized appropriately
- [ ] SSL required for connections

Verify RLS:
```sql
SELECT tablename, rowsecurity FROM pg_tables 
WHERE schemaname = 'public';
```

Verify audit log triggers:
```sql
SELECT tgname, tgenabled FROM pg_trigger 
WHERE tgrelid = 'audit_logs'::regclass;
```

---

## Redis

- [ ] Redis connection verified
- [ ] Rate limit keys expiring correctly
- [ ] Memory limits configured
- [ ] Persistence configured (if needed)

Test connection:
```python
from middleware.rate_limit import get_redis
get_redis().ping()  # Should return True
```

---

## API Endpoints

- [ ] `/health` returning 200
- [ ] `/api/auth/login` rate limited (10/min)
- [ ] `/api/webhooks/stripe` signature verification working
- [ ] All endpoints require authentication (except public ones)
- [ ] Error responses are generic (no stack traces)

---

## Security Headers

Verify response includes:
- [ ] `X-Content-Type-Options: nosniff`
- [ ] `X-Frame-Options: DENY`
- [ ] `X-XSS-Protection: 1; mode=block`
- [ ] `X-Request-ID` present

---

## Monitoring

- [ ] Health check endpoint monitored
- [ ] Error rate alerting configured
- [ ] Rate limit violation alerts
- [ ] Database connection pool alerts
- [ ] Circuit breaker state alerts

---

## Audit Logging

- [ ] Auth attempts logged
- [ ] Authorization failures logged
- [ ] State changes logged
- [ ] HMAC signatures being generated
- [ ] Log retention configured (90 days hot)

Verify logging:
```python
from services.audit import log_event, EventType, ActorType
log_id = log_event(
    event_type=EventType.CONFIG_UPDATE,
    action="Deployment verification",
    actor_type=ActorType.SYSTEM
)
```

---

## Frontend

- [ ] `VITE_SUPABASE_URL` set
- [ ] `VITE_SUPABASE_ANON_KEY` set
- [ ] `VITE_API_URL` pointing to production API
- [ ] Production build created (`npm run build`)
- [ ] Static assets served with caching headers

---

## Final Checks

- [ ] No debug logging in production
- [ ] No hardcoded secrets in code
- [ ] No TODO comments in security-critical code
- [ ] Backup verified
- [ ] Rollback plan documented

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| Security | | | |
| Ops | | | |
