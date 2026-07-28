# KSP Datathon 2026 

Karnataka State Police — Intelligent Conversational AI & Crime Analytics
Platform. 

## Directory structure

**Application services**

```
backend/              FastAPI service — auth, /ask orchestrator agent, voice
                       intake, PDF export. See backend/README.md.
frontend/              Next.js app (dashboard, cases, ask, admin). See
                       frontend/README.md.
embeddings-service/    Standalone microservice serving multilingual-e5-base
                       embeddings for RAG retrieval. See
                       embeddings-service/README.md.
```

**Data & schema**

```
db/                    Hand-authored SQL migrations + curated reference CSVs.
                       See db/README.md.
dataset/               Raw, read-only source data (boundaries, station maps,
                       BNS/IPC PDFs) the seed pipeline builds from. See
                       dataset/README.md.
scripts/seed/          Seeding pipeline: normalizes dataset/ → loads db/
                       migrations → populates Supabase with reference data,
                       golden demo threads, Kannada translations, and
                       embeddings. Order and details in db/README.md.
```

**Docs & references**

```
steering-docs/         Architecture and design specs (auth, orchestrator,
                       semantic layer, data schema, demo scenarios, etc.) —
                       the source of truth for how the system is supposed to
                       behave.
References/            Datathon challenge brief PDFs (data discovery, demo
                       script, evaluation criteria, semantic layer, trust
                       design).
```

**Deployment config**

```
client/                Unused default Catalyst client scaffold, superseded by
                       frontend/out (the actual deployed static export).
catalyst.json,         Zoho Catalyst deployment config (see Deployment
.catalystrc            below).
```

## Running locally

### 1. Backend (FastAPI)

```bash
cd backend
cp .env.example .env   # fill in Supabase + LLM credentials — see backend/README.md
uvicorn app.main:app --reload --workers 1
```

Runs at http://localhost:8000. `--workers 1` is required — the agent's
thread store is in-process (`steering-docs/ORCHESTRATOR_STEERING.md` O-13).

Set `ASK_ENGINE=agent` in `backend/.env` to run the real orchestrator against
live data (needs the embeddings service above and working LLM credentials);
`fixture` (the default) serves canned demo responses instead. Point
`EMBEDDINGS_BASE_URL` at `http://localhost:8081/v1` when running the agent
engine locally.

> If `uvicorn` fails with a "bad interpreter" error, the committed `.venv`'s
> console scripts may have a stale shebang from an earlier repo location.
> Work around it with `python -m uvicorn app.main:app --reload --workers 1`,
> or rebuild the venv.

### 2. Frontend (Next.js)

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install   # first time only
npm run dev
```

Runs at http://localhost:3000.

See `backend/README.md`, `frontend/README.md`, and
`embeddings-service/README.md` for full setup (Supabase migrations, demo
user provisioning, mock-vs-real Ask service toggle).

### Demo credentials

For evaluators — accounts seeded by `backend/scripts/demo_users.json` via
`backend/scripts/provision_users.py`:

| Username         | Password      | Role                   | Officer ID   |
| ---------------- | ------------- | ---------------------- | ------------ |
| `io.demo`         | `I0_ER`       | investigating_officer  | KSP-23417    |
| `supervisor.demo` | `$upervis0r`  | supervisor              | KSP-70068    |
| `analyst.demo`    | `An@lyst`     | analyst                 | KSP-87128    |
| `admin.demo`      | `@dmin`       | admin                   | —            |

### Database

The backend and agent expect a Supabase Postgres instance with the schema in
`db/migrations/` applied and seeded via `scripts/seed/` (reference data,
golden demo threads, Kannada translations, and embeddings). See
`db/README.md` for the migration list and full seeding order, and
`dataset/README.md` for what raw source data feeds into it.

## Deployment

The app is hosted entirely on [Zoho Catalyst](https://www.catalyst.zoho.com/),
Zoho's serverless application platform, across three of its services:

- **AppSail** — runs the `backend` and `embeddings-service` as separate
  Docker containers. `catalyst.json` declares the AppSail entry for the
  backend; `backend/Dockerfile` and `embeddings-service/Dockerfile` both bind
  to the port Catalyst injects via `X_ZOHO_CATALYST_LISTEN_PORT` (falling
  back to 8080 for local `docker run`).
- **Client** — serves the frontend's Next.js static export (`frontend/out`)
  as a static site; also declared in `catalyst.json`.
- **Cache / Stratus / QuickML** — supporting Catalyst services used at
  runtime by the backend (response caching, object storage, and the
  in-platform LLM used for intent classification respectively); configured
  via env vars, not declared in `catalyst.json`.

Production env vars (Supabase, LLM profiles, Catalyst OAuth/cache/Stratus
settings) are configured per-environment in Catalyst, not committed to the
repo — `backend/app-config.json` (gitignored) holds the local copy used for
deploys. Deployed URLs are intentionally not listed here; ask a maintainer
for the current environment link.


