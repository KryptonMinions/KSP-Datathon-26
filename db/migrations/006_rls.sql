-- DATA_ARCHITECTURE_SCHEMA_V2.md §1.3 Layer 1 (Postgres RLS, the hard data
-- boundary). Mirrors the policy shape already documented as a template in
-- backend/sql/schema.sql (role check via
-- (auth.jwt() -> 'app_metadata' ->> 'role')), but applies the *literal*
-- §1.3 grants rather than that file's illustrative officer-scoped example:
-- investigating_officer/supervisor/analyst get a blanket SELECT across
-- Groups C-G (not row-scoped to assigned_officer_id — that finer
-- distinction is Layer 2, the orchestrator's query-class gating, which is
-- out of scope for this migration).
--
-- No role has direct INSERT/UPDATE/DELETE on any table below in v1 — writes
-- happen only through seed scripts using the service role, which bypasses
-- RLS by design. Only SELECT policies are created here.

-- ============================================================
-- Groups A, B, I — reference/lookup data. All authenticated roles read.
-- ============================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'districts', 'sub_divisions', 'circles', 'police_stations', 'officers',
        'bns_sections', 'crime_types', 'mo_codes',
        'admin_boundaries', 'localities'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
        EXECUTE format(
            'CREATE POLICY "all_roles_read" ON %I FOR SELECT TO authenticated USING (true);',
            t
        );
    END LOOP;
END $$;

-- ============================================================
-- Groups C-G — case/operational data. investigating_officer, supervisor,
-- analyst read all rows; admin gets no grant at all (deliberately no
-- policy — default deny).
-- ============================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'persons', 'person_phones', 'person_addresses',
        'firs', 'fir_accused', 'fir_victims', 'fir_witnesses',
        'case_diary_entries', 'arrests', 'chargesheets', 'court_disposals',
        'ncr_petitions', 'seizures', 'missing_persons',
        'history_sheets', 'history_sheet_entries', 'gangs',
        'gang_memberships', 'known_associates',
        'stolen_property', 'vehicles',
        'district_socioeconomic', 'events_calendar',
        -- Group J: document_chunks is derived from case-table RAG fields
        -- (complaint_text, victim_statement, etc.) — not explicitly listed
        -- in §1.3's Layer 1 breakdown, but must not be more permissive than
        -- its source data, so it gets the same operational-role policy.
        'document_chunks'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
        EXECUTE format(
            'CREATE POLICY "operational_roles_read" ON %I FOR SELECT TO authenticated '
            'USING ((auth.jwt() -> ''app_metadata'' ->> ''role'') IN '
            '(''investigating_officer'', ''supervisor'', ''analyst''));',
            t
        );
    END LOOP;
END $$;

-- ============================================================
-- Group H — query_audit_log. Admin: SELECT only. Append-only for everyone
-- (including admin) — INSERT happens exclusively via the backend service
-- role, which bypasses RLS; UPDATE/DELETE are revoked outright.
-- ============================================================

ALTER TABLE query_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "admin_read_audit_log" ON query_audit_log FOR SELECT TO authenticated
    USING ((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

REVOKE UPDATE, DELETE ON query_audit_log FROM PUBLIC;

-- reviewed_by/reviewed_at may only be set via this function, restricted to
-- the admin app-role by an explicit check (not just by GRANT/REVOKE, so the
-- restriction holds even if EXECUTE is ever broadly granted).
CREATE OR REPLACE FUNCTION review_audit_flag(p_log_id UUID, p_reviewer VARCHAR(15))
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $func$
BEGIN
    IF (auth.jwt() -> 'app_metadata' ->> 'role') IS DISTINCT FROM 'admin' THEN
        RAISE EXCEPTION 'only the admin role may review audit flags';
    END IF;

    UPDATE query_audit_log
    SET reviewed_by = p_reviewer, reviewed_at = now()
    WHERE log_id = p_log_id;
END;
$func$;

REVOKE ALL ON FUNCTION review_audit_flag(UUID, VARCHAR) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION review_audit_flag(UUID, VARCHAR) TO authenticated;
