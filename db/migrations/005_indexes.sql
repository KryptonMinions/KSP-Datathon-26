-- DATA_ARCHITECTURE_SCHEMA_V2.md §2, §3 index requirements. SEED_RUNBOOK.md
-- §3 step 5: "GiST on every geom/centroid/boundary/jurisdiction_boundary;
-- trigram GIN on persons.full_name, persons.aliases, localities.locality_name,
-- localities.aliases, vehicles.registration_number; GIN on tsvector columns;
-- HNSW vector_cosine_ops on document_chunks.embedding."

-- ============================================================
-- GiST — every geography column (point or polygon)
-- ============================================================

CREATE INDEX idx_police_stations_geom ON police_stations USING gist (geom);
CREATE INDEX idx_police_stations_jurisdiction ON police_stations USING gist (jurisdiction_boundary);
CREATE INDEX idx_admin_boundaries_geom ON admin_boundaries USING gist (geom);
CREATE INDEX idx_localities_centroid ON localities USING gist (centroid);
CREATE INDEX idx_localities_boundary ON localities USING gist (boundary);
CREATE INDEX idx_persons_geom ON persons USING gist (geom);
CREATE INDEX idx_person_addresses_geom ON person_addresses USING gist (geom);
CREATE INDEX idx_firs_geom ON firs USING gist (geom);
CREATE INDEX idx_case_diary_entries_geom ON case_diary_entries USING gist (geom);
CREATE INDEX idx_arrests_geom ON arrests USING gist (geom);
CREATE INDEX idx_ncr_petitions_geom ON ncr_petitions USING gist (geom);
CREATE INDEX idx_stolen_property_geom ON stolen_property USING gist (geom);
CREATE INDEX idx_missing_persons_geom ON missing_persons USING gist (geom);
CREATE INDEX idx_seizures_geom ON seizures USING gist (geom);
CREATE INDEX idx_events_calendar_geom ON events_calendar USING gist (geom);
CREATE INDEX idx_events_calendar_route ON events_calendar USING gist (route_geom);

-- ============================================================
-- Trigram GIN — fuzzy name/alias/plate matching (pg_trgm)
-- ============================================================

-- array_to_string() is declared STABLE (not IMMUTABLE) in Postgres's
-- catalog — a blanket volatility for the generic anyarray signature, even
-- though it's fully deterministic for TEXT[]. Index expressions require
-- IMMUTABLE, so wrap it in a trivial SQL function that is.
CREATE OR REPLACE FUNCTION immutable_array_to_string(text[]) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT array_to_string($1, ' ');
$$;

CREATE INDEX idx_persons_full_name_trgm ON persons USING gin (full_name gin_trgm_ops);
-- aliases is TEXT[]; gin_trgm_ops operates on text, so index a concatenated
-- expression (per schema note on C1) — matches the forward-geocoder pattern
-- used for localities below.
CREATE INDEX idx_persons_aliases_trgm ON persons USING gin ((immutable_array_to_string(aliases)) gin_trgm_ops);

CREATE INDEX idx_localities_name_trgm ON localities USING gin (locality_name gin_trgm_ops);
CREATE INDEX idx_localities_aliases_trgm ON localities USING gin ((immutable_array_to_string(aliases)) gin_trgm_ops);

CREATE INDEX idx_vehicles_reg_number_trgm ON vehicles USING gin (registration_number gin_trgm_ops);

-- ============================================================
-- tsvector GIN — full-text fallback (§2)
-- ============================================================

CREATE INDEX idx_firs_complaint_text_tsv ON firs USING gin (complaint_text_tsv);
CREATE INDEX idx_firs_fir_narrative_tsv ON firs USING gin (fir_narrative_tsv);
CREATE INDEX idx_case_diary_entries_text_tsv ON case_diary_entries USING gin (entry_text_tsv);
CREATE INDEX idx_mo_codes_description_tsv ON mo_codes USING gin (mo_description_tsv);
CREATE INDEX idx_chargesheets_summary_tsv ON chargesheets USING gin (summary_text_tsv);
CREATE INDEX idx_ncr_petitions_text_tsv ON ncr_petitions USING gin (petition_text_tsv);
CREATE INDEX idx_history_sheet_entries_text_tsv ON history_sheet_entries USING gin (entry_text_tsv);
CREATE INDEX idx_gangs_notes_tsv ON gangs USING gin (notes_tsv);
CREATE INDEX idx_stolen_property_description_tsv ON stolen_property USING gin (description_tsv);
CREATE INDEX idx_seizures_items_description_tsv ON seizures USING gin (items_description_tsv);
CREATE INDEX idx_events_calendar_notes_tsv ON events_calendar USING gin (notes_tsv);

-- ============================================================
-- HNSW — vector similarity (pgvector)
-- ============================================================

CREATE INDEX idx_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- Supporting FK/lookup indexes (not explicitly enumerated in §3 but needed
-- for the query patterns the schema doc describes — cheap to add now).
-- ============================================================

CREATE INDEX idx_firs_station_id ON firs (station_id);
CREATE INDEX idx_firs_district_id ON firs (district_id);
CREATE INDEX idx_firs_crime_type_id ON firs (crime_type_id);
CREATE INDEX idx_firs_mo_code_id ON firs (mo_code_id);
CREATE INDEX idx_firs_complainant_id ON firs (complainant_id);
CREATE INDEX idx_fir_accused_fir_id ON fir_accused (fir_id);
CREATE INDEX idx_fir_accused_person_id ON fir_accused (person_id);
CREATE INDEX idx_fir_victims_fir_id ON fir_victims (fir_id);
CREATE INDEX idx_case_diary_entries_fir_id ON case_diary_entries (fir_id);
CREATE INDEX idx_person_phones_phone_number ON person_phones (phone_number);
CREATE INDEX idx_known_associates_person_a ON known_associates (person_id_a);
CREATE INDEX idx_known_associates_person_b ON known_associates (person_id_b);
CREATE INDEX idx_gang_memberships_gang_id ON gang_memberships (gang_id);
CREATE INDEX idx_gang_memberships_person_id ON gang_memberships (person_id);
CREATE INDEX idx_document_chunks_source ON document_chunks (source_table, source_id);
CREATE INDEX idx_query_audit_log_officer_id ON query_audit_log (officer_id);
CREATE INDEX idx_query_audit_log_session_id ON query_audit_log (session_id);
