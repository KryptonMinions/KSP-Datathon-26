-- DATA_ARCHITECTURE_SCHEMA_V2.md §2. Idempotent — safe to re-run even when
-- the extensions were already enabled via the Supabase dashboard.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
