-- DATA_ARCHITECTURE_SCHEMA_V2.md §3, Group H (Audit & Governance) and
-- Group J (Semantic Index). Append-only enforcement for query_audit_log
-- (REVOKE UPDATE/DELETE + the review_audit_flag SECURITY DEFINER function)
-- lives in 006_rls.sql alongside the rest of the permission model, not here
-- — this file only creates table structure.

-- ============================================================
-- Group H — Audit & Governance
-- ============================================================

-- H1. query_audit_log. Written by the backend service role only (§1.3);
-- no role has direct INSERT/UPDATE/DELETE in v1 except the append path.
CREATE TABLE query_audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    officer_id VARCHAR(15) REFERENCES officers(officer_id),
    session_id VARCHAR(100) NOT NULL,
    query_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    query_text TEXT NOT NULL,
    query_language VARCHAR(10),
    query_type VARCHAR(20) CHECK (query_type IN ('lookup', 'case_detail', 'pattern', 'network', 'geo_analytics', 'trend', 'summary', 'audit')),
    records_accessed TEXT[],
    response_summary TEXT,
    components_used TEXT[],
    is_flagged BOOLEAN NOT NULL DEFAULT FALSE,
    flag_reason TEXT,
    reviewed_by VARCHAR(15) REFERENCES officers(officer_id),
    reviewed_at TIMESTAMPTZ,
    -- v2.0 additions
    normalized_query_text TEXT,
    input_modality VARCHAR(10) CHECK (input_modality IN ('text', 'voice')),
    sarvam_request_id VARCHAR(64),
    response_reason VARCHAR(20) CHECK (response_reason IN ('answered', 'not_found', 'low_confidence', 'out_of_scope', 'invalid_reference')),
    thread_id UUID,
    request_id VARCHAR(40)
);

-- ============================================================
-- Group J — Semantic Index
-- ============================================================

-- J1. document_chunks. Table + HNSW index created now (embedding population
-- deferred to a follow-up step per the data-generation plan's decision 2 —
-- local e5-base embedding backfill is a separate run, not part of this
-- migration/seed pass).
CREATE TABLE document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_table VARCHAR(40) NOT NULL,
    source_id VARCHAR(40) NOT NULL,
    source_field VARCHAR(40) NOT NULL,
    chunk_index SMALLINT NOT NULL,
    sentence_start SMALLINT,
    sentence_end SMALLINT,
    chunk_text TEXT NOT NULL,
    embedding vector(768),
    district_id CHAR(3),
    station_id CHAR(10),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_table, source_id, source_field, chunk_index)
);
