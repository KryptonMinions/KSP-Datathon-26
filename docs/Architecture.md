# System Architecture Reference
## KSP Datathon 2026 — Challenge 1: Intelligent Conversational AI & Crime Analytics Platform

**Purpose of this document:** This is the reference architecture for coding agents and contributors building this repo. It reflects the finalized product plan (23 user stories, 5 personas, 17 components) and the v1 build scope. Treat this as the source of truth for module boundaries, naming, and build order. Do not introduce new top-level components without updating this doc.

---

## 1. System Overview

A natural-language conversational interface over a Karnataka State Police crime database, combined with investigative analytics (network analysis, MO/pattern matching, case intelligence) for five personas: **Investigating Officer (IO)**, **Supervisor**, **Analyst**, **Policymaker**, **Admin**.

**v1 scope:** 23 of 26 identified user stories. Financial crime (Module 7) and crime forecasting (Module 8) are explicitly deferred to Phase 2, along with predictive models (C11). Geospatial analytics are schema-ready (lat/lng columns present) but map rendering, hotspot detection, and PostGIS are Phase 2.

**Guiding principle:** Trust (citation, RBAC, audit) is cross-cutting infrastructure, not a bolt-on feature. Every answer must be traceable, role-filtered, and logged from day one — this is not deferred to "polish later."

---

## 2. Component Inventory (C1–C17)

Components are grouped into four layers. C11 is out of scope for v1 (Phase 2 only). C14/C15/C16 apply implicitly to every story and every response.

### Layer 1 — Interaction
| ID | Component | v1 Scope |
|----|------------|---------|
| C1 | Chat interface & session/context manager | Multi-turn state, resolves references like "those cases" |
| C2 | Voice pipeline (Kannada/English STT+TTS) | Stubbed in v1; not required for the live demo |
| C3 | Export & report generator | PDF/brief export, formatted reports |

### Layer 2 — Understanding & Query
| ID | Component | v1 Scope |
|----|------------|---------|
| C4 | Query orchestrator (agent) | **Custom lightweight router — no agent framework.** Classifies intent, routes to C6/C7/C9/C12/C13 |
| C5 | Domain semantic layer | BNS↔IPC mapping, crime taxonomy (EN/Kannada), glossary, metric definitions, schema-to-concept map, role/jurisdiction resolver. Encoded as static YAML, injected into orchestrator/prompt context |
| C6 | Structured query engine (text-to-SQL) | Highest-frequency component; used by 12 of 23 stories |
| C7 | Semantic search / RAG | Vector retrieval over FIR narratives, MO descriptions, case diary text |
| C8 | Entity resolution service | Dedupes people/addresses/phones across name variants and scripts; feeds C6 and C9 |

### Layer 3 — Analytics
| ID | Component | v1 Scope |
|----|------------|---------|
| C9 | Graph engine | **SQL-first for v1**: build graph from relational tables (`known_associates`, `gang_memberships`, `fir_accused`) using NetworkX at query time; render with vis.js or Cytoscape.js on the frontend. No dedicated graph DB in v1 |
| C10 | Geo-temporal analytics | Trend/seasonality only in v1 (no map rendering, no hotspot algorithms — Phase 2) |
| C11 | Predictive models | **Out of scope — Phase 2.** Do not stub API surface beyond a documented placeholder |
| C12 | Case intelligence services | Summarization, timeline construction, similar-case matching |
| C13 | Alerting & subscription service | Watchlists, spike detection (non-predictive), scheduled notifications |

### Layer 4 — Trust (cross-cutting, applies to every response)
| ID | Component | v1 Scope |
|----|------------|---------|
| C14 | Citation / provenance layer | Every claim traced to record IDs. Three levels: FIR-level, field-level, sentence-level (RAG). See §5 |
| C15 | RBAC policy engine | Enforced at the **data access layer**, never at the prompt layer. See §5 |
| C16 | Audit & monitoring | Immutable log of every query, answer, and record touched |
| C17 | Data pipeline & external connectors | ETL, data-quality processing, external dataset joins |

