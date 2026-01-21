-- ED-BASE Migration 008: Row-Level Security Policies
-- Purpose: Team isolation enforced at database level (Invariant #3)
-- Backend authorization overrides frontend (Invariant #6)

-- WHY RLS: Defense in depth. Even if application code has bugs,
-- the database prevents cross-team data access.

-- Enable RLS on all application tables
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_webhooks ENABLE ROW LEVEL SECURITY;

-- Audit logs have special handling (read-only, no user filtering)
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- TEAM POLICIES
-- ============================================================

-- WHY: Users can only see teams they belong to
DROP POLICY IF EXISTS teams_select_policy ON teams;
CREATE POLICY teams_select_policy ON teams
    FOR SELECT
    USING (
        deleted_at IS NULL AND
        id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() AND is_active = true
        )
    );

-- WHY: Only team owners can update team settings
DROP POLICY IF EXISTS teams_update_policy ON teams;
CREATE POLICY teams_update_policy ON teams
    FOR UPDATE
    USING (
        id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() 
            AND is_active = true 
            AND role = 'owner'
        )
    );

-- WHY: Anyone can create a team (they become owner)
DROP POLICY IF EXISTS teams_insert_policy ON teams;
CREATE POLICY teams_insert_policy ON teams
    FOR INSERT
    WITH CHECK (true);

-- ============================================================
-- TEAM MEMBERSHIP POLICIES
-- ============================================================

-- WHY: Users can see memberships for their teams
DROP POLICY IF EXISTS memberships_select_policy ON team_memberships;
CREATE POLICY memberships_select_policy ON team_memberships
    FOR SELECT
    USING (
        team_id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() AND is_active = true
        )
    );

-- WHY: Only admins/owners can add members
DROP POLICY IF EXISTS memberships_insert_policy ON team_memberships;
CREATE POLICY memberships_insert_policy ON team_memberships
    FOR INSERT
    WITH CHECK (
        team_id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() 
            AND is_active = true 
            AND role IN ('owner', 'admin')
        )
    );

-- WHY: Only admins/owners can modify memberships
DROP POLICY IF EXISTS memberships_update_policy ON team_memberships;
CREATE POLICY memberships_update_policy ON team_memberships
    FOR UPDATE
    USING (
        team_id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() 
            AND is_active = true 
            AND role IN ('owner', 'admin')
        )
    );

-- ============================================================
-- PAYMENT POLICIES
-- ============================================================

-- WHY: Users can only see their team's payments
DROP POLICY IF EXISTS payments_select_policy ON payments;
CREATE POLICY payments_select_policy ON payments
    FOR SELECT
    USING (
        team_id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() AND is_active = true
        )
    );

-- WHY: Only team members can create payments for their team
DROP POLICY IF EXISTS payments_insert_policy ON payments;
CREATE POLICY payments_insert_policy ON payments
    FOR INSERT
    WITH CHECK (
        user_id = auth.uid() AND
        team_id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() AND is_active = true
        )
    );

-- WHY: Payment updates require admin role (status changes)
DROP POLICY IF EXISTS payments_update_policy ON payments;
CREATE POLICY payments_update_policy ON payments
    FOR UPDATE
    USING (
        team_id IN (
            SELECT team_id FROM team_memberships 
            WHERE user_id = auth.uid() 
            AND is_active = true 
            AND role IN ('owner', 'admin')
        )
    );

-- ============================================================
-- SESSION POLICIES
-- ============================================================

-- WHY: Users can only see their own sessions
DROP POLICY IF EXISTS sessions_select_policy ON sessions;
CREATE POLICY sessions_select_policy ON sessions
    FOR SELECT
    USING (user_id = auth.uid());

-- WHY: Sessions created only for authenticated user
DROP POLICY IF EXISTS sessions_insert_policy ON sessions;
CREATE POLICY sessions_insert_policy ON sessions
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- WHY: Users can revoke their own sessions (logout)
DROP POLICY IF EXISTS sessions_update_policy ON sessions;
CREATE POLICY sessions_update_policy ON sessions
    FOR UPDATE
    USING (user_id = auth.uid());

-- ============================================================
-- IDEMPOTENCY KEY POLICIES
-- ============================================================

-- WHY: Users can only see their own idempotency keys
DROP POLICY IF EXISTS idempotency_select_policy ON idempotency_keys;
CREATE POLICY idempotency_select_policy ON idempotency_keys
    FOR SELECT
    USING (user_id = auth.uid());

-- WHY: Users create their own keys
DROP POLICY IF EXISTS idempotency_insert_policy ON idempotency_keys;
CREATE POLICY idempotency_insert_policy ON idempotency_keys
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- WHY: Users can update their pending keys
DROP POLICY IF EXISTS idempotency_update_policy ON idempotency_keys;
CREATE POLICY idempotency_update_policy ON idempotency_keys
    FOR UPDATE
    USING (user_id = auth.uid());

-- ============================================================
-- AUDIT LOG POLICIES (Special: Read-Only, Admin Access)
-- ============================================================

-- WHY: Audit logs readable only by system/admin
-- Normal users should NOT see raw audit logs
DROP POLICY IF EXISTS audit_logs_select_policy ON audit_logs;
CREATE POLICY audit_logs_select_policy ON audit_logs
    FOR SELECT
    USING (
        -- Only allow select for users with 'owner' role in any team
        -- In practice, this would be further restricted to specific admin roles
        EXISTS (
            SELECT 1 FROM team_memberships 
            WHERE user_id = auth.uid() 
            AND is_active = true 
            AND role = 'owner'
        )
    );

-- WHY: Audit logs are insert-only from application
DROP POLICY IF EXISTS audit_logs_insert_policy ON audit_logs;
CREATE POLICY audit_logs_insert_policy ON audit_logs
    FOR INSERT
    WITH CHECK (true);

-- NO UPDATE OR DELETE POLICIES
-- Combined with triggers, this enforces immutability

-- ============================================================
-- WEBHOOK POLICIES (System Access Only)
-- ============================================================

-- WHY: Webhooks are processed by system, not user-facing
DROP POLICY IF EXISTS webhooks_select_policy ON processed_webhooks;
CREATE POLICY webhooks_select_policy ON processed_webhooks
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM team_memberships 
            WHERE user_id = auth.uid() 
            AND is_active = true 
            AND role IN ('owner', 'admin')
        )
    );

-- Application service role handles inserts
DROP POLICY IF EXISTS webhooks_insert_policy ON processed_webhooks;
CREATE POLICY webhooks_insert_policy ON processed_webhooks
    FOR INSERT
    WITH CHECK (true);

COMMENT ON POLICY teams_select_policy ON teams IS 'Users see only teams they belong to. Deleted teams hidden.';
COMMENT ON POLICY payments_select_policy ON payments IS 'Team isolation. Users see only their teams payments.';
COMMENT ON POLICY sessions_select_policy ON sessions IS 'Users manage only their own sessions.';
COMMENT ON POLICY audit_logs_select_policy ON audit_logs IS 'Audit logs visible only to team owners. No UPDATE/DELETE allowed.';
