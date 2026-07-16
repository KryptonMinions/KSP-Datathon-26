-- DATA_ARCHITECTURE_SCHEMA_V2.md §3, Groups C (Persons), D (FIR &
-- Investigation), E (Criminal Intelligence), F (Property & Vehicles),
-- G (External & Socio-Economic).
--
-- Physical CREATE TABLE order here follows FK dependency, not the document's
-- C/D/E/F/G grouping — e.g. firs (D) must exist before person_phones (C)'s
-- source_fir_id FK, and vehicles/stolen_property (F) must exist before
-- seizures (D) references them. Each table is commented with its schema
-- group for cross-reference. One genuinely circular pair — stolen_property
-- <-> seizures — is resolved with a deferred ALTER TABLE at the end of this
-- file (stolen_property.recovery_seizure_id FK added after seizures exists).
--
-- [GEO] pattern repeated per §1.2.2-1.2.3: latitude/longitude DECIMAL(9,6) +
-- a stored generated geography(Point,4326) column (NULL when lat/lng is
-- NULL) + location_precision/geocode_source/geocode_confidence.

-- ============================================================
-- Group C — Persons (Master Entity)
-- ============================================================

-- C1. persons. v2.1 removed religion/caste/fingerprint_id/address_current/
-- address_permanent — addresses live solely in person_addresses.
CREATE TABLE persons (
    person_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(150) NOT NULL,
    full_name_kn VARCHAR(150),
    aliases TEXT[],
    gender VARCHAR(15),
    date_of_birth DATE,
    age_approx SMALLINT,
    father_name VARCHAR(150),
    mother_name VARCHAR(150),
    spouse_name VARCHAR(150),
    nationality VARCHAR(50),
    education_level VARCHAR(50),
    occupation VARCHAR(100),
    occupation_category VARCHAR(50),
    monthly_income_approx INTEGER,
    district_id CHAR(3) REFERENCES districts(district_id),
    aadhaar_last4 CHAR(4),
    phone_primary VARCHAR(15),
    phone_secondary VARCHAR(15),
    is_history_sheeted BOOLEAN NOT NULL DEFAULT FALSE,
    is_proclaimed_offender BOOLEAN NOT NULL DEFAULT FALSE,
    photo_id VARCHAR(200),
    er_cluster_id UUID,
    er_confidence DECIMAL(4,3) CHECK (er_confidence BETWEEN 0 AND 1),
    er_status VARCHAR(20) CHECK (er_status IN ('Canonical', 'Duplicate', 'Unresolved')),
    -- [GEO] — home-address point, source=generated (denormalised from the
    -- Current person_addresses row for query convenience).
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
    home_locality_id UUID REFERENCES localities(locality_id),
    passport_no VARCHAR(20),
    passport_issue_date DATE,
    passport_issue_place VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- C3. person_addresses (created before firs since it has no FK to firs).
CREATE TABLE person_addresses (
    address_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    address_text TEXT NOT NULL,
    address_type VARCHAR(15) NOT NULL CHECK (address_type IN ('Current', 'Permanent', 'Work', 'Associate')),
    station_id CHAR(10) REFERENCES police_stations(station_id),
    valid_from DATE,
    valid_to DATE,
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
    locality_id UUID REFERENCES localities(locality_id)
);

-- ============================================================
-- Group D — FIR & Investigation
-- ============================================================

-- D1. firs. FIR ID format 'KA-[DIST]-[STN]-[YEAR]-[SERIAL]' per §7.2 — a
-- natural-key VARCHAR PK, not a UUID.
CREATE TABLE firs (
    fir_id VARCHAR(20) PRIMARY KEY,
    station_id CHAR(10) NOT NULL REFERENCES police_stations(station_id),
    district_id CHAR(3) NOT NULL REFERENCES districts(district_id),
    fir_number VARCHAR(20) NOT NULL,
    fir_year SMALLINT NOT NULL,
    registration_date TIMESTAMPTZ NOT NULL,
    incident_date TIMESTAMPTZ,
    incident_date_approx BOOLEAN NOT NULL DEFAULT FALSE,
    incident_location TEXT NOT NULL,
    incident_area VARCHAR(150),
    crime_type_id VARCHAR(20) REFERENCES crime_types(crime_type_id),
    primary_bns_section VARCHAR(10) REFERENCES bns_sections(section_id),
    additional_sections TEXT[],
    ipc_sections TEXT[],
    is_pre_bns BOOLEAN NOT NULL DEFAULT FALSE,
    complaint_text TEXT,
    complaint_text_kn TEXT,
    fir_narrative TEXT,
    mo_code_id VARCHAR(15) REFERENCES mo_codes(mo_code_id),
    mo_description_free TEXT,
    weapons_used TEXT[],
    property_involved TEXT,
    complainant_id UUID REFERENCES persons(person_id),
    io_officer_id VARCHAR(15) REFERENCES officers(officer_id),
    sho_officer_id VARCHAR(15) REFERENCES officers(officer_id),
    investigation_status VARCHAR(30) NOT NULL CHECK (investigation_status IN ('Open', 'Under_Investigation', 'Chargesheet_Filed', 'Closed', 'Transferred')),
    chargesheet_deadline DATE,
    fir_type VARCHAR(20),
    is_zero_fir BOOLEAN NOT NULL DEFAULT FALSE,
    -- [GEO] — incident point, precision mix per §7.3.
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
    incident_locality_id UUID REFERENCES localities(locality_id),
    -- v2.0 FORM IF-1 alignment fields (§3 D1).
    info_received_ts TIMESTAMPTZ,
    gd_entry_number VARCHAR(10),
    gd_entry_time TIMESTAMPTZ,
    information_type VARCHAR(10) CHECK (information_type IN ('Written', 'Oral')),
    beat_number VARCHAR(10),
    direction_distance_from_ps VARCHAR(100),
    delay_reason TEXT,
    other_acts_sections TEXT[],
    inquest_ud_case_no VARCHAR(30),
    despatch_to_court_ts TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    complaint_text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(complaint_text, ''))) STORED,
    fir_narrative_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(fir_narrative, ''))) STORED,
    UNIQUE (station_id, fir_number, fir_year)
);

