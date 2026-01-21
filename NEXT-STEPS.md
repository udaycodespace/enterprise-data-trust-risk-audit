# ED-BASE → ED-TRAIL Transition Guide

## PURPOSE

This document defines the only correct next steps after freezing ED-BASE and before starting ED-TRAIL.

---

## CURRENT STATE (LOCKED)

### ED-BASE STATUS
- ✅ ED-BASE is **FINAL and FROZEN**
- ✅ All security invariants are enforced
- ✅ `info.txt`, threat-model, incident-response, deployment-checklist are source of truth
- ❌ No further edits unless a real incident occurs

### DO NOT MODIFY (Contract Files)
- `backend/middleware/auth.py`
- `backend/services/idempotency.py`
- `backend/services/audit.py`
- `backend/services/transactions.py`
- `migrations/002_audit_logs.sql`
- `migrations/008_rls_policies.sql`
- `info.txt`

---

## CLARIFICATIONS

### 1️⃣ Currency (USD vs INR)
- ED-BASE is **currency-agnostic** (integer minor units + ISO code)
- ED-TRAIL will standardize on **INR**
- ❌ Do NOT rename DB columns
- ❌ Do NOT hardcode INR in ED-BASE
- ✅ INR handling lives ONLY in ED-TRAIL business logic

### 2️⃣ Token / HMAC
- JWTs → standard signed tokens
- Sessions → SHA-256 hashed
- Raw tokens never stored
- **No code changes required**

---

## NEXT STEPS (MANDATORY ORDER)

| Step | Action | Status |
|------|--------|--------|
| 1 | Create `ed-trail/` folder | ✅ Done |
| 2 | Write `ed-trail/prd.md` | ✅ Done |
| 3 | Commit the PRD | ⏳ Ready |
| 4 | Create ED-TRAIL tables | Pending |
| 5 | Create ED-TRAIL APIs | Pending |
| 6 | Build ED-TRAIL frontend | Pending |

---

## WHAT NOT TO DO

- ❌ Do NOT regenerate ED-BASE with AI
- ❌ Do NOT change currency columns
- ❌ Do NOT touch auth/session code
- ❌ Do NOT add OTP/OAuth yet
- ❌ Do NOT start coding ED-TRAIL before PRD is committed

---

## SUCCESS CONDITION

You are doing it right if:
- ED-BASE remains untouched
- INR logic exists only in ED-TRAIL
- All security is inherited, not duplicated
- PRD is written before code

---

## FINAL RULE

**ED-BASE is the lock. ED-TRAIL is the value. Never confuse the two.**
