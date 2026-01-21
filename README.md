# ED-BASE & ED-TRAIL

**Enterprise Data Trust, Risk & Audit Intelligence Platform**

This repository contains two clearly separated systems:

- **ED-BASE** — a frozen, security-first enterprise foundation
- **ED-TRAIL** — a data lineage & integrity platform built on top of ED-BASE

> ED-BASE is the lock.  
> ED-TRAIL is the value.

---

## Repository Structure

```

.
├── backend/        # ED-BASE backend (Flask, security foundation)
├── frontend/       # ED-BASE frontend (React)
├── migrations/     # ED-BASE database schema
├── docs/           # Security, threat model, incident response
├── ed-trail/       # ED-TRAIL domain system (business logic)
│   ├── migrations/
│   ├── backend/
│   ├── frontend/
│   ├── prd.md
│   └── info.txt
├── prd.txt         # ED-BASE PRD (frozen)
├── info.txt        # ED-BASE implementation summary
├── NEXT-STEPS.md   # ED-BASE → ED-TRAIL transition rules

```

---

## ED-BASE (FROZEN)

**ED-BASE** is a production-grade enterprise security foundation.

It provides:

- Authentication (Supabase)
- Session revocation (token hashes, not tokens)
- Team isolation (Postgres RLS)
- Idempotent state changes
- ACID transactions
- Immutable audit logs
- Rate limiting
- Safe error handling

🔒 **ED-BASE is frozen.**  
It must not be modified unless a real security incident occurs.

Source of truth:
- `prd.txt`
- `info.txt`
- `docs/threat-model.md`
- `docs/incident-response.md`

---

## ED-TRAIL (BUILT ON ED-BASE)

**ED-TRAIL** is a domain system for:

- Data lineage tracking
- Integrity break detection
- Risk scoring for enterprise data assets

ED-TRAIL:
- Reuses ED-BASE security without reimplementation
- Adds only domain logic and tables
- Standardizes on INR (stored in paise) **without modifying ED-BASE**

Source of truth:
- `ed-trail/prd.md`
- `ed-trail/info.txt`

---

## Design Principles

- Security foundations are immutable
- Domain logic is isolated
- No duplicated auth, audit, or transaction logic
- All guarantees are documented and enforced
- PRDs exist before code

---

## Status

- ✅ ED-BASE: Final & Frozen
- ✅ ED-TRAIL: Fully implemented
- 🏷️ Tag: `v1.0-ed-trail`

---

## Why this repo exists

This project demonstrates **enterprise-grade system design**:
- Separation of platform vs product
- Audit-safe thinking
- Risk-aware architecture
- Security-first development

This is not a demo app.  
This is a reference system.

---

## License

MIT