---

## 3. Tech Stack (v1)

| Layer | Choice | Notes |
|---|---|---|
| Backend API | **FastAPI (Python)** | Hosts C4 orchestrator and all engine endpoints |
| Frontend | **Next.js (App Router) + Tailwind CSS + shadcn/ui** | Chat UI + persona dashboards |
| LLM orchestration (C4) | **Custom lightweight router — no LangChain/LangGraph.** | Simple intent classifier → engine dispatch table. Keep this transparent and debuggable; a hackathon jury will ask "how does the system decide where to route a query" and the answer needs to be inspectable code, not a black-box agent framework |
| Database | **Deferred to deployment platform.** | Product plan assumed PostgreSQL + pgvector + tsvector for v1 prototyping. **Actual deployment target is Zoho Catalyst** (backend, frontend, and data store). This repo does NOT scaffold a local Postgres/pgvector instance — see §4 and §7 |
| Graph rendering | NetworkX (backend, computed at query time) + vis.js/Cytoscape.js (frontend) | No Neo4j in v1 |
| Embeddings | `intfloat/multilingual-e5-base` (EN + Kannada) | Wire in once a data store is chosen on Catalyst |

**Open item flagged for the team:** the original data architecture doc (18-table schema) was designed against PostgreSQL semantics (UUID PKs, `TEXT[]` arrays, `tsvector` full-text columns, DECIMAL lat/lng). Zoho Catalyst's native Data Store has different modeling primitives. Before C6 (text-to-SQL) and C17 (data pipeline) are built out, confirm whether Catalyst will host an actual PostgreSQL instance, or whether the schema needs translating to Catalyst's Data Store model. This repo's data access layer (`backend/app/data/`) is deliberately abstracted behind a repository interface so the underlying store can be swapped without touching engine logic.

---

## 4. Directory Structure

```
ksp-datathon-2026/
├── docs/
│   └── ARCHITECTURE.md              # this document
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app entrypoint
│   │   ├── core/
│   │   │   └── config.py            # settings, env vars
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       ├── chat.py          # C1 session + C4 orchestrator entrypoint
│   │   │       ├── query.py         # direct query endpoint (bypasses chat framing)
│   │   │       ├── graph.py         # C9 network endpoints
│   │   │       └── reports.py       # C3 export endpoints
│   │   ├── orchestrator/            # C4
│   │   │   ├── router.py            # custom lightweight router / dispatch table
│   │   │   └── classifier.py        # intent classification stub
│   │   ├── semantic_layer/          # C5
│   │   │   ├── crime_taxonomy.yaml
│   │   │   ├── bns_ipc_mapping.yaml
│   │   │   └── glossary.yaml
│   │   ├── engines/
│   │   │   ├── sql_engine.py        # C6 — stub
│   │   │   ├── rag_engine.py        # C7 — stub
│   │   │   ├── entity_resolution.py # C8 — stub
│   │   │   ├── graph_engine.py      # C9 — NetworkX stub
│   │   │   ├── case_intelligence.py # C12 — stub
│   │   │   └── alerting.py          # C13 — stub
│   │   ├── trust/
│   │   │   ├── citation.py          # C14
│   │   │   ├── rbac.py              # C15
│   │   │   └── audit.py             # C16
│   │   └── data/
│   │       ├── repository.py        # abstract data access interface (Catalyst-agnostic)
│   │       └── models.py            # pydantic schemas mirroring the 18-table data dictionary
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/
│   ├── app/                         # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx                 # chat interface (C1)
│   │   └── dashboard/
│   │       └── page.tsx             # supervisor/analyst dashboard shell
│   ├── components/
│   │   ├── chat/
│   │   ├── citation/                # C14 UI — source chips / evidence trail
│   │   └── ui/                      # shadcn components
│   ├── lib/
│   │   └── api.ts                   # fetch wrapper to backend
│   ├── package.json
│   ├── tailwind.config.ts
│   └── README.md
├── .gitignore
└── README.md
```

