# ED-TRAIL — Product Requirements Document

**Data Lineage & Integrity Visibility Platform**

---

## 1. Purpose & Relationship to ED-BASE

ED-TRAIL is a **data lineage and integrity detection system** built on top of the frozen ED-BASE security foundation.

### Dependency Model

- **ED-TRAIL depends on ED-BASE** — all security guarantees are inherited
- **ED-BASE is NOT modified** — security layer remains frozen
- **ED-TRAIL adds business logic only** — domain-specific features on top of proven infrastructure

### Inheritance

| Capability | Provided By |
|------------|-------------|
| Authentication | ED-BASE |
| Session management | ED-BASE |
| Authorization & team isolation | ED-BASE |
| Rate limiting | ED-BASE |
| Idempotency | ED-BASE |
| Audit logging | ED-BASE |
| Transaction guarantees | ED-BASE |
| Payment patterns | ED-BASE |

ED-TRAIL **reuses** these capabilities via middleware and services. No reimplementation.

---

## 2. Explicit Assumptions from ED-BASE

The following are inherited and assumed true:

1. **Authentication** — Supabase Auth handles email/password, OTP, OAuth
2. **Sessions** — Token hashes (SHA-256) stored, not raw tokens
3. **JWTs** — Standard signed tokens from auth provider
4. **Audit logs** — Append-only, HMAC-signed, immutable
5. **Idempotency** — Exactly-once execution for state changes
6. **Team isolation** — RLS policies enforce boundaries
7. **Currency storage** — Integer minor units with ISO-4217 code

ED-TRAIL does NOT re-verify these. They are contract guarantees from ED-BASE.

---

## 3. Currency Standardization

### ED-TRAIL Currency Policy

- **Standard currency**: INR (Indian Rupee)
- **Storage format**: Paise (100 paise = 1 rupee)
- **Conversion**: ED-TRAIL business logic converts rupees → paise before persistence

### Rules

| Rule | Description |
|------|-------------|
| Input | Accept amounts in rupees from UI |
| Conversion | Multiply by 100 to get paise |
| Storage | Store as `amount_paise BIGINT` with `currency = 'INR'` |
| Display | Divide by 100 for rupee display |

### What NOT to do

- ❌ Do NOT rename ED-BASE columns (they remain `amount_cents`)
- ❌ Do NOT hardcode INR in ED-BASE
- ✅ INR handling exists ONLY in ED-TRAIL business logic layer

---

## 4. Core Domain

### ED-TRAIL Purpose

ED-TRAIL provides **data lineage tracking** and **integrity break detection** for enterprise audit and risk visibility.

### Core Capabilities

1. **Data Lineage**
   - Track data flow across systems
   - Record source → transformation → destination
   - Maintain versioned lineage graphs

2. **Integrity Detection**
   - Detect breaks in expected data flow
   - Flag anomalies in transformation chains
   - Alert on missing or unexpected data

3. **Audit Visibility**
   - Unified view of data provenance
   - Risk scoring for data assets
   - Compliance reporting

### Key Entities

| Entity | Description |
|--------|-------------|
| DataSource | Origin of data (system, file, API) |
| DataAsset | Tracked data element |
| LineageEdge | Connection between assets |
| IntegrityCheck | Validation rule |
| BreakEvent | Detected integrity failure |

---

## 5. Architecture

### New Tables (ED-TRAIL Only)

ED-TRAIL adds domain-specific tables. ED-BASE tables remain unchanged.

```
ed_trail_data_sources
ed_trail_data_assets
ed_trail_lineage_edges
ed_trail_integrity_checks
ed_trail_break_events
ed_trail_risk_scores
```

### Naming Convention

- All ED-TRAIL tables prefixed with `ed_trail_`
- Prevents collision with ED-BASE tables
- Clear ownership boundaries

### Integration Points