-- C2. person_phones — created after firs for the source_fir_id FK.
CREATE TABLE person_phones (
    phone_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    phone_number VARCHAR(15) NOT NULL,
    phone_type VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_date DATE,
    source_fir_id VARCHAR(20) REFERENCES firs(fir_id)
);

-- D2. fir_accused
CREATE TABLE fir_accused (
    fir_accused_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_id VARCHAR(20) NOT NULL REFERENCES firs(fir_id),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    role VARCHAR(20) NOT NULL CHECK (role IN ('Main_Accused', 'Co_Accused', 'Absconder', 'Unknown', 'Suspect')),
    accused_serial SMALLINT NOT NULL,
    is_arrested BOOLEAN NOT NULL DEFAULT FALSE,
    arrest_date DATE,
    is_juvenile BOOLEAN NOT NULL DEFAULT FALSE
);

-- D3. fir_victims
CREATE TABLE fir_victims (
    fir_victim_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_id VARCHAR(20) NOT NULL REFERENCES firs(fir_id),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    victim_serial SMALLINT NOT NULL,
    injury_type VARCHAR(50),
    victim_statement TEXT,
    victim_statement_kn TEXT
);

-- D4. fir_witnesses
CREATE TABLE fir_witnesses (
    fir_witness_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_id VARCHAR(20) NOT NULL REFERENCES firs(fir_id),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    witness_type VARCHAR(20) CHECK (witness_type IN ('Eyewitness', 'Panch', 'Expert', 'Character', 'Mahazar')),
    statement_recorded BOOLEAN NOT NULL DEFAULT FALSE,
    statement_date DATE
);

-- D5. case_diary_entries. [GEO] populated only for Spot_Visit-type entries
-- (§3 D5) — NULL otherwise.
CREATE TABLE case_diary_entries (
    entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_id VARCHAR(20) NOT NULL REFERENCES firs(fir_id),
    officer_id VARCHAR(15) REFERENCES officers(officer_id),
    entry_date TIMESTAMPTZ NOT NULL,
    entry_number SMALLINT NOT NULL,
    entry_text TEXT NOT NULL,
    entry_text_kn TEXT,
    action_taken VARCHAR(50),
    next_action_planned TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
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
    entry_text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', entry_text)) STORED,
    UNIQUE (fir_id, entry_number)
);