---

## 5. Trust Layer — Build Rules (non-negotiable, per locked decisions)

**C14 — Citation.** Every response carries a structured citation payload. Three levels, chosen automatically by which engine produced the answer:
- FIR-level (aggregate/count queries from C6)
- Field-level (lookup queries about a specific person/case from C6)
- Sentence-level (RAG answers from C7 — cites `case_diary_entry` id + date)

**C15 — RBAC.** Enforced at the data access layer (`backend/app/data/repository.py`), before any record reaches the LLM or the orchestrator. Never enforce role filtering only at the prompt layer — a reworded query must not be able to bypass it.

**C16 — Audit.** Every query, the engine it was routed to, and every record ID touched is logged immutably. This log is itself queryable by Admin persona stories (anomaly detection).

---

## 6. Query Orchestrator (C4) — Design Intent

No agent framework. The router is a plain, inspectable dispatch table:

1. Classify the incoming query into one of: `structured_lookup`, `semantic_search`, `network_query`, `case_summary`, `report_export`, `alert_management`.
2. Attach session context (persona, role, jurisdiction) from C1.
3. Ground the query against C5 (semantic layer) before dispatch — resolve synonyms, BNS/IPC sections, time expressions.
4. Dispatch to the corresponding engine (C6/C7/C9/C12/C13).
5. Wrap the engine's raw result with the C14 citation payload before returning to C1.

Keep `classifier.py` simple and swappable (rule-based v1, upgradeable to a small classifier model later) — the priority is that a jury or teammate can read the routing logic in one file and understand exactly why a query went where it went.

---

## 7. What This Repo Scaffold Does NOT Include (by design)

- No local PostgreSQL / pgvector instance — deployment target is Zoho Catalyst; data layer is abstracted so the concrete store is a later decision.
- No C11 (predictive models) implementation or API surface — Phase 2.
- No map rendering / PostGIS — Phase 2.
- No production auth provider wiring — `trust/rbac.py` is a stub with the role model defined, not connected to a real identity provider yet.
- No LangChain/LangGraph — orchestration is intentionally custom and minimal.

---

## 8. Build Order (recommended)

1. Data access repository interface + pydantic models mirroring the 18-table schema (even before the concrete Catalyst store is picked, this unblocks engine stubs).
2. C5 semantic layer YAML files (already designed — port from the Semantic Layer reference doc).
3. C4 router + classifier skeleton, wired to stub engines that return mock data.
4. C14/C15/C16 trust wrappers around the response path — build these alongside the first real engine (C6), not after.
5. C6 (text-to-SQL) against real/synthetic data once the Catalyst data store decision is made.
6. C9 (graph, NetworkX) and C7 (RAG) next — both needed for the locked demo stories (1, 2, 4, 10).
7. Frontend chat UI wired to `/api/chat`, then citation UI, then the supervisor dashboard shell.

---

## 9. Backend Implementation Specification (file-by-file, for the coding agent)

```
backend/
├── app/
│   ├── main.py
│   ├── core/config.py
│   ├── api/routes/{health,chat,query,graph,reports}.py
│   ├── orchestrator/{router,classifier}.py
│   ├── semantic_layer/{glossary,bns_ipc_mapping,crime_taxonomy}.yaml + loader.py
│   ├── engines/{sql_engine,rag_engine,entity_resolution,graph_engine,case_intelligence,alerting}.py
│   ├── trust/{citation,rbac,audit}.py
│   └── data/{repository,models}.py
├── requirements.txt
├── .env.example
└── README.md
```

**`app/main.py`** — FastAPI app factory. Configures CORS (origins from settings), registers all route modules from `api/routes/`. No business logic here.

