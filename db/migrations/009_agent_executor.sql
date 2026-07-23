-- ORCHESTRATOR_STEERING.md §10.2 — the DB-side half of the two-layer SQL
-- safety model (O-4). The app-side sqlglot SQLGuard is the first layer; this
-- migration is the second: a privilege-dropped executor RPC so that even if
-- the guard is bypassed, the database itself permits only SELECT on an
-- allowlist of tables, under a statement timeout and row cap.
--
-- Also adds match_document_chunks (RAG vector search over document_chunks) and
-- ask_turn_traces (per-turn agent trace, O-12 / §12).
--
-- Idempotent: safe to re-run. Roles are created guarded; policies are dropped
-- then recreated; functions use CREATE OR REPLACE; the table uses IF NOT EXISTS.

-- ============================================================
-- 1. Privilege-dropped read-only roles (NOLOGIN)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ask_agent_ro') THEN
        CREATE ROLE ask_agent_ro NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ask_agent_audit_ro') THEN
        CREATE ROLE ask_agent_audit_ro NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO ask_agent_ro, ask_agent_audit_ro;

-- PostGIS/pgvector operators may live in an `extensions` schema on Supabase;
-- grant USAGE if present so ST_* / <=> resolve under the dropped role.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'extensions') THEN
        GRANT USAGE ON SCHEMA extensions TO ask_agent_ro, ask_agent_audit_ro;
    END IF;
END $$;

-- The executor runs SECURITY INVOKER as service_role (the PostgREST secret-key
-- role) and SET LOCAL ROLE-drops into these roles, so service_role must be a
-- member. (SET ROLE is forbidden inside a SECURITY DEFINER function — SQLSTATE
-- 42501 — which is why the executor is invoker-based, not definer-based.)
GRANT ask_agent_ro TO service_role;
GRANT ask_agent_audit_ro TO service_role;
DO $$
BEGIN
    EXECUTE format('GRANT ask_agent_ro TO %I', current_user);
    EXECUTE format('GRANT ask_agent_audit_ro TO %I', current_user);
END $$;

-- ============================================================
-- 2. case-scope grants + permissive RLS for ask_agent_ro
-- ------------------------------------------------------------
-- All Group A/B/I reference + C-G case + J semantic read tables, minus
-- user_directory and the audit tables. RLS is already ENABLED on these
-- (006_rls.sql) with policies TO `authenticated`; the dropped role is a
-- different Postgres role, so it needs its own permissive SELECT policy
-- (row-level jurisdiction scoping is enforced at the app tier, §4.1).
-- This list is the single source of truth for the `case` SQLGuard allowlist
-- (backend/app/agent/tools/sql.py must match it exactly).
-- ============================================================
DO $$
DECLARE
    t text;
    case_tables text[] := ARRAY[
        -- Group A / B / I — reference
        'districts', 'admin_boundaries', 'sub_divisions', 'circles',
        'police_stations', 'localities', 'officers',
        'bns_sections', 'crime_types', 'mo_codes',
        -- Group C-G — case / operational
        'persons', 'person_addresses', 'person_phones',
        'firs', 'fir_accused', 'fir_victims', 'fir_witnesses',
        'case_diary_entries', 'arrests', 'chargesheets', 'court_disposals',
        'ncr_petitions', 'history_sheets', 'history_sheet_entries',
        'gangs', 'gang_memberships', 'known_associates',
        'vehicles', 'stolen_property', 'missing_persons', 'seizures',
        'district_socioeconomic', 'events_calendar',
        -- Group J — semantic index
        'document_chunks'
    ];
BEGIN
    FOREACH t IN ARRAY case_tables
    LOOP
        EXECUTE format('GRANT SELECT ON %I TO ask_agent_ro', t);
        EXECUTE format('DROP POLICY IF EXISTS "ask_agent_ro_read" ON %I', t);
        EXECUTE format(
            'CREATE POLICY "ask_agent_ro_read" ON %I FOR SELECT TO ask_agent_ro USING (true)',
            t
        );
    END LOOP;
END $$;

-- ============================================================
-- 3. audit-scope grants + permissive RLS for ask_agent_audit_ro
-- ============================================================
DO $$
DECLARE
    t text;
    audit_tables text[] := ARRAY['query_audit_log', 'ask_turn_traces'];
