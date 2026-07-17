# `db/` — schema migrations and curated reference data

This directory holds the two things that are hand-authored rather than
derived: the raw SQL schema (`migrations/`) and small analyst-curated
lookup CSVs (`reference/`) that the seeding scripts depend on as FK targets
or calibration inputs. The actual seeded rows live in Supabase Postgres, not
in this repo — see [Seeding pipeline](#seeding-pipeline-scriptsseed) below
for how they get there.

## `migrations/` — schema, indexes, RLS

Numbered, applied in order via `scripts/seed/apply_migrations.py`. Each file
commits independently, so a failure partway through only rolls back that
file — `apply_migrations.py --from 004` resumes cleanly after a fix.

| File | Creates |
|---|---|
| `001_extensions.sql` | `postgis`, `pg_trgm`, `pgcrypto`, `vector` — idempotent |
| `002_reference_tables.sql` | Groups A/B/I: districts, admin_boundaries, sub_divisions, circles, police_stations, localities, officers, bns_sections, crime_types |
| `003_case_tables.sql` | Groups C–G: persons and every FIR/investigation/intelligence/property table (35 tables total across all migrations) |
| `004_audit_semantic.sql` | Group H (`query_audit_log`) and Group J (`document_chunks`, the RAG chunk+embedding store) |
| `005_indexes.sql` | GiST on every geometry/boundary column, trigram GIN for fuzzy name/plate search, tsvector GIN for full-text search, HNSW (`vector_cosine_ops`) on `document_chunks.embedding` |
| `006_rls.sql` | Row-Level Security: reference tables (Groups A/B/I) readable by any authenticated role; case tables (Groups C–G) readable only by `investigating_officer`/`supervisor`/`analyst` (admin gets **no** policy — default deny); `query_audit_log` is SELECT-only for `admin`, append-only for everyone |
| `007_fix_write_grants.sql` | Closes a gap `006` left open: Supabase auto-grants `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` to `anon`/`authenticated` on every new table by default, independent of any RLS policy. `006` only revoked from `PUBLIC`, which doesn't touch a grant made directly to those roles. `007` revokes the direct grants (and fixes default privileges so new tables don't reopen the gap) — found and confirmed via a **live** JWT-authenticated RLS test (`scripts/seed/verify_rls_live.py`), not just by reading policy definitions. |

RLS enforcement is genuinely live-tested, not just defined: `verify_rls_live.py`
drives real Postgres role-switching (`SET ROLE authenticated` + a simulated
`request.jwt.claims`) to confirm each role sees exactly the rows it should,
and that `query_audit_log` mutation is denied for every role including
`admin` — against an actual inserted-then-rolled-back test row, not an empty
table.

## `reference/` — curated CSVs (FK targets, not raw source data)

| File | Purpose |
|---|---|
| `district_units.csv` | The authoritative 37-unit KSP police-district code list (31 revenue districts + 6 commissionerates). Every other table's `district_id` FK ultimately points here. Built by `scripts/seed/build_district_units.py` from the normalized district GeoJSON, with judgment calls (e.g. how Bengaluru's revenue-district split maps onto police-commissionerate units) documented inline in that script rather than silently resolved. Includes an `is_active` column — only 10 of the 37 units carry synthetic case data (FIRs, persons, NCRs, …); the rest carry reference/boundary data only. |
| `crime_mix.csv` | Analyst-specified per-district crime-type weighting used only for the background-corpus generator (`scripts/seed/07_background.py`) to pick a plausible `crime_type_id` per synthetic FIR. **Explicitly not derived from NCRB or any published crime statistics** — see the file's own header comment — and must never be presented as such. |

## Seeding pipeline (`scripts/seed/`)

The scripts that actually populate the database, run in this order:

1. `00_normalize_sources.py`, `extract_bns.py` — see [`seed-sources/README.md`](../seed-sources/README.md)
2. `apply_migrations.py` — runs everything in `migrations/`
3. `01_reference.py` — loads real geodata: districts, admin boundaries, police stations, localities, synthesized sub-divisions/circles, station jurisdiction polygons (Voronoi), BNS sections
4. `02_lookups.py` — loads `crime_types` (~49), `mo_codes` (~83, hand-curated modus-operandi catalog), `officers` (100, synthesized roster), `district_socioeconomic`
5. `03_synthetic.py` — the three **golden demo threads** (Chain Gang / Repeat Victim / Dasara Bandobast), each with exact named entities, MO codes, and DBSCAN hotspot-cluster guarantees required by the demo scenarios; narrative text (English) generated locally via Ollama, grounded in each row's own structured facts so narrative can't contradict data
6. `06_kannada_pass.py` — batched Kannada mirror translation (`ai4bharat/indictrans2-en-indic-1B`, sentence-aligned) for master-data labels (100%) and narrative fields (at the population rates the schema doc specifies)
7. `07_background.py` — background-corpus generator (persons/gangs stages only run so far; FIR/NCR/diary-entry generation was deferred — not required for the golden threads to work, and multi-hour on this hardware)
8. `04_embed.py` — chunks every RAG-marked narrative field and embeds each chunk with `intfloat/multilingual-e5-base` (768-dim) into `document_chunks`, with sentence-range citation anchors and denormalized `district_id`/`station_id` for scoped retrieval
9. `05_validate.py` — the full GATE 6 validation suite (referential integrity, geometry containment, cluster guarantees, reserved-registry absence, `_kn` rates, RLS policy shape, embedding population); writes `seed-sources/validation_report.json`

Several `fix_*.py` / `verify_*.py` scripts alongside these are one-off
retrofits and live checks written in response to specific issues the
validator or manual review surfaced (e.g. `fix_stray_cjk.py` for a local
LLM occasionally code-switching into Chinese mid-generation,
`verify_rls_live.py` for the live RLS test described above) — each has a
docstring explaining what it found and fixed.