**`app/core/config.py`** — Pydantic `Settings` (via `pydantic-settings`), loaded from `.env`. Fields: `app_env`, `app_name`, `cors_origins` (comma-separated, exposed as a list), and placeholders for the eventual Catalyst connection (`catalyst_project_id`, `catalyst_data_store_url`) plus `anthropic_api_key`. Leave Catalyst fields blank until provisioned.

**`app/data/models.py`** — Pydantic models mirroring the 18-table Data Architecture doc. Start with the slice each early engine needs: `Person` (person_id, full_name, aliases, gender, dob), `FIR` (fir_id in format `KA-[DIST]-[STN_SERIAL]-[YEAR]-[FIR_SERIAL]`, district, station, year, bns_sections, ipc_sections, fir_narrative, filed_on, investigation_status), `CaseDiaryEntry` (entry_id, fir_id, entry_date, entry_text, investigating_officer_id), `KnownAssociate` (person_id_a, person_id_b, relationship_type), `GangMembership` (gang_id, person_id, role), and `UserRole` (user_id, persona, district_scope, station_scope) as the backing model for C15. Expand toward the full 18 tables as engines require them.

**`app/data/repository.py`** — Abstract `Repository` interface (ABC) with methods: `get_person`, `search_firs`, `get_case_diary`, `get_known_associates`, `get_gang_memberships` — every method takes the requester's `UserRole` as an argument so RBAC filtering happens inside the implementation, never upstream. Ship one concrete implementation for local development — an in-memory/mock repository seeded with a couple of representative records — so the API is runnable end-to-end before a real store exists. A FastAPI dependency function (`get_repository`) returns the active implementation; this is the single place to swap in a Catalyst-backed (or Postgres-backed) implementation later without touching any engine code.

**`app/semantic_layer/*.yaml`** — Static content files, ported directly from the already-produced Semantic Layer C5 reference document: `crime_taxonomy.yaml` (25 crime types, EN + Kannada aliases, primary BNS section), `bns_ipc_mapping.yaml` (26+ section mappings with cognizability/bailability, plus special acts), `glossary.yaml` (24 bilingual procedure terms + investigation status mapping). `loader.py` loads and caches these at startup and exposes a `resolve_crime_type(term)` helper that matches an English or Kannada term to a `crime_type_id` for use during query grounding.

**`app/engines/sql_engine.py` (C6)** — Text-to-SQL / structured query engine. v1 stub: accepts the query text and requester, calls `repository.search_firs`, and returns a citation-wrapped answer (FIR-level). Replace with real NL→query translation once the concrete data store is chosen.

**`app/engines/rag_engine.py` (C7)** — Semantic search over FIR narratives, MO descriptions, case diary text. v1 stub returns a placeholder sentence-level citation. Real implementation needs a vector index (embeddings model `intfloat/multilingual-e5-base`, chosen for EN+Kannada coverage) once the data store supports it.

**`app/engines/entity_resolution.py` (C8)** — Resolves a name/alias string to a canonical `Person`. v1: exact/case-insensitive match against name + aliases. Upgrade path: fuzzy matching and cross-script (Kannada↔English) matching.

**`app/engines/graph_engine.py` (C9)** — Builds a person's network **at query time** from relational data (`known_associates`, `gang_memberships`) using NetworkX, and returns a plain `{nodes: [...], edges: [...]}` payload for the frontend to render (vis.js/Cytoscape.js). No graph database in v1.

**`app/engines/case_intelligence.py` (C12)** — Case summarization from `CaseDiaryEntry` records for a given FIR; returns a sentence-level citation referencing the entry IDs used.

**`app/engines/alerting.py` (C13)** — Watchlist/alert data model and a `list_active_alerts(user_id)` stub returning an empty list in v1.