| ED-TRAIL Component | ED-BASE Service |
|--------------------|-----------------|
| API routes | `middleware/auth.py` (authentication) |
| Data mutations | `services/idempotency.py` (exactly-once) |
| State changes | `services/transactions.py` (ACID) |
| Activity tracking | `services/audit.py` (logging) |
| User access | `services/authorization.py` (team isolation) |

### RLS Policy Reuse

ED-TRAIL tables will apply the same RLS pattern:
- Team-scoped access
- Role-based permissions
- No cross-team data visibility

---

## 6. ED-TRAIL Edge Cases

### 6.1 Broken Lineage

**Scenario**: Expected upstream data source stops sending data.

**Handling**:
- BreakEvent created with `type = 'missing_source'`
- Alert generated
- Lineage graph marked incomplete
- Risk score elevated

### 6.2 Late Data

**Scenario**: Data arrives after expected processing window.

**Handling**:
- Store with `arrived_late = true` flag
- Include in lineage but mark as delayed
- Separate reporting for on-time vs late data

### 6.3 Audit Period Inconsistencies

**Scenario**: Data for closed audit period is modified.

**Handling**:
- Reject modification if period is closed
- Log attempt to audit trail
- Allow only via explicit override with approval audit

### 6.4 Orphaned Assets

**Scenario**: Data asset has no upstream lineage.

**Handling**:
- Flag as `origin_unknown = true`
- Require manual classification
- Prevent downstream propagation until resolved

### 6.5 Circular Dependencies

**Scenario**: Lineage graph contains cycles.

**Handling**:
- Detect during edge creation
- Reject if cycle would be created
- Existing cycles flagged for remediation

---

## 7. Explicit Non-Goals

ED-TRAIL does NOT:

| Non-Goal | Reason |
|----------|--------|
| Business Intelligence | Not a BI/reporting tool |
| ML Fraud Detection | No machine learning models |
| ERP Replacement | Not an enterprise resource planner |
| Replace ED-BASE | Security layer is inherited, not replaced |
| Real-time Streaming | Batch-oriented lineage tracking |
| Data Transformation | Tracks lineage, does not transform data |
| Custom Auth | Uses ED-BASE authentication |

---

## 8. Success Criteria

ED-TRAIL is successful when:

1. **Lineage Completeness** — All data flows are tracked
2. **Integrity Detection** — Breaks are identified within SLA
3. **Audit Readiness** — Reports generated on demand
4. **Risk Visibility** — Scores reflect actual data health
5. **Zero Security Regression** — ED-BASE guarantees maintained

---

## 9. Implementation Constraints

### Must Follow

- ED-BASE middleware used unchanged
- ED-BASE services called, not reimplemented
- New tables only, no ED-BASE schema changes
- INR logic in ED-TRAIL only
- PRD committed before any code

### Forbidden

- Modifying ED-BASE contract files
- Duplicating auth/session/audit logic
- Hardcoding currency in ED-BASE
- Starting code before PRD approval

---

## 10. Relationship Summary

```
┌─────────────────────────────────────────────────────┐
│                     ED-TRAIL                         │
│         (Data Lineage & Integrity)                   │
│                                                      │
│   ┌─────────────────────────────────────────────┐   │
│   │  ed_trail_* tables                          │   │
│   │  Lineage API routes                         │   │
│   │  INR currency handling                      │   │
│   │  Integrity checks                           │   │
│   └─────────────────────────────────────────────┘   │
│                        │                             │
│                        │ uses                        │
│                        ▼                             │
│   ┌─────────────────────────────────────────────┐   │
│   │              ED-BASE (FROZEN)               │   │
│   │  ─────────────────────────────────────────  │   │
│   │  Auth │ Sessions │ Audit │ Idempotency      │   │
│   │  Rate Limits │ Transactions │ RLS           │   │
│   └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## FINAL STATEMENT

ED-TRAIL builds **business value** on top of ED-BASE **security guarantees**.

ED-BASE is the lock. ED-TRAIL is the value. Never confuse the two.