-- D6. arrests
CREATE TABLE arrests (
    arrest_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_accused_id UUID REFERENCES fir_accused(fir_accused_id),
    fir_id VARCHAR(20) NOT NULL REFERENCES firs(fir_id),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    arresting_officer_id VARCHAR(15) REFERENCES officers(officer_id),
    arrest_date TIMESTAMPTZ NOT NULL,
    arrest_location TEXT,
    remand_type VARCHAR(30),
    remand_expiry DATE,
    bail_status VARCHAR(20),
    bail_date DATE,
    is_absconding BOOLEAN NOT NULL DEFAULT FALSE,
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
    arrest_locality_id UUID REFERENCES localities(locality_id)
);

-- D7. chargesheets. self-referencing parent_chargesheet_id is fine within
-- one CREATE TABLE.
CREATE TABLE chargesheets (
    chargesheet_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_id VARCHAR(20) NOT NULL UNIQUE REFERENCES firs(fir_id),
    filing_officer_id VARCHAR(15) REFERENCES officers(officer_id),
    filing_date DATE NOT NULL,
    court_name VARCHAR(150),
    court_case_number VARCHAR(50),
    sections_applied TEXT[] NOT NULL,
    sections_applied_ipc TEXT[],
    num_accused SMALLINT,
    num_witnesses SMALLINT,
    summary_text TEXT,
    filing_status VARCHAR(20),
    is_supplementary BOOLEAN NOT NULL DEFAULT FALSE,
    parent_chargesheet_id UUID REFERENCES chargesheets(chargesheet_id),
    summary_text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(summary_text, ''))) STORED
);

-- D8. court_disposals
CREATE TABLE court_disposals (
    disposal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chargesheet_id UUID REFERENCES chargesheets(chargesheet_id),
    fir_id VARCHAR(20) REFERENCES firs(fir_id),
    disposal_date DATE,
    court_name VARCHAR(150),
    outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('Convicted', 'Acquitted', 'Compounded', 'Withdrawn', 'Pending')),
    sentence_details TEXT,
    notes TEXT
);

-- D9. ncr_petitions
CREATE TABLE ncr_petitions (
    petition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    petition_type VARCHAR(20) NOT NULL CHECK (petition_type IN ('NCR', 'Petition', 'CSR', 'Dispute', 'Nuisance', 'Verification')),
    ncr_number VARCHAR(20),
    station_id CHAR(10) REFERENCES police_stations(station_id),
    district_id CHAR(3) REFERENCES districts(district_id),
    complainant_id UUID REFERENCES persons(person_id),
    respondent_id UUID REFERENCES persons(person_id),
    received_date TIMESTAMPTZ NOT NULL,
    category VARCHAR(50),
    petition_text TEXT NOT NULL,
    petition_text_kn TEXT,
    address_text TEXT,
    locality_id UUID REFERENCES localities(locality_id),
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
    assigned_officer_id VARCHAR(15) REFERENCES officers(officer_id),
    status VARCHAR(25) NOT NULL CHECK (status IN ('Open', 'Closed', 'Escalated_To_FIR', 'Referred')),
    escalated_fir_id VARCHAR(20) REFERENCES firs(fir_id),
    closed_date DATE,
    petition_text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', petition_text)) STORED,
    CHECK (status <> 'Escalated_To_FIR' OR escalated_fir_id IS NOT NULL)
);

-- ============================================================
-- Group E — Criminal Intelligence
-- ============================================================