**`app/trust/citation.py` (C14)** — Defines `CitationLevel` enum (`fir_level`, `field_level`, `sentence_level`), a `Citation` model (level, source_ids, optional detail string), and a `CitedResponse` model (`answer`, `citations: list[Citation]`) that every engine returns. Provide a `wrap_with_citation(answer, level, source_ids, detail=None)` helper so engines don't hand-build the payload.

**`app/trust/rbac.py` (C15)** — Defines the valid persona set (`investigating_officer`, `supervisor`, `analyst`, `policymaker`, `admin`) and a `get_current_user()` stub that resolves the session's `UserRole`. This is explicitly **not** wired to a real identity provider yet — replace with actual auth (Zoho Catalyst's auth service, most likely) before anything beyond local development. The actual access filtering logic lives in `repository.py`, not here.

**`app/trust/audit.py` (C16)** — An `AuditEvent` model (timestamp, user_id, persona, query_text, routed_to, record_ids_touched) and a `log_event(...)` function. v1: append to an in-memory list (or stdout). Replace with an append-only store before deployment — this backs the Admin persona's audit-anomaly story.

**`app/orchestrator/classifier.py` (C4, part 1)** — Rule-based intent classifier (keyword matching is sufficient for v1) returning one of: `structured_lookup`, `semantic_search`, `network_query`, `case_summary`, `report_export`, `alert_management`. Deliberately simple and readable — no ML model, no framework — so anyone can read the file and understand exactly why a query was routed a given way.

**`app/orchestrator/router.py` (C4, part 2)** — `handle_query(query_text, requester, repo)`: classifies the query, dispatches to the matching engine, and logs the interaction via `audit.log_event` before returning the engine's `CitedResponse`. This is the one file that ties C4 → C5 (grounding) → C6/C7/C9/C12/C13 → C14 → C16 together. Keep it a flat if/elif dispatch table, not a class hierarchy or plugin system — legibility over cleverness.

**`app/api/routes/health.py`** — `GET /health` → `{"status": "ok"}`.

**`app/api/routes/chat.py`** — `POST /api/chat` with body `{message: str, persona: str}`. Resolves the current user via `rbac.get_current_user(persona=...)`, calls `orchestrator.router.handle_query`, returns a `CitedResponse`. This is the primary entrypoint the frontend chat UI (C1) calls.

**`app/api/routes/query.py`** — `POST /api/query` — same shape as `/api/chat` but framed as a direct analytics query (used by dashboard-style callers rather than the conversational UI).

**`app/api/routes/graph.py`** — `GET /api/graph/{person_id}?persona=...` → calls `engines.graph_engine.build_network`, returns the nodes/edges payload.

**`app/api/routes/reports.py`** — `GET /api/reports/status` stub for v1; expand into real export endpoints (C3) later.

**`requirements.txt`** — Keep minimal for v1 since there's no local DB: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `python-dotenv`, `pyyaml`, `networkx`. Add a DB driver only once the Catalyst/Postgres decision in §3 is resolved.

**`.env.example`** — `APP_ENV`, `APP_NAME`, `CORS_ORIGINS`, `CATALYST_PROJECT_ID`, `CATALYST_DATA_STORE_URL`, `ANTHROPIC_API_KEY`.

---

