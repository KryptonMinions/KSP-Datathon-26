-- DATA_ARCHITECTURE_SCHEMA_V2.md §3, Groups A (Jurisdiction & Officer
-- Masters), B (Lookup/Reference), I (Geospatial Reference).
-- Created in FK dependency order, not strictly A->B->I document order:
-- districts -> admin_boundaries -> sub_divisions -> circles ->
-- police_stations -> localities -> officers -> bns_sections -> crime_types
-- -> mo_codes.
--
-- [GEO] pattern (§1.2.2-1.2.3): latitude/longitude + a stored generated
-- geography(Point,4326) column, NULL when lat/lng is NULL, plus the
-- precision/source/confidence metadata triplet. Applied inline per table
-- below (police_stations only, in this file — the other 11 [GEO]-bearing
-- tables live in 003_case_tables.sql).

-- ============================================================
-- Group A — Jurisdiction & Officer Masters
-- ============================================================

-- A1. districts — KSP police units (31 district units + 6 commissionerates),
-- not revenue districts. See db/reference/district_units.csv for the
-- authoritative code list once Stage 3 populates it.
CREATE TABLE districts (
    district_id CHAR(3) PRIMARY KEY,
    district_name VARCHAR(100) NOT NULL,
    district_name_kn VARCHAR(100),
    unit_type VARCHAR(15) NOT NULL CHECK (unit_type IN ('District', 'Commissionerate')),
    division VARCHAR(50),
    hq_city VARCHAR(100),
    centroid_latitude DECIMAL(9,6),
    centroid_longitude DECIMAL(9,6)
);

-- I1. admin_boundaries — real polygons (State/District/Taluk/Hobli).
-- Created here (not in the later "Group I" position in the doc) because
-- police_stations.jurisdiction_boundary and localities both logically
-- follow from having district polygons available first.
CREATE TABLE admin_boundaries (
    boundary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    boundary_type VARCHAR(15) NOT NULL CHECK (boundary_type IN ('State', 'District', 'Taluk', 'Hobli')),
    name VARCHAR(150) NOT NULL,
    name_kn VARCHAR(150),
    ref_district_id CHAR(3) REFERENCES districts(district_id),
    geom geography(MultiPolygon, 4326) NOT NULL,
    source VARCHAR(30) NOT NULL CHECK (source IN ('KGIS', 'DataMeet', 'OSM'))
);

-- A2. sub_divisions — synthesized groupings (§6), not a real open dataset.
CREATE TABLE sub_divisions (
    subdivision_id CHAR(6) PRIMARY KEY,
    subdivision_name VARCHAR(100) NOT NULL,
    district_id CHAR(3) NOT NULL REFERENCES districts(district_id)
);

-- A3. circles — synthesized groupings (§6).
CREATE TABLE circles (
    circle_id CHAR(8) PRIMARY KEY,
    circle_name VARCHAR(100) NOT NULL,
    subdivision_id CHAR(6) NOT NULL REFERENCES sub_divisions(subdivision_id)
);

-- A4. police_stations. circle_id is nullable: seeding order populates
-- stations before circles are synthesized (SEED_RUNBOOK.md §7.6 step 3),
-- so the FK is filled in by a later UPDATE, not at insert time.
CREATE TABLE police_stations (
    station_id CHAR(10) PRIMARY KEY,
    station_name VARCHAR(150) NOT NULL,
    station_name_kn VARCHAR(150),
    circle_id CHAR(8) REFERENCES circles(circle_id),
    district_id CHAR(3) NOT NULL REFERENCES districts(district_id),
    station_type VARCHAR(30),
    address TEXT,
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    geom geography(Point, 4326) GENERATED ALWAYS AS (
        CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
             THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        END
    ) STORED,
    location_precision VARCHAR(15) CHECK (location_precision IN ('exact', 'street', 'locality', 'station', 'district')),
    geocode_source VARCHAR(15) CHECK (geocode_source IN ('gps', 'gazetteer', 'manual', 'generated')),
    geocode_confidence DECIMAL(4,3) CHECK (geocode_confidence BETWEEN 0 AND 1),
    jurisdiction_boundary geography(MultiPolygon, 4326),
    phone VARCHAR(15),
    established_year SMALLINT
);