-- E1. history_sheets
CREATE TABLE history_sheets (
    history_sheet_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL UNIQUE REFERENCES persons(person_id),
    hs_number VARCHAR(30) NOT NULL,
    station_id CHAR(10) REFERENCES police_stations(station_id),
    opened_date DATE NOT NULL,
    opened_by_officer VARCHAR(15) REFERENCES officers(officer_id),
    category VARCHAR(20) NOT NULL CHECK (category IN ('Rowdy', 'Goonda', 'History_Sheeter', 'Bootlegger', 'Gambler', 'Other')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_reviewed_date DATE,
    review_notes TEXT,
    risk_level VARCHAR(10) NOT NULL CHECK (risk_level IN ('Low', 'Medium', 'High', 'Very_High')),
    total_cases_count SMALLINT NOT NULL DEFAULT 0,
    conviction_count SMALLINT NOT NULL DEFAULT 0,
    absconding_count SMALLINT NOT NULL DEFAULT 0,
    last_crime_date DATE
);

-- E2. history_sheet_entries
CREATE TABLE history_sheet_entries (
    hs_entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    history_sheet_id UUID NOT NULL REFERENCES history_sheets(history_sheet_id),
    entry_date DATE NOT NULL,
    entry_text TEXT NOT NULL,
    officer_id VARCHAR(15) REFERENCES officers(officer_id),
    related_fir_id VARCHAR(20) REFERENCES firs(fir_id),
    entry_text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', entry_text)) STORED
);

-- E3. gangs
CREATE TABLE gangs (
    gang_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gang_name VARCHAR(150) NOT NULL,
    gang_name_kn VARCHAR(150),
    primary_crime_type VARCHAR(20) REFERENCES crime_types(crime_type_id),
    operating_district CHAR(3) REFERENCES districts(district_id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    formation_approx_year SMALLINT,
    known_strength SMALLINT,
    notes TEXT,
    notes_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(notes, ''))) STORED
);

-- E4. gang_memberships
CREATE TABLE gang_memberships (
    membership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gang_id UUID NOT NULL REFERENCES gangs(gang_id),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    role_in_gang VARCHAR(20) NOT NULL CHECK (role_in_gang IN ('Leader', 'Sub-Leader', 'Member', 'Associate', 'Informant', 'Financier')),
    joined_approx_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    left_date DATE,
    notes TEXT
);

-- E5. known_associates
CREATE TABLE known_associates (
    association_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id_a UUID NOT NULL REFERENCES persons(person_id),
    person_id_b UUID NOT NULL REFERENCES persons(person_id),
    association_type VARCHAR(20) NOT NULL CHECK (association_type IN ('Co_Accused', 'Family', 'Employer_Employee', 'Neighbour', 'Gang_Member', 'Phone_Contact', 'Financier', 'Known_Receiver')),
    first_seen_fir_id VARCHAR(20) REFERENCES firs(fir_id),
    confidence VARCHAR(10) NOT NULL CHECK (confidence IN ('Confirmed', 'Suspected')),
    notes TEXT,
    CHECK (person_id_a < person_id_b)
);

-- ============================================================
-- Group F — Property & Vehicles
-- ============================================================

-- F2. vehicles — created before stolen_property/seizures since both
-- reference it.
CREATE TABLE vehicles (
    vehicle_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    registration_number VARCHAR(15) NOT NULL UNIQUE,
    vehicle_type VARCHAR(30) NOT NULL,
    make VARCHAR(50),
    model VARCHAR(50),
    color VARCHAR(30),
    year_of_manufacture SMALLINT,
    owner_person_id UUID REFERENCES persons(person_id),
    is_stolen BOOLEAN NOT NULL DEFAULT FALSE,
    stolen_fir_id VARCHAR(20) REFERENCES firs(fir_id),
    theft_date DATE,
    is_recovered BOOLEAN NOT NULL DEFAULT FALSE,
    recovery_date DATE
);

-- F1. stolen_property. recovery_seizure_id FK to seizures is added via
-- ALTER TABLE at the end of this file — seizures doesn't exist yet and also
-- references this table (linked_property_id), a genuine circular pair.
CREATE TABLE stolen_property (
    property_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_id VARCHAR(20) NOT NULL REFERENCES firs(fir_id),
    property_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    description_kn TEXT,
    estimated_value_inr INTEGER,
    serial_number VARCHAR(100),
    is_recovered BOOLEAN NOT NULL DEFAULT FALSE,
    recovery_date DATE,
    recovery_fir_id VARCHAR(20) REFERENCES firs(fir_id),
    recovery_location TEXT,
    recovery_locality_id UUID REFERENCES localities(locality_id),
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
    recovery_seizure_id UUID,
    description_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', description)) STORED
);