BEGIN
    FOREACH t IN ARRAY audit_tables
    LOOP
        -- ask_turn_traces is created below; guard so this block is order-safe.
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_name = t) THEN
            EXECUTE format('GRANT SELECT ON %I TO ask_agent_audit_ro', t);
            EXECUTE format('DROP POLICY IF EXISTS "ask_agent_audit_ro_read" ON %I', t);
            EXECUTE format(
                'CREATE POLICY "ask_agent_audit_ro_read" ON %I FOR SELECT TO ask_agent_audit_ro USING (true)',
                t
            );
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- 4. ask_turn_traces (O-12 / §12) — append-only, service-role only
-- ============================================================
CREATE TABLE IF NOT EXISTS ask_turn_traces (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    log_id UUID REFERENCES query_audit_log(log_id),
    request_id VARCHAR(40),
    trace JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ask_turn_traces ENABLE ROW LEVEL SECURITY;
-- No policy for `authenticated` = default deny. INSERT/SELECT happen only via
-- the backend service role (bypasses RLS). Writes stay append-only.
REVOKE UPDATE, DELETE ON ask_turn_traces FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ask_turn_traces FROM anon, authenticated;

-- Grant the audit read-role now that the table exists (step 3 skipped it if
-- it ran before this CREATE on a fresh DB).
GRANT SELECT ON ask_turn_traces TO ask_agent_audit_ro;
DROP POLICY IF EXISTS "ask_agent_audit_ro_read" ON ask_turn_traces;
CREATE POLICY "ask_agent_audit_ro_read" ON ask_turn_traces
    FOR SELECT TO ask_agent_audit_ro USING (true);

-- ============================================================
-- 5. execute_agent_select — privilege-dropped SELECT executor
-- ------------------------------------------------------------
-- SECURITY INVOKER (runs as the calling service_role). SET LOCAL ROLE drops to
-- the scope's read-only role (any DML/DDL or out-of-allowlist table then fails
-- on privileges), SET LOCAL statement_timeout bounds runtime, and the row cap
-- is enforced DB-side by fetching cap+1 rows and truncating. Invoker (not
-- definer) because SET ROLE is disallowed inside SECURITY DEFINER functions.
-- ============================================================
CREATE OR REPLACE FUNCTION execute_agent_select(
    p_sql text,
    p_scope text DEFAULT 'case',
    p_row_cap int DEFAULT 200
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, extensions
AS $fn$
DECLARE
    v_role text;
    v_all jsonb;
    v_rows jsonb;
    v_total int;
    v_count int;
    v_truncated boolean := false;
BEGIN
    IF p_scope = 'audit' THEN
        v_role := 'ask_agent_audit_ro';
    ELSE
        v_role := 'ask_agent_ro';
    END IF;

    -- Privilege drop + guards (transaction-local; reset on function exit).
    EXECUTE format('SET LOCAL ROLE %I', v_role);
    PERFORM set_config('statement_timeout', '8000', true);

    EXECUTE format(
        'SELECT coalesce(jsonb_agg(to_jsonb(_t)), ''[]''::jsonb) '
        'FROM (SELECT * FROM (%s) _q LIMIT %s) _t',
        p_sql, p_row_cap + 1
    ) INTO v_all;

    v_total := jsonb_array_length(v_all);
    IF v_total > p_row_cap THEN
        v_truncated := true;
        v_count := p_row_cap;
        SELECT coalesce(jsonb_agg(e ORDER BY ord), '[]'::jsonb) INTO v_rows
        FROM jsonb_array_elements(v_all) WITH ORDINALITY AS a(e, ord)
        WHERE ord <= p_row_cap;
    ELSE
        v_rows := v_all;
        v_count := v_total;
    END IF;

    RETURN jsonb_build_object(
        'rows', v_rows,
        'row_count', v_count,
        'truncated', v_truncated
    );
END;
$fn$;

REVOKE ALL ON FUNCTION execute_agent_select(text, text, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION execute_agent_select(text, text, int) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION execute_agent_select(text, text, int) TO service_role;

-- ============================================================
-- 6. match_document_chunks — RAG vector search (§9.3)
-- ------------------------------------------------------------
-- HNSW cosine search over document_chunks. Parameterized (no model SQL), so
-- it's inherently injection-safe. Query embeddings MUST be produced with the
-- e5 "query: " prefix by the caller (search_narratives tool).
-- ============================================================
CREATE OR REPLACE FUNCTION match_document_chunks(
    p_embedding vector(768),
    p_filters jsonb DEFAULT '{}'::jsonb,
    p_k int DEFAULT 8
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, extensions
AS $fn$
    SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)
    FROM (
        SELECT
            chunk_id,
            source_table,
            source_id,
            source_field,
            left(chunk_text, 400) AS snippet,
            district_id,
            station_id,
            round((1 - (embedding <=> p_embedding))::numeric, 4) AS similarity
        FROM document_chunks
        WHERE embedding IS NOT NULL
          AND (p_filters->>'source_field' IS NULL OR source_field = p_filters->>'source_field')
          AND (p_filters->>'source_table' IS NULL OR source_table = p_filters->>'source_table')
          AND (p_filters->>'district_id'  IS NULL OR district_id  = p_filters->>'district_id')
          AND (p_filters->>'station_id'   IS NULL OR station_id   = p_filters->>'station_id')
          AND (p_filters->>'fir_id'       IS NULL OR source_id    = p_filters->>'fir_id')
        ORDER BY embedding <=> p_embedding
        LIMIT p_k
    ) t;
$fn$;

REVOKE ALL ON FUNCTION match_document_chunks(vector, jsonb, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION match_document_chunks(vector, jsonb, int) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION match_document_chunks(vector, jsonb, int) TO service_role;