-- I2. localities — the geocoding gazetteer. self-referencing FK
-- (parent_locality_id) is fine within a single CREATE TABLE.
CREATE TABLE localities (
    locality_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    locality_name VARCHAR(150) NOT NULL,
    locality_name_kn VARCHAR(150),
    aliases TEXT[],
    locality_type VARCHAR(15) NOT NULL CHECK (locality_type IN ('Ward', 'Village', 'Area', 'Layout', 'Town', 'Hobli')),
    district_id CHAR(3) REFERENCES districts(district_id),
    primary_station_id CHAR(10) REFERENCES police_stations(station_id),
    parent_locality_id UUID REFERENCES localities(locality_id),
    pincode CHAR(6),
    centroid geography(Point, 4326) NOT NULL,
    boundary geography(MultiPolygon, 4326),
    source VARCHAR(30) NOT NULL CHECK (source IN ('KGIS', 'DataMeet', 'OSM', 'Synthetic'))
);

-- A5. officers
CREATE TABLE officers (
    officer_id VARCHAR(15) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    name_kn VARCHAR(150),
    rank VARCHAR(50) NOT NULL,
    rank_code VARCHAR(10),
    station_id CHAR(10) REFERENCES police_stations(station_id),
    district_id CHAR(3) REFERENCES districts(district_id),
    role VARCHAR(30) NOT NULL CHECK (role IN ('IO', 'SHO', 'Circle_Inspector', 'Supervisor', 'Analyst', 'Admin')),
    -- Nullable link to Supabase auth.users.id for the 4 demo login accounts;
    -- used by RLS auth.uid() scoping and the audit writer. No FK constraint
    -- to auth.users — that table lives in a different schema and Supabase
    -- manages its lifecycle independently.
    auth_user_id UUID,
    date_of_joining DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ============================================================
-- Group B — Lookup / Reference
-- ============================================================

-- B1. bns_sections. is_cognizable/is_bailable are NOT NULL per spec even
-- though neither source PDF contains a classification schedule
-- (SEED_RUNBOOK.md §2.1) — Stage 3 ingest fills these from a public BNSS
-- First Schedule reference (documented per-row in bns_sections.source_note,
-- carried as a comment column during load, not part of this table).
CREATE TABLE bns_sections (
    section_id VARCHAR(10) PRIMARY KEY,
    bns_section VARCHAR(20) NOT NULL,
    bns_description TEXT NOT NULL,
    ipc_equivalent VARCHAR(20),
    ipc_description TEXT,
    offence_category VARCHAR(50) CHECK (offence_category IN ('Property', 'Person', 'Sexual', 'Economic', 'Public_Order', 'Narcotics', 'Cyber')),
    is_cognizable BOOLEAN NOT NULL,
    is_bailable BOOLEAN NOT NULL,
    max_punishment_yrs SMALLINT,
    chargesheet_days SMALLINT NOT NULL
);

-- B2. crime_types
CREATE TABLE crime_types (
    crime_type_id VARCHAR(20) PRIMARY KEY,
    crime_type_name VARCHAR(100) NOT NULL,
    crime_type_name_kn VARCHAR(100),
    parent_category VARCHAR(50) NOT NULL,
    primary_bns_section VARCHAR(10) REFERENCES bns_sections(section_id),
    severity_level SMALLINT NOT NULL CHECK (severity_level BETWEEN 1 AND 5)
);

-- B3. mo_codes. mo_description carries both the RAG chunking source and a
-- tsvector full-text fallback (§2); GIN index on the tsvector lives in
-- 005_indexes.sql.
CREATE TABLE mo_codes (
    mo_code_id VARCHAR(15) PRIMARY KEY,
    crime_type_id VARCHAR(20) REFERENCES crime_types(crime_type_id),
    mo_description TEXT NOT NULL,
    mo_description_kn TEXT,
    target_type VARCHAR(50) CHECK (target_type IN ('Residential', 'Commercial', 'Vehicle', 'Person', 'ATM', 'Temple')),
    time_pattern VARCHAR(50) CHECK (time_pattern IN ('Night', 'Early_Morning', 'Business_Hours', 'Evening', 'Variable')),
    tool_used VARCHAR(100),
    typical_gang_size SMALLINT,
    mo_description_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', mo_description)) STORED
);