## 10. Frontend Implementation Specification (file-by-file, for the coding agent)

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── globals.css
│   ├── page.tsx                # chat interface (C1)
│   └── dashboard/page.tsx      # supervisor/analyst dashboard shell
├── components/
│   ├── chat/                   # message list, message input, persona switcher
│   ├── citation/                # C14 UI — source chips / evidence trail
│   └── ui/                     # shadcn/ui primitives (button, card, input, badge)
├── lib/
│   ├── api.ts                  # fetch wrapper to backend
│   └── utils.ts                # cn() helper (clsx + tailwind-merge), shadcn convention
├── package.json
├── tailwind.config.ts
├── postcss.config.js
├── next.config.js
├── tsconfig.json
└── README.md
```

**Setup approach for the coding agent:** scaffold with `npx create-next-app@latest` (TypeScript, App Router, Tailwind CSS, no `src/` directory to match the structure above), then run `npx shadcn@latest init` followed by `npx shadcn@latest add button card input badge scroll-area` to pull in the UI primitives referenced below — don't hand-write shadcn components from scratch.

**`app/layout.tsx`** — Root layout, sets metadata (title: "KSP Crime Analytics", description referencing the Datathon), imports `globals.css`.

**`app/globals.css`** — Tailwind directives + shadcn's CSS custom properties (`--background`, `--foreground`, `--primary`, `--muted`, `--border`, `--radius`, etc.) — generated automatically by `shadcn init`.

**`app/page.tsx`** — The chat interface (C1). Persona switcher (dropdown: IO / Supervisor / Analyst / Policymaker / Admin) at the top, a scrollable message list, a message input at the bottom. On submit, calls `lib/api.ts`'s `sendChatMessage(message, persona)`, appends the response, and renders its citations via the `citation/` components.

**`app/dashboard/page.tsx`** — Placeholder shell for the Supervisor/Analyst persona dashboard (Story 10-style monthly review pack). Not a priority until the chat interface and the four locked demo stories (1, 2, 4, 10) are working.

**`components/chat/`** — `MessageList`, `MessageBubble`, `MessageInput`, `PersonaSwitcher`. Keep these presentational; state lives in `app/page.tsx` (or a small hook) for v1 — no global state library needed yet.

**`components/citation/`** — `CitationChip` (renders one `Citation` as a small pill showing its level and source IDs — this is the UI expression of C14, the "clickable citation" pattern referenced in the Trust Design doc), `EvidenceTrail` (expands a message's full citation list).

**`components/ui/`** — Standard shadcn/ui primitives, added via the CLI, not hand-written.

**`lib/api.ts`** — Typed fetch wrapper. Exports `Citation`, `CitedResponse` types (matching the backend's citation model exactly), and `sendChatMessage(message, persona)` which POSTs to `${NEXT_PUBLIC_API_BASE_URL}/api/chat`. `NEXT_PUBLIC_API_BASE_URL` defaults to `http://localhost:8000` for local dev; set it to the deployed backend URL on Zoho Catalyst.

**`lib/utils.ts`** — `cn()` helper combining `clsx` + `tailwind-merge`, the standard shadcn/ui convention.

**Dependencies:** `next`, `react`, `react-dom`, `clsx`, `tailwind-merge`, `lucide-react`, `class-variance-authority` (all pulled in automatically by `create-next-app` + `shadcn init`); dev dependencies `typescript`, `tailwindcss`, `postcss`, `autoprefixer`, `@types/*`.

**API contract note for the agent:** the frontend's `Citation`/`CitedResponse` TypeScript types must stay structurally identical to the backend's citation model (§9) — `level` is one of `"fir_level" | "field_level" | "sentence_level"`.

---

## 11. Deployment Note (Zoho Catalyst)

Both backend and frontend, plus the data store, are targeted at Zoho Catalyst. Before deployment, resolve:
- What Catalyst offers for hosting the backend (Python/serverless function support vs. a container-based service) — FastAPI needs an ASGI-compatible host, so confirm which Catalyst product fits.
- The Catalyst data store option (native Data Store vs. managed external DB) and the schema-translation question flagged in §3, before building out C6 and C17 further.
- Whether Catalyst serves Next.js as a static export or with a Node runtime — this affects whether App Router server components/API routes are usable, or whether the frontend should lean entirely on the separate FastAPI backend for all data access.

---

*Document version: v1.1 — companion to the Product Plan, Data Architecture, Semantic Layer, and Trust Design documents already produced for this project. This version adds the backend/frontend implementation specification (§9–§11) for direct hand-off to a coding agent. No code is scaffolded in this repo — this document is the sole deliverable, to be fed to the coding agent for actual implementation.*