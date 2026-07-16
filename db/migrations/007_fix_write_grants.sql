-- Fixes a gap in 006_rls.sql found by a live JWT-authenticated RLS test
-- (scripts/seed/verify_rls_live.py): every table in the public schema
-- carries Supabase's default per-table privilege grants of INSERT, UPDATE,
-- DELETE, and TRUNCATE to both `authenticated` AND `anon` (auto-applied to
-- every new table in a Supabase project, independent of anything this
-- migration set did or didn't do). 006_rls.sql only revoked UPDATE/DELETE
-- on query_audit_log FROM PUBLIC — that does nothing against a privilege
-- granted directly to `authenticated`/`anon`, not inherited via PUBLIC.
--
-- Net effect before this migration: RLS policies correctly gated SELECT
-- (the only command any policy in 006_rls.sql covers), but INSERT/UPDATE/
-- DELETE/TRUNCATE were wide open for every authenticated *and* anonymous
-- request against every table, completely bypassing the "writes happen
-- only through the service role" design stated in 006_rls.sql's own
-- header comment.
--
-- Fix: explicitly revoke write privileges from anon and authenticated on
-- every table in the public schema. SELECT is untouched — RLS policies
-- already gate it correctly, and this migration doesn't add or remove any
-- policy, only closes the direct-grant gap alongside them.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM anon, authenticated;

-- Also fix default privileges so any future table created in this schema
-- doesn't silently reopen the same gap.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM anon, authenticated;
