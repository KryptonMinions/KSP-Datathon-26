-- ORCHESTRATOR_STEERING.md §9.4 references "existing migration-008
-- resolve_*_candidates RPCs" but no such migration file was ever committed to
-- this repo — the three functions below exist live in Supabase (created out
-- of band, presumably via the SQL editor, while building the semantic layer)
-- but a fresh database rebuilt from db/migrations/*.sql would be missing them
-- entirely. This file captures the verified live definitions (via
-- pg_get_functiondef) so migrations stay the source of truth. Applying this
-- against the current DB is a no-op (CREATE OR REPLACE, identical body).
--
-- Fuzzy entity resolution over the pg_trgm indexes from 005_indexes.sql
-- (idx_persons_full_name_trgm, idx_persons_aliases_trgm,
-- idx_vehicles_reg_number_trgm, idx_localities_name_trgm,
-- idx_localities_aliases_trgm). Fixed, parametrized SQL — the search text is
-- always a bound parameter, never concatenated, so no injection surface.
--
-- Not SECURITY DEFINER: these run as the invoking role. In practice that's
-- always service_role (PostgREST secret-key calls from the agent tool layer),
-- which already bypasses RLS, so invoker vs definer is not a privilege gap
-- here — anon/authenticated have EXECUTE revoked outright below regardless.

-- ============================================================
-- resolve_person_candidates — trigram match on full_name/aliases (+ optional
-- Kannada full_name_kn/alias match via q_kn). match_method explains which
-- path matched (exact_alias | exact_kn | trigram_name | trigram_alias |
-- trigram_kn) for debugging/citation display.
-- ============================================================
CREATE OR REPLACE FUNCTION resolve_person_candidates(q text, q_kn text DEFAULT NULL::text, limit_n integer DEFAULT 5)
RETURNS TABLE(person_id uuid, er_cluster_id uuid, full_name text, match_method text, similarity double precision)
LANGUAGE sql
STABLE
AS $fn$
    SELECT
        p.person_id,
        p.er_cluster_id,
        p.full_name,
        CASE
            WHEN q = ANY(p.aliases) THEN 'exact_alias'
            WHEN q_kn IS NOT NULL AND (p.full_name_kn = q_kn OR q_kn = ANY(p.aliases)) THEN 'exact_kn'
            WHEN p.full_name % q THEN 'trigram_name'
            WHEN EXISTS (SELECT 1 FROM unnest(p.aliases) a WHERE a % q) THEN 'trigram_alias'
            ELSE 'trigram_kn'
        END AS match_method,
        GREATEST(
            similarity(p.full_name, q),
            COALESCE((SELECT max(similarity(a, q)) FROM unnest(p.aliases) a), 0),
            CASE WHEN q_kn IS NOT NULL THEN similarity(coalesce(p.full_name_kn, ''), q_kn) ELSE 0 END
        ) AS similarity
    FROM persons p
    WHERE p.full_name % q
       OR q = ANY(p.aliases)
       OR EXISTS (SELECT 1 FROM unnest(p.aliases) a WHERE a % q)
       OR (q_kn IS NOT NULL AND (
             p.full_name_kn = q_kn
             OR q_kn = ANY(p.aliases)
             OR similarity(coalesce(p.full_name_kn, ''), q_kn) > 0.35
           ))
    ORDER BY similarity DESC
    LIMIT limit_n;
$fn$;

-- ============================================================
-- resolve_vehicle_candidates — exact plate match first, trigram fallback
-- (typo-tolerant plate lookup) only when no exact match exists.
-- ============================================================
CREATE OR REPLACE FUNCTION resolve_vehicle_candidates(plate text, limit_n integer DEFAULT 5)
RETURNS TABLE(vehicle_id uuid, registration_number text, match_method text, similarity double precision)
LANGUAGE sql
STABLE
AS $fn$
    WITH exact AS (
        SELECT v.vehicle_id, v.registration_number, 'exact'::text AS match_method, 1.0::double precision AS similarity
        FROM vehicles v
        WHERE v.registration_number = plate
    )
    SELECT * FROM exact
    UNION ALL
    SELECT v.vehicle_id, v.registration_number, 'trigram'::text, similarity(v.registration_number, plate)
    FROM vehicles v
    WHERE NOT EXISTS (SELECT 1 FROM exact)
      AND v.registration_number % plate
    ORDER BY similarity DESC
    LIMIT limit_n;
$fn$;

-- ============================================================
-- resolve_locality_candidates — trigram match on locality_name/aliases,
-- threshold-filtered (default 0.35), returns centroid lat/lng directly.
-- ============================================================
CREATE OR REPLACE FUNCTION resolve_locality_candidates(q text, threshold double precision DEFAULT 0.35, limit_n integer DEFAULT 5)
RETURNS TABLE(locality_id uuid, locality_name text, centroid_lat double precision, centroid_lng double precision, similarity double precision)
LANGUAGE sql
STABLE
AS $fn$
    WITH scored AS (
        SELECT
            l.locality_id,
            l.locality_name,
            ST_Y(l.centroid::geometry) AS centroid_lat,
            ST_X(l.centroid::geometry) AS centroid_lng,
            GREATEST(
                similarity(l.locality_name, q),
                COALESCE((SELECT max(similarity(a, q)) FROM unnest(l.aliases) a), 0)
            ) AS similarity
        FROM localities l
        WHERE l.locality_name % q
           OR EXISTS (SELECT 1 FROM unnest(l.aliases) a WHERE a % q)
    )
    SELECT *
    FROM scored
    WHERE similarity >= threshold
    ORDER BY similarity DESC
    LIMIT limit_n;
$fn$;

-- ============================================================
-- Grants — service_role only (matches the live grants exactly).
-- ============================================================
REVOKE ALL ON FUNCTION resolve_person_candidates(text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION resolve_person_candidates(text, text, integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION resolve_person_candidates(text, text, integer) TO service_role;

REVOKE ALL ON FUNCTION resolve_vehicle_candidates(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION resolve_vehicle_candidates(text, integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION resolve_vehicle_candidates(text, integer) TO service_role;

REVOKE ALL ON FUNCTION resolve_locality_candidates(text, double precision, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION resolve_locality_candidates(text, double precision, integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION resolve_locality_candidates(text, double precision, integer) TO service_role;