-- D11. missing_persons — placed here (needs persons, firs, police_stations,
-- localities only; no dependency on seizures/stolen_property).
CREATE TABLE missing_persons (
    mp_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES persons(person_id),
    reported_by_person_id UUID REFERENCES persons(person_id),
    reported_fir_id VARCHAR(20) REFERENCES firs(fir_id),
    station_id CHAR(10) REFERENCES police_stations(station_id),
    report_date TIMESTAMPTZ NOT NULL,
    last_seen_date TIMESTAMPTZ,
    last_seen_location TEXT,
    locality_id UUID REFERENCES localities(locality_id),
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
    physical_description TEXT,
    status VARCHAR(15) NOT NULL CHECK (status IN ('Missing', 'Traced', 'Matched_UDB')),
    traced_date DATE,
    traced_location TEXT
);

-- D10. seizures — mahazar/panchnama records. Created after stolen_property
-- and vehicles so linked_property_id/linked_vehicle_id can be real FKs.
CREATE TABLE seizures (
    seizure_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fir_id VARCHAR(20) NOT NULL REFERENCES firs(fir_id),
    case_diary_entry_id UUID REFERENCES case_diary_entries(entry_id),
    mahazar_number VARCHAR(30) NOT NULL,
    seizure_type VARCHAR(20) NOT NULL CHECK (seizure_type IN ('Property', 'Weapon', 'Vehicle', 'Document', 'Narcotics', 'Cash', 'Other')),
    seizure_date TIMESTAMPTZ NOT NULL,
    seizure_location TEXT NOT NULL,
    locality_id UUID REFERENCES localities(locality_id),
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
    seizing_officer_id VARCHAR(15) REFERENCES officers(officer_id),
    pancha_1_person_id UUID REFERENCES persons(person_id),
    pancha_2_person_id UUID REFERENCES persons(person_id),
    items_description TEXT NOT NULL,
    items_description_kn TEXT,
    linked_property_id UUID REFERENCES stolen_property(property_id),
    linked_vehicle_id UUID REFERENCES vehicles(vehicle_id),
    muddemal_number VARCHAR(30),
    custody_status VARCHAR(20) CHECK (custody_status IN ('In_Custody', 'Court_Deposit', 'FSL', 'Released')),
    items_description_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', items_description)) STORED
);

-- Close the circular stolen_property <-> seizures reference now that both
-- tables exist.
ALTER TABLE stolen_property
    ADD CONSTRAINT fk_stolen_property_recovery_seizure
    FOREIGN KEY (recovery_seizure_id) REFERENCES seizures(seizure_id);

-- ============================================================
-- Group G — External & Socio-Economic
-- ============================================================

-- G1. district_socioeconomic
CREATE TABLE district_socioeconomic (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    district_id CHAR(3) NOT NULL REFERENCES districts(district_id),
    data_year SMALLINT NOT NULL,
    population INTEGER,
    population_urban_pct DECIMAL(5,2),
    literacy_rate DECIMAL(5,2),
    unemployment_rate DECIMAL(5,2),
    per_capita_income_inr INTEGER,
    poverty_rate DECIMAL(5,2),
    migrant_population_pct DECIMAL(5,2),
    police_stations_count SMALLINT,
    officers_per_lakh_pop DECIMAL(6,2),
    data_source VARCHAR(200) NOT NULL,
    UNIQUE (district_id, data_year)
);

-- G2. events_calendar
CREATE TABLE events_calendar (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name VARCHAR(150) NOT NULL,
    event_name_kn VARCHAR(150),
    event_type VARCHAR(50) NOT NULL,
    district_id CHAR(3) REFERENCES districts(district_id),
    station_id CHAR(10) REFERENCES police_stations(station_id),
    event_date_start TIMESTAMPTZ NOT NULL,
    event_date_end TIMESTAMPTZ,
    expected_footfall INTEGER,
    historical_incident_count SMALLINT,
    notes TEXT,
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
    venue_locality_id UUID REFERENCES localities(locality_id),
    route_geom geography(LineString, 4326),
    notes_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(notes, ''))) STORED
);